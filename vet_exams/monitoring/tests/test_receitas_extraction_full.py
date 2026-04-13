import pytest
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from vet_exams.monitoring.models import Receita, Animal, Remedio, IndicacaoMedicamento
from vet_exams.monitoring.receitas_extraction import process_receita_with_gemini
from model_bakery import baker

@pytest.mark.django_db
class TestReceitasExtractionFull:
    @patch('vet_exams.monitoring.receitas_extraction._get_genai_client')
    @patch('os.path.isfile')
    def test_process_receita_with_gemini_success(self, mock_isfile, mock_get_client, user):
        mock_isfile.return_value = True
        animal = baker.make(Animal, guardian=user)
        # Both data and source_identifier are likely required by schema or migrations
        from datetime import date
        receita = Receita.objects.create(
            animal=animal, 
            source_identifier="ID123", 
            data=date.today()
        )
        receita.file.save("receita.pdf", ContentFile(b"dummy pdf"))
        
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock upload
        mock_upload = MagicMock()
        mock_upload.state.name = "ACTIVE"
        mock_upload.uri = "gs://bucket/receita.pdf"
        mock_upload.mime_type = "application/pdf"
        mock_client.files.upload.return_value = mock_upload
        
        # Mock response
        mock_response = MagicMock()
        mock_response.text = """
        {
          "data_receita": "2025-03-10",
          "new_remedios": [
            { "name": "Novalgina", "principio_ativo": "Dipirona" }
          ],
          "indicacoes": [
            {
              "remedio": "Novalgina",
              "forma_apresentacao": "gotas",
              "medida_apresentacao": "500mg/ml",
              "dosagem": "10 gotas",
              "frequencia": "a cada 8 horas",
              "periodo": "por 3 dias"
            }
          ]
        }
        """
        mock_response.usage_metadata = {"total_token_count": 50}
        mock_client.models.generate_content.return_value = mock_response
        
        result = process_receita_with_gemini(receita)
        
        assert result['success'] is True
        assert Remedio.objects.filter(name="Novalgina").exists()
        assert IndicacaoMedicamento.objects.filter(receita=receita).count() == 1

    def test_process_receita_no_file(self, user):
        from datetime import date
        animal = baker.make(Animal, guardian=user)
        receita = Receita.objects.create(
            animal=animal, 
            source_identifier="ID456", 
            data=date.today()
        )
        result = process_receita_with_gemini(receita)
        assert result['success'] is False
        assert "sem arquivo" in result['detail']
