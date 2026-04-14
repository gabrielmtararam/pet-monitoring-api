import pytest
from django.utils import timezone
from vet_exams.monitoring.exams_extraction import (
    _build_suggestions_prompt,
    _build_catalog_prompt,
    _parse_observed_at,
    _extract_json_from_text
)
from model_bakery import baker
from vet_exams.monitoring.models import AnimalExam

@pytest.mark.django_db
class TestExtractionUtils:
    def test_build_suggestions_prompt(self, user):
        animal = baker.make('animals.Animal', guardian=user)
        exam = AnimalExam.objects.create(
            animal=animal,
            source_exam_type_label="Hemograma",
            source_observed_at=timezone.now()
        )
        prompt = _build_suggestions_prompt(exam)
        assert "Hemograma" in prompt
        assert "Sugestões da página de origem" in prompt

    def test_build_catalog_prompt(self):
        prompt = _build_catalog_prompt(["Hemograma"], ["Crea"], ["mg/dL"])
        assert "Hemograma" in prompt
        assert "Crea" in prompt
        assert "mg/dL" in prompt

    def test_parse_observed_at(self):
        now = timezone.now()
        assert _parse_observed_at(None).date() == now.date()
        assert _parse_observed_at("2025-03-10T14:00:00").year == 2025

    def test_extract_json_from_text(self):
        text = "Aqui está o json: {\"key\": \"value\"} fim."
        data = _extract_json_from_text(text)
        assert data == {"key": "value"}
        assert _extract_json_from_text("no json here") is None
