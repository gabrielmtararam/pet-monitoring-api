"""
Extract structured exam data from PDF/image using Gemini (google.genai), then persist
ExamType, ParameterType, MeasurementUnit, ExtractedExam, ExamParameterResult.
"""
import json
import os
import time
from typing import Any

from google import genai
from google.genai import types
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from vet_exams.monitoring.models import (
    AnimalExam,
    ExamOrganFinding,
    ExamParameterResult,
    ExamType,
    ExtractedExam,
    MeasurementUnit,
    ParameterType,
)


def _build_suggestions_prompt(exam: AnimalExam) -> str:
    """Build the suggestions block (source exam type label and date) for the prompt."""
    parts = []
    if (exam.source_exam_type_label or "").strip():
        parts.append(
            f"Sugestão de tipo de exame (da página de origem): \"{(exam.source_exam_type_label or '').strip()}\". "
            "Pode ser um dos itens se a label tiver mais de um (ex.: Hemograma + Bioquímico → use só Bioquímico se o arquivo for só isso), ou ignore se não se aplicar (ex.: label 'Outros')."
        )
    if exam.source_observed_at:
        parts.append(
            f"Sugestão de data/hora do exame (da página): {exam.source_observed_at.isoformat()}. "
            "Use apenas se não encontrar data/hora no documento."
        )
    if not parts:
        return ""
    return "Sugestões da página de origem:\n" + "\n".join(parts) + "\n\n"


def _build_catalog_prompt(exam_types: list, parameter_types: list, units: list) -> str:
    """Build the catalog text for the prompt."""
    lines = [
        "Catálogo já cadastrado no sistema (prefira sempre usar os nomes exatamente como abaixo quando houver correspondência):",
        "",
        "ExamType (tipos de exame): " + ", ".join(exam_types) if exam_types else "ExamType: (nenhum cadastrado)",
        "ParameterType (parâmetros): " + ", ".join(parameter_types) if parameter_types else "ParameterType: (nenhum cadastrado)",
        "MeasurementUnit (símbolos): " + ", ".join(units) if units else "MeasurementUnit: (nenhum cadastrado)",
        "",
        "IMPORTANTE - Parâmetros: agrupe no que já existe no catálogo quando for o mesmo analito. Ex.: se no catálogo existir 'Crea', use 'Crea' (e não crie 'Creatinina'); se existir 'ALT', use 'ALT' (e não crie 'TGP' ou 'Alanina aminotransferase'). Abreviações, sinônimos e nomes completos do mesmo parâmetro devem mapear para o nome já cadastrado. Só inclua em new_parameter_types quando não houver nenhum parâmetro equivalente no catálogo.",
        "Para tipos de exame e unidades, mesma lógica: prefira o que já está no catálogo; só adicione em new_exam_types ou new_units se não existir equivalente.",
    ]
    return "\n".join(lines)


PROMPT_EXTRACTION = """
Analise este exame veterinário (PDF ou imagem). Extraia:
1) Parâmetros numéricos de laboratório (bioquímicos, gasométricos, hemograma, medidas de ultrassom etc.).
2) Se for exame de imagem (ultrassom, raio-x etc.): para cada órgão/estrutura avaliada, extraia o nome do órgão e a descrição/achado em texto (ex.: "Rins: Em topografia habitual, contornos definidos...").
3) Impressão diagnóstica ou conclusão do exame, se houver (ex.: seção IMPRESSÃO DIAGNÓSTICA).
4) Data e hora em que o exame foi realizado/coletado, se constar no documento.

{suggestions}

{catalog}

Retorne APENAS um único objeto JSON válido, sem texto antes ou depois, com a seguinte estrutura:

{{
  "exam_type": "nome do tipo de exame (use um nome do catálogo se fizer match, senão um nome descritivo que será cadastrado)",
  "observed_at": "data/hora do exame em ISO 8601 (ex: 2025-03-10T14:00:00) ou null se não identificável no documento",
  "observed_at_found_in_document": true ou false (true se você encontrou data/hora de realização ou coleta no próprio documento; false se usou apenas a sugestão da página ou não encontrou)",
  "new_exam_types": ["lista de nomes de tipos de exame que não existem no catálogo e devem ser cadastrados"],
  "new_parameter_types": ["lista de nomes de parâmetros que não existem no catálogo e devem ser cadastrados"],
  "new_units": [{{ "symbol": "símbolo", "description": "descrição opcional" }}],
  "diagnostic_impression": "texto completo da impressão diagnóstica / conclusão do exame (ex.: 'IMPRESSÃO DIAGNÓSTICA: • Achado 1. • Achado 2.'). Vazio se não houver.",
  "organ_findings": [
    {{ "organ": "Nome do órgão ou estrutura (ex.: Rins, Vesícula urinária)", "description": "Descrição ou achado para esse órgão, texto completo" }}
  ],
  "parameters": [
    {{
      "parameter_type": "nome do parâmetro (do catálogo ou novo)",
      "unit": "símbolo da unidade (do catálogo ou novo)",
      "measured_value": "valor medido (string)",
      "reference_range": "intervalo de referência ou vazio",
      "raw_parameter_name": "nome exatamente como no laudo (opcional)",
      "raw_unit": "unidade exatamente como no laudo (opcional)"
    }}
  ]
}}

Regras:
- Para cada parâmetro numérico no laudo, preencha um item em parameters.
- Em exames de imagem (ultrassom etc.), preencha organ_findings: um item por órgão/estrutura, com organ (nome) e description (texto do achado).
- diagnostic_impression: copie a seção de conclusão/impressão diagnóstica do laudo, se existir.
- exam_type: use a sugestão da página quando fizer sentido (pode ser um dos itens se a label tiver mais de um, ex.: "Hemograma + Bioquímico" → use "Bioquímico" se o arquivo for só isso); ignore se não se aplicar (ex.: label "Outros").
- observed_at: use a data/hora que constar no documento; se não encontrar, use a sugestão de data/hora da página se fornecida. observed_at_found_in_document: true apenas se você encontrou data/hora no próprio documento.
- Parâmetros: SEMPRE que o laudo mencionar um analito que já existe no catálogo (mesmo com outro nome ou abreviatura), use o nome exato do catálogo em parameter_type e NÃO inclua em new_parameter_types. Ex.: catálogo tem "Crea" → use "Crea" para Creatinina; catálogo tem "Fósforo" → use "Fósforo" para P. Só crie novo (new_parameter_types) quando não houver equivalente.
- Unidades e tipos de exame: mesma regra — prefira o nome exato do catálogo; só adicione em new_units/new_exam_types se não houver equivalente.
- Retorne somente o JSON, sem markdown e sem explicações.
"""


def _get_genai_client():
    api_key = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não configurada no ambiente.")
    return genai.Client(api_key=api_key)


def _get_catalog_for_user(user):
    """Return list of names/symbols for ExamType, ParameterType, MeasurementUnit."""
    exam_types = list(ExamType.objects.values_list("name", flat=True))
    parameter_types = list(ParameterType.objects.values_list("name", flat=True))
    units = list(MeasurementUnit.objects.values_list("symbol", flat=True))
    return exam_types, parameter_types, units


def _parse_observed_at(value: Any):
    if not value:
        return timezone.now()
    if hasattr(value, "strip"):
        value = value.strip()
    parsed = parse_datetime(value)
    if parsed:
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed)
        return parsed
    return timezone.now()


def _extract_json_from_text(text: str) -> dict | None:
    """Extract first JSON object from model response."""
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


def process_exam_with_gemini(exam: AnimalExam) -> dict:
    """
    Send exam file to Gemini with catalog, parse JSON, create new types/units
    as needed, then create ExtractedExam and ExamParameterResult.
    """
    if not exam.file:
        return {"success": False, "detail": "Exame sem arquivo anexado."}

    path = getattr(exam.file, "path", None)
    if not path or not os.path.isfile(path):
        return {"success": False, "detail": "Arquivo do exame não encontrado no disco."}

    client = _get_genai_client()
    exam_types, parameter_types, units = _get_catalog_for_user(exam.animal.guardian)
    catalog = _build_catalog_prompt(exam_types, parameter_types, units)
    suggestions = _build_suggestions_prompt(exam)
    prompt = PROMPT_EXTRACTION.format(catalog=catalog, suggestions=suggestions)

    # Gemini requires mime_type in config when it cannot infer from path
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

    # Create new entities
    for name in data.get("new_exam_types") or []:
        if name and isinstance(name, str):
            ExamType.objects.get_or_create(name=name.strip())

    for name in data.get("new_parameter_types") or []:
        if name and isinstance(name, str):
            ParameterType.objects.get_or_create(name=name.strip())

    for item in data.get("new_units") or []:
        if isinstance(item, dict) and item.get("symbol"):
            MeasurementUnit.objects.get_or_create(
                symbol=item["symbol"].strip(),
                defaults={"description": (item.get("description") or "").strip() or None},
            )

    exam_type_name = (data.get("exam_type") or "").strip()
    exam_type = None
    if exam_type_name:
        exam_type, _ = ExamType.objects.get_or_create(name=exam_type_name)

    raw_observed = data.get("observed_at")
    if raw_observed and str(raw_observed).strip():
        observed_at = _parse_observed_at(raw_observed)
    elif exam.source_observed_at:
        observed_at = exam.source_observed_at
    else:
        observed_at = timezone.now()

    observed_at_found = data.get("observed_at_found_in_document")
    if not isinstance(observed_at_found, bool):
        observed_at_found = None

    observations_text = (data.get("diagnostic_impression") or "").strip() or None
    extracted = ExtractedExam.objects.create(
        animal=exam.animal,
        source_file=exam,
        exam_type=exam_type,
        observed_at=observed_at,
        observed_at_found_in_document=observed_at_found,
        observations=observations_text,
        gemini_prompt_tokens=prompt_tokens,
        gemini_completion_tokens=completion_tokens,
        gemini_total_tokens=total_tokens,
    )

    for idx, item in enumerate(data.get("organ_findings") or []):
        if not isinstance(item, dict):
            continue
        organ = (item.get("organ") or "").strip()
        description = (item.get("description") or "").strip()
        if organ and description:
            ExamOrganFinding.objects.create(
                exam=extracted,
                organ_name=organ[:200],
                description=description,
                order=idx,
            )

    created_params = 0
    for p in data.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        param_name = (p.get("parameter_type") or p.get("nome") or "").strip()
        if not param_name:
            continue
        param_type, _ = ParameterType.objects.get_or_create(name=param_name)
        unit_symbol = (p.get("unit") or p.get("unidade") or "").strip()
        unit = None
        if unit_symbol:
            unit, _ = MeasurementUnit.objects.get_or_create(
                symbol=unit_symbol,
                defaults={"description": None},
            )
        measured = (p.get("measured_value") or p.get("valor") or "").strip() or "—"
        ref_range = (p.get("reference_range") or p.get("intervalo_referencia") or "").strip() or None
        raw_name = (p.get("raw_parameter_name") or "").strip() or None
        raw_unit = (p.get("raw_unit") or "").strip() or None
        _, created = ExamParameterResult.objects.update_or_create(
            exam=extracted,
            parameter_type=param_type,
            defaults={
                "unit": unit,
                "measured_value": measured[:120],
                "reference_range": ref_range[:120] if ref_range else None,
                "raw_parameter_name": raw_name[:120] if raw_name else None,
                "raw_unit": raw_unit[:40] if raw_unit else None,
            },
        )
        if created:
            created_params += 1

    return {
        "success": True,
        "detail": "Exame processado e extração salva.",
        "extracted_exam_id": extracted.id,
        "parameters_created": created_params,
        "exam_type": exam_type.name if exam_type else None,
        "gemini_prompt_tokens": prompt_tokens,
        "gemini_completion_tokens": completion_tokens,
        "gemini_total_tokens": total_tokens,
    }


def process_first_downloaded_exam(user):
    """
    Get the first AnimalExam with file that has not been processed yet (no ExtractedExam
    linked to it), run Gemini extraction, and persist results.
    """
    first = (
        AnimalExam.objects.filter(animal__guardian=user)
        .exclude(file="")
        .annotate(extracted_count=Count("extracted_exams"))
        .filter(extracted_count=0)
        .order_by("id")
        .first()
    )
    if not first:
        return {"success": False, "detail": "Nenhum exame pendente de processamento (todos já processados ou sem arquivo)."}
    return process_exam_with_gemini(first)
