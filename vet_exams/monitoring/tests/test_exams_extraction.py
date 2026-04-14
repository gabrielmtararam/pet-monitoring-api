"""
Comprehensive tests for exams_extraction.py to maximize coverage.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from django.utils import timezone
from types import SimpleNamespace

import vet_exams.monitoring.exams_extraction as ee
from vet_exams.monitoring.exams_extraction import (
    _build_suggestions_prompt,
    _build_catalog_prompt,
    _get_genai_client,
    _get_catalog_for_user,
    _parse_observed_at,
    _extract_json_from_text,
    process_exam_with_gemini,
    process_first_downloaded_exam,
)
from vet_exams.monitoring.models import (
    Animal, AnimalExam, ExamType, ParameterType, MeasurementUnit, ExtractedExam
)
from model_bakery import baker


@pytest.mark.django_db
class TestExamsExtractionPure:
    # --- Pure function tests ---

    def test_build_suggestions_prompt_empty_exam(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="x.pdf")
        result = _build_suggestions_prompt(exam)
        assert result == ""

    def test_build_suggestions_prompt_with_label_and_date(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(
            animal=animal, file_name="x.pdf",
            source_exam_type_label="Hemograma",
            source_observed_at=timezone.now()
        )
        result = _build_suggestions_prompt(exam)
        assert "Hemograma" in result
        assert "Sugestões" in result

    def test_build_catalog_prompt_with_items(self):
        result = _build_catalog_prompt(["Hemograma"], ["Glicose"], ["mg/dL"])
        assert "Hemograma" in result
        assert "Glicose" in result
        assert "mg/dL" in result

    def test_build_catalog_prompt_empty(self):
        result = _build_catalog_prompt([], [], [])
        assert "nenhum" in result

    def test_extract_json_from_text_valid(self):
        result = _extract_json_from_text('{"k": 1}')
        assert result == {"k": 1}

    def test_extract_json_from_text_with_prefix(self):
        result = _extract_json_from_text('prefix{"k": 1}suffix')
        assert result == {"k": 1}

    def test_extract_json_from_text_empty(self):
        assert _extract_json_from_text("") is None

    def test_extract_json_from_text_no_json(self):
        assert _extract_json_from_text("no json here") is None

    def test_extract_json_from_text_invalid_json(self):
        assert _extract_json_from_text("{not valid}") is None

    def test_parse_observed_at_none(self):
        result = _parse_observed_at(None)
        assert result is not None  # returns timezone.now()

    def test_parse_observed_at_valid_string(self):
        result = _parse_observed_at("2025-01-15T10:30:00")
        assert result.year == 2025

    def test_parse_observed_at_invalid_string(self):
        result = _parse_observed_at("not-a-date")
        assert result is not None  # falls back to now

    def test_get_genai_client_no_key(self):
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("GEMINI_API_KEY", None)
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                _get_genai_client()

    def test_get_catalog_for_user(self, user):
        # Creates some catalog items
        baker.make(ExamType, name="Hemo")
        baker.make(ParameterType, name="Gluc")
        baker.make(MeasurementUnit, symbol="mg")
        exam_types, param_types, units = _get_catalog_for_user(user)
        assert "Hemo" in exam_types
        assert "Gluc" in param_types
        assert "mg" in units

    # --- process_exam_with_gemini tests ---

    def test_process_exam_no_file(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="x.pdf")
        result = process_exam_with_gemini(exam)
        assert result["success"] is False
        assert "sem arquivo" in result["detail"]

    def test_process_exam_file_not_on_disk(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="x.pdf")
        exam.file.name = "nonexistent.pdf"
        result = process_exam_with_gemini(exam)
        assert result["success"] is False

    def test_process_exam_with_gemini_full_success(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="test_extr.pdf")
        exam.file.save("test_extr.pdf", ContentFile(b"pdf content"))

        mock_client = MagicMock()
        uploaded = SimpleNamespace()
        uploaded.uri = "http://mock-uri"
        uploaded.mime_type = "application/pdf"
        uploaded.name = "file1"
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded
        mock_client.files.get.return_value = uploaded

        json_data = {
            "exam_type": "Hemograma",
            "observed_at": "2025-01-15T10:00:00",
            "observed_at_found_in_document": True,
            "new_exam_types": ["Bioquímico"],
            "new_parameter_types": ["Glicose"],
            "new_units": [{"symbol": "mg/dL", "description": "miligrama por decilitro"}],
            "diagnostic_impression": "Resultado normal",
            "organ_findings": [{"organ": "Rins", "description": "Contornos normais"}],
            "parameters": [
                {
                    "parameter_type": "Glicose",
                    "unit": "mg/dL",
                    "measured_value": "85",
                    "reference_range": "70-110",
                    "raw_parameter_name": "GLU",
                    "raw_unit": "mg/dL"
                }
            ],
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(json_data)
        mock_response.usage_metadata = SimpleNamespace(
            total_token_count=100,
            prompt_token_count=60,
            candidates_token_count=40
        )
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(ee, "_get_genai_client", return_value=mock_client):
            with patch.object(ee, "_extract_json_from_text", return_value=json_data):
                result = process_exam_with_gemini(exam)

        assert result["success"] is True
        assert result["parameters_created"] == 1
        assert ExamType.objects.filter(name="Bioquímico").exists()

    def test_process_exam_gemini_returns_no_json(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="test2.pdf")
        exam.file.save("test2.pdf", ContentFile(b"x"))

        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="application/pdf", name="f")
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded
        mock_client.files.get.return_value = uploaded
        mock_response = MagicMock()
        mock_response.text = "no json"
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(ee, "_get_genai_client", return_value=mock_client):
            with patch.object(ee, "_extract_json_from_text", return_value=None):
                result = process_exam_with_gemini(exam)
        assert result["success"] is False

    def test_process_exam_upload_fails(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="test3.pdf")
        exam.file.save("test3.pdf", ContentFile(b"x"))

        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="application/pdf", name="f")
        uploaded.state = SimpleNamespace(name="FAILED")
        mock_client.files.upload.return_value = uploaded

        with patch.object(ee, "_get_genai_client", return_value=mock_client):
            result = process_exam_with_gemini(exam)
        assert result["success"] is False
        assert "Falha no upload" in result["detail"]

    def test_process_first_downloaded_exam_none(self, user):
        result = process_first_downloaded_exam(user)
        assert result["success"] is False

    def test_process_first_downloaded_exam_picks_first(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="first.pdf")
        exam.file.save("first.pdf", ContentFile(b"x"))

        mock_client = MagicMock()
        uploaded = SimpleNamespace(uri="http://u", mime_type="application/pdf", name="f")
        uploaded.state = SimpleNamespace(name="ACTIVE")
        mock_client.files.upload.return_value = uploaded

        good_json = {"exam_type": "Hemo", "parameters": []}
        mock_response = MagicMock()
        mock_response.text = json.dumps(good_json)
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(ee, "process_exam_with_gemini", return_value={"success": True}) as mock_proc:
            result = process_first_downloaded_exam(user)
        assert result["success"] is True
        mock_proc.assert_called_once_with(exam)
