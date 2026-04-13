import pytest
from django.urls import reverse
from rest_framework import status
from model_bakery import baker
from vet_exams.monitoring.models import WaterBowl, WaterWeightLog

@pytest.mark.django_db
class TestMonitoringViews:
    def test_water_bowl_list_auth(self, auth_client, animal):
        bowl = baker.make(WaterBowl, animal=animal)
        url = reverse('waterbowl-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        # The response is paginated
        assert response.data['count'] == 1
        assert response.data['results'][0]['id'] == bowl.id

    def test_water_bowl_list_unauth(self, api_client):
        url = reverse('waterbowl-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_bulk_create_water_logs(self, auth_client, animal):
        bowl1 = baker.make(WaterBowl, animal=animal)
        bowl2 = baker.make(WaterBowl, animal=animal)
        url = reverse('waterweightlog-bulk-create')
        
        data = {
            'entry_type': 'reading',
            'items': [
                {'bowl': bowl1.id, 'weight': 500},
                {'bowl': bowl2.id, 'weight': 480},
            ]
        }
        
        response = auth_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert WaterWeightLog.objects.filter(bowl__animal=animal).count() == 2

    def test_monitoring_export(self, auth_client, animal):
        # Create at least one bowl so it doesn't return 404
        baker.make(WaterBowl, animal=animal)
        url = reverse('monitoring-export')
        response = auth_client.get(url, {'animal_id': animal.id})
        assert response.status_code == status.HTTP_200_OK
        assert 'bowls' in response.data
        assert 'water_logs' in response.data
        assert response.data['animal_id'] == animal.id

    def test_monitoring_export_missing_animal(self, auth_client):
        url = reverse('monitoring-export')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
