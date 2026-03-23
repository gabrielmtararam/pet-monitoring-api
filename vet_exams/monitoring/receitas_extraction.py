"""
Extract structured prescription data from receita PDF/image using Gemini,
then persist Remedio and IndicacaoMedicamento.
"""
import json
import os
import time
from datetime import date

from django.db.models import Count
from google import genai
from google.genai import types

from vet_exams.monitoring.models import IndicacaoMedicamento, Receita, Remedio


def _build_remedios_catalog() -> str:
    """Build catalog text of registered medicines (name and principio_ativo) for the prompt."""
    remedios = Remedio.objects.all().values_list("name", "principio_ativo")
    if not remedios:
        return "Remédios já cadastrados: (nenhum).\n\nCadastre novos em new_remedios quando o medicamento não existir no catálogo."
    lines = ["Remédios já cadastrados (use o nome exatamente como abaixo quando for o mesmo medicamento):", ""]
    for name, principio in remedios:
        p = f" (princípio ativo: {principio})" if principio else ""
        lines.append(f"  - {name}{p}")
    lines.append("")
    lines.append("Se o medicamento não existir no catálogo, inclua em new_remedios e use o nome em indicacoes[].remedio.")
    return "\n".join(lines)


PROMPT_RECEITA = """
Analise esta receita veterinária (PDF ou imagem). Extraia a data da receita (se constar) e todas as prescrições/medicações, com: nome do remédio, forma de apresentação (ex.: frasco, comprimido), medida da apresentação (ex.: 2mg/ml), dosagem (ex.: 0,4ml), frequência (ex.: a cada 12 horas) e período (ex.: por 7 dias).

{catalog}

{suggestions}

Retorne APENAS um único objeto JSON válido, sem texto antes ou depois, com a seguinte estrutura:

{{
  "data_receita": "data da receita em ISO (YYYY-MM-DD) ou null se não identificável",
  "new_remedios": [
    {{ "name": "nome comercial ou do medicamento", "principio_ativo": "princípio ativo/substância ou vazio" }}
  ],
  "indicacoes": [
    {{
      "remedio": "nome do remédio (do catálogo ou igual ao que colocou em new_remedios)",
      "forma_apresentacao": "ex.: frasco, comprimido",
      "medida_apresentacao": "ex.: 2mg/ml",
      "dosagem": "ex.: 0,4ml",
      "frequencia": "ex.: a cada 12 horas",
      "periodo": "ex.: por 7 dias"
    }}
  ]
}}

Regras:
- Para cada medicação prescrita na receita, preencha um item em indicacoes.
- remedio em indicacoes: use o nome exato do catálogo quando for o mesmo medicamento; caso contrário use um nome descritivo e inclua em new_remedios.
- new_remedios: apenas medicamentos que não existem no catálogo. Para cada um informe name e principio_ativo (se souber).
- data_receita: use apenas se constar no documento; senão null.
- Retorne somente o JSON, sem markdown e sem explicações.
"""


def _get_genai_client():
    api_key = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não configurada no ambiente.")
    return genai.Client(api_key=api_key)


def _extract_json_from_text(text: str) -> dict | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _parse_data_receita(value) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def process_receita_with_gemini(receita: Receita) -> dict:
    """
    Send receita file to Gemini with remedios catalog, parse JSON,
    create new Remedio as needed, create IndicacaoMedicamento for each item.
    """
    if not receita.file:
        return {"success": False, "detail": "Receita sem arquivo anexado."}

    path = getattr(receita.file, "path", None)
    if not path or not os.path.isfile(path):
        return {"success": False, "detail": "Arquivo da receita não encontrado no disco."}

    client = _get_genai_client()
    catalog = _build_remedios_catalog()
    suggestions = f"Sugestão de data (da página): {receita.data.isoformat()}.\n\n" if receita.data else ""
    prompt = PROMPT_RECEITA.format(catalog=catalog, suggestions=suggestions)

    mime_type = "application/pdf"
    if path.lower().endswith((".png", ".jpg", ".jpeg")):
        mime_type = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    uploaded = client.files.upload(file=path, config={"mime_type": mime_type})
    state = getattr(uploaded, "state", None)
    state_name = getattr(state, "name", None) if state is not None else str(state) if state is not None else None
    while state_name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)
        state = getattr(uploaded, "state", None)
        state_name = getattr(state, "name", None) if state is not None else str(state) if state is not None else None
    if state_name == "FAILED":
        return {"success": False, "detail": "Falha no upload do arquivo para o Gemini."}

    file_part = types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type or mime_type)
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=[prompt, file_part],
    )
    text = getattr(response, "text", None) or ""
    data = _extract_json_from_text(text)
    if not data:
        return {"success": False, "detail": "Resposta da IA não contém JSON válido.", "raw": text[:500]}

    usage = getattr(response, "usage_metadata", None)
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    if usage is not None:
        if hasattr(usage, "get"):
            prompt_tokens = usage.get("prompt_token_count") or usage.get("prompt_tokens")
            completion_tokens = usage.get("candidates_token_count") or usage.get("completion_tokens")
            total_tokens = usage.get("total_token_count") or usage.get("total_tokens")
        else:
            prompt_tokens = getattr(usage, "prompt_token_count", None) or getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "candidates_token_count", None) or getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_token_count", None) or getattr(usage, "total_tokens", None)

    # Optional: update receita.data from document
    data_receita = _parse_data_receita(data.get("data_receita"))
    if data_receita:
        receita.data = data_receita
        receita.save(update_fields=["data"])

    # Create new Remedio from new_remedios
    for item in data.get("new_remedios") or []:
        if not isinstance(item, dict) or not (item.get("name") or "").strip():
            continue
        name = (item.get("name") or "").strip()[:200]
        principio = (item.get("principio_ativo") or "").strip()[:200] or None
        Remedio.objects.get_or_create(
            name=name,
            defaults={"principio_ativo": principio},
        )

    # Create IndicacaoMedicamento for each indicacao
    created_count = 0
    for idx, ind in enumerate(data.get("indicacoes") or []):
        if not isinstance(ind, dict) or not (ind.get("remedio") or "").strip():
            continue
        remedio_name = (ind.get("remedio") or "").strip()[:200]
        remedio, _ = Remedio.objects.get_or_create(name=remedio_name, defaults={"principio_ativo": None})
        forma = (ind.get("forma_apresentacao") or "").strip()[:100] or None
        medida = (ind.get("medida_apresentacao") or "").strip()[:80] or None
        dosagem = (ind.get("dosagem") or "").strip()[:80] or None
        frequencia = (ind.get("frequencia") or "").strip()[:120] or None
        periodo = (ind.get("periodo") or "").strip()[:120] or None
        IndicacaoMedicamento.objects.create(
            receita=receita,
            remedio=remedio,
            forma_apresentacao=forma,
            medida_apresentacao=medida,
            dosagem=dosagem,
            frequencia=frequencia,
            periodo=periodo,
            order=idx,
        )
        created_count += 1

    receita.gemini_prompt_tokens = prompt_tokens
    receita.gemini_completion_tokens = completion_tokens
    receita.gemini_total_tokens = total_tokens
    receita.save(update_fields=["gemini_prompt_tokens", "gemini_completion_tokens", "gemini_total_tokens"])

    return {
        "success": True,
        "detail": "Receita processada e indicações salvas.",
        "receita_id": receita.id,
        "indicacoes_created": created_count,
        "gemini_prompt_tokens": prompt_tokens,
        "gemini_completion_tokens": completion_tokens,
        "gemini_total_tokens": total_tokens,
    }


def process_first_receita(user):
    """
    Get the first Receita with file that has no IndicacaoMedicamento yet (for user's animals),
    run Gemini extraction and persist.
    """
    first = (
        Receita.objects.filter(animal__guardian=user)
        .exclude(file="")
        .annotate(indicacoes_count=Count("indicacoes"))
        .filter(indicacoes_count=0)
        .order_by("id")
        .first()
    )
    if not first:
        return {"success": False, "detail": "Nenhuma receita pendente de processamento (todas já processadas ou sem arquivo)."}
    return process_receita_with_gemini(first)
