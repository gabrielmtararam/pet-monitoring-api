"""
Fixed tests for receitas_extraction.py — correct Receita field names.
"""
import pytest
import json
from datetime import date as date_cls
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from django.utils import timezone
from types import SimpleNamespace

import vet_exams.monitoring.receitas_extraction as re_mod
from vet_exams.monitoring.receitas_extraction import (
    _build_remedios_catalog,
    _get_genai_client,
    _extract_json_from_text,
    _parse_data_receita,
    process_receita_with_gemini,
    process_first_receita,
)
from vet_exams.monitoring.models import Animal, Receita, Remedio, IndicacaoMedicamento
from model_bakery import baker


def make_receita(animal, source_identifier, data=None):
    """Helper to create correctReceita objects."""
    return Receita.objects.create(
        animal=animal,
        source_identifier=source_identifier,
        data=data or date_cls(2025, 1, 1),
    )


@pytest.mark.django_db
class TestReceitasExtractionFull:
    def test_build_remedios_catalog_empty(self):
        Remedio.objects.all().delete()
        result = _build_remedios_catalog()
        assert "nenhum" in result

    def test_build_remedios_catalog_with_items(self):
        baker.make(Remedio, name="Amoxicilina", principio_ativo="Amoxicilina triidratada")
        baker.make(Remedio, name="Dipirona", principio_ativo=None)
        result = _build_remedios_catalog()
        assert "Amoxicilina" in result
        assert "Dipirona" in result

    def test_extract_json_from_text_valid(self):
        assert _extract_json_from_text('{"k": 1}') == {"k": 1}

    def test_extract_json_from_text_empty(self):
        assert _extract_json_from_text("") is None

    def test_extract_json_from_text_no_braces(self):
        assert _extract_json_from_text("no braces") is None

    def test_extract_json_from_text_invalid(self):
        assert _extract_json_from_text("{bad") is None

    def test_parse_data_receita_valid(self):
        result = _parse_data_receita("2025-03-15")
        assert result.year == 2025
        assert result.month == 3
        assert result.day == 15

    def test_parse_data_receita_none(self):
        assert _parse_data_receita(None) is None

    def test_parse_data_receita_empty_string(self):
        assert _parse_data_receita("") is None

    def test_parse_data_receita_invalid(self):
        assert _parse_data_receita("not-a-date") is None

    def test_get_genai_client_no_key(self):
        import os
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                _get_genai_client()

    def test_process_receita_no_file(self, user):
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "s1")
        result = process_receita_with_gemini(receita)
        assert result["success"] is False
        assert "sem arquivo" in result["detail"]

    def test_process_receita_file_missing_on_disk(self, user):
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "s2")
        receita.file.name = "nonexistent.pdf"
        result = process_receita_with_gemini(receita)
        assert result["success"] is False
        assert "não encontrado" in result["detail"]

    def test_process_receita_full_success(self, user):
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "s3")
        receita.file.save("r3.pdf", ContentFile(b"pdf"))

        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="application/pdf", name="f")
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded

        json_data = {
            "data_receita": "2025-03-10",
            "new_remedios": [
                {"name": "Metronidazol", "principio_ativo": "Metronidazol 500mg"}
            ],
            "indicacoes": [
                {
                    "remedio": "Metronidazol",
                    "forma_apresentacao": "comprimido",
                    "medida_apresentacao": "500mg",
                    "dosagem": "1 comprimido",
                    "frequencia": "2x ao dia",
                    "periodo": "7 dias",
                }
            ],
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(json_data)
        # Use dict so usage.get() works properly
        mock_response.usage_metadata = {
            "prompt_token_count": 30,
            "candidates_token_count": 20,
            "total_token_count": 50,
        }
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(re_mod, "_get_genai_client", return_value=mock_client):
            with patch.object(re_mod, "_extract_json_from_text", return_value=json_data):
                result = process_receita_with_gemini(receita)

        assert result["success"] is True
        assert result["indicacoes_created"] == 1
        assert Remedio.objects.filter(name="Metronidazol").exists()

    def test_process_receita_upload_failed(self, user):
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "s4")
        receita.file.save("r4.pdf", ContentFile(b"pdf"))

        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="application/pdf", name="f")
        uploaded.state = SimpleNamespace(name="FAILED")
        mock_client.files.upload.return_value = uploaded

        with patch.object(re_mod, "_get_genai_client", return_value=mock_client):
            result = process_receita_with_gemini(receita)
        assert result["success"] is False
        assert "upload" in result["detail"].lower()

    def test_process_receita_no_json_response(self, user):
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "s5")
        receita.file.save("r5.pdf", ContentFile(b"pdf"))

        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="application/pdf", name="f")
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded
        mock_response = MagicMock()
        mock_response.text = "no valid json"
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(re_mod, "_get_genai_client", return_value=mock_client):
            with patch.object(re_mod, "_extract_json_from_text", return_value=None):
                result = process_receita_with_gemini(receita)
        assert result["success"] is False
        assert "JSON" in result["detail"]

    def test_process_first_receita_none_pending(self, user):
        result = process_first_receita(user)
        assert result["success"] is False

    def test_process_first_receita_processes_first(self, user):
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "pfr1")
        receita.file.save("pfr.pdf", ContentFile(b"pdf"))

        json_data = {"data_receita": None, "new_remedios": [], "indicacoes": []}
        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="application/pdf", name="f")
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded
        mock_response = MagicMock()
        mock_response.text = json.dumps(json_data)
        mock_response.usage_metadata = {"prompt_token_count": 10, "total_token_count": 10}
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(re_mod, "_get_genai_client", return_value=mock_client):
            with patch.object(re_mod, "_extract_json_from_text", return_value=json_data):
                result = process_first_receita(user)
        assert result["success"] is True

    def test_process_receita_with_jpeg_file(self, user):
        """Test MIME type for .jpg files."""
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "s6")
        receita.file.save("r6.jpg", ContentFile(b"jpg"))

        json_data = {"data_receita": None, "new_remedios": [], "indicacoes": []}
        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="image/jpeg", name="f")
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded
        mock_response = MagicMock()
        mock_response.text = json.dumps(json_data)
        mock_response.usage_metadata = {"total_token_count": 5}
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(re_mod, "_get_genai_client", return_value=mock_client):
            with patch.object(re_mod, "_extract_json_from_text", return_value=json_data):
                result = process_receita_with_gemini(receita)
        assert result["success"] is True

    def test_process_receita_with_png_file(self, user):
        """Test MIME type for .png files."""
        animal = baker.make(Animal, guardian=user)
        receita = make_receita(animal, "s7")
        receita.file.save("r7.png", ContentFile(b"png"))

        json_data = {"data_receita": None, "new_remedios": [], "indicacoes": []}
        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="image/png", name="f")
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded
        mock_response = MagicMock()
        mock_response.text = json.dumps(json_data)
        mock_response.usage_metadata = {"total_token_count": 5}
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(re_mod, "_get_genai_client", return_value=mock_client):
            with patch.object(re_mod, "_extract_json_from_text", return_value=json_data):
                result = process_receita_with_gemini(receita)
        assert result["success"] is True
