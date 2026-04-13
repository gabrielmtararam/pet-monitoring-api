import pytest
from datetime import date
from vet_exams.monitoring.receitas_extraction import (
    _build_remedios_catalog,
    _parse_data_receita,
    _extract_json_from_text
)
from model_bakery import baker
from vet_exams.monitoring.models import Remedio

@pytest.mark.django_db
class TestReceitasExtractionUtils:
    def test_build_remedios_catalog(self):
        baker.make(Remedio, name="Aspirina", principio_ativo="Ácido acetilsalicílico")
        catalog = _build_remedios_catalog()
        assert "Aspirina" in catalog
        assert "Ácido acetilsalicílico" in catalog

    def test_build_remedios_catalog_empty(self):
        Remedio.objects.all().delete()
        catalog = _build_remedios_catalog()
        assert "nenhum" in catalog

    def test_parse_data_receita(self):
        assert _parse_data_receita("2025-03-10") == date(2025, 3, 10)
        assert _parse_data_receita(None) is None
        assert _parse_data_receita("invalid") is None

    def test_extract_json_from_text(self):
        text = "JSON: {\"key\": \"val\"}"
        assert _extract_json_from_text(text) == {"key": "val"}
