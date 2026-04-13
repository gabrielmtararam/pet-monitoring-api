import pytest
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from vet_exams.monitoring.models import AnimalExam, Animal, ExtractedExam
from vet_exams.monitoring.exams_extraction import process_exam_with_gemini
from model_bakery import baker

@pytest.mark.django_db
class TestExamsExtractionFull:
    @patch('vet_exams.monitoring.exams_extraction._get_genai_client')
    @patch('os.path.isfile')
    def test_process_exam_with_gemini_success(self, mock_isfile, mock_get_client, user):
        mock_isfile.return_value = True
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="test.pdf")
        exam.file.save("test.pdf", ContentFile(b"dummy pdf"))
        
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock upload
        mock_upload = MagicMock()
        mock_upload.state.name = "ACTIVE"
        mock_upload.uri = "gs://bucket/test.pdf"
        mock_upload.mime_type = "application/pdf"
        mock_client.files.upload.return_value = mock_upload
        
        # Mock response
        mock_response = MagicMock()
        mock_response.text = """
        {
          "exam_type": "Hemograma",
          "observed_at": "2025-03-10T14:00:00",
          "observed_at_found_in_document": true,
          "new_exam_types": [],
          "new_parameter_types": ["Glicose"],
          "new_units": [{"symbol": "mg/dL", "description": "miligramas por decilitro"}],
          "diagnostic_impression": "Normal",
          "organ_findings": [],
          "parameters": [
            {"parameter_type": "Glicose", "unit": "mg/dL", "measured_value": "100", "reference_range": "70-110"}
          ]
        }
        """
        mock_response.usage_metadata = {"total_token_count": 100}
        mock_client.models.generate_content.return_value = mock_response
        
        result = process_exam_with_gemini(exam)
        
        assert result['success'] is True
        assert ExtractedExam.objects.count() == 1
        extracted = ExtractedExam.objects.first()
        assert extracted.exam_type.name == "Hemograma"
        assert extracted.parameter_results.count() == 1
        assert extracted.parameter_results.first().parameter_type.name == "Glicose"

    def test_process_exam_no_file(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal)
        result = process_exam_with_gemini(exam)
        assert result['success'] is False
        assert "sem arquivo" in result['detail']
