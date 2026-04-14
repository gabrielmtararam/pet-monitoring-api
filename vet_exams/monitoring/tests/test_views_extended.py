import pytest
from django.urls import reverse
from rest_framework import status
from model_bakery import baker
from vet_exams.monitoring.models import AnimalExam
from unittest.mock import patch, MagicMock

@pytest.mark.django_db
class TestMonitoringViewsExtended:
    def test_export_no_animal_id(self, auth_client):
        url = reverse('monitoring-export')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['detail'] == 'Parâmetro animal_id é obrigatório.'

    def test_export_invalid_animal_id(self, auth_client):
        url = reverse('monitoring-export') + '?animal_id=abc'
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['detail'] == 'animal_id inválido.'

    def test_export_animal_not_found(self, auth_client, user):
        url = reverse('monitoring-export') + '?animal_id=9999'
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch('vet_exams.monitoring.views.run_login_automation')
    def test_exams_update_api(self, mock_automation, auth_client):
        mock_automation.return_value = {'success': True, 'detail': 'OK'}
        url = reverse('exams-update')
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True

    @patch('vet_exams.monitoring.views.process_first_downloaded_exam')
    def test_exams_process_api(self, mock_process, auth_client):
        mock_process.return_value = {'success': True, 'detail': 'Processed'}
        url = reverse('exams-process')
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
