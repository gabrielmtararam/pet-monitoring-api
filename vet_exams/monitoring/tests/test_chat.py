import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework import status
from model_bakery import baker

@pytest.mark.django_db
class TestChatAPIView:
    @patch('vet_exams.monitoring.views._get_genai_client')
    def test_chat_success(self, mock_get_client, auth_client, user):
        # Mocking GenAI client and response
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.text = "Olá! Eu sou o assistente veterinário."
        mock_response.function_calls = []
        mock_client.models.generate_content.return_value = mock_response
        
        url = reverse('monitoring-chat')
        data = {'prompt': 'Olá, como vai?', 'animal_id': 1}
        response = auth_client.post(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['response'] == "Olá! Eu sou o assistente veterinário."

    def test_chat_no_prompt(self, auth_client):
        url = reverse('monitoring-chat')
        response = auth_client.post(url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch('vet_exams.monitoring.views._get_genai_client')
    def test_chat_function_calling(self, mock_get_client, auth_client, user):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # 1. Mock first response with function call
        mock_response = MagicMock()
        mock_response.text = ""
        
        mock_func_call = MagicMock()
        mock_func_call.name = "get_water_consumption"
        mock_func_call.args = {"animal_id": 1, "start_date": "2025-01-01", "end_date": "2025-01-31"}
        
        mock_response.function_calls = [mock_func_call]
        mock_response.candidates = [MagicMock()]
        
        # 2. Mock second response (final answer)
        mock_final_response = MagicMock()
        mock_final_response.text = "O consumo foi de 500g."
        
        mock_client.models.generate_content.side_effect = [mock_response, mock_final_response]
        
        url = reverse('monitoring-chat')
        data = {'prompt': 'Quanto ele bebeu em Janeiro?', 'animal_id': 1}
        response = auth_client.post(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['response'] == "O consumo foi de 500g."
        assert mock_client.models.generate_content.call_count == 2
