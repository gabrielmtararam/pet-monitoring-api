import pytest
from django.urls import reverse
from rest_framework import status
from model_bakery import baker
from vet_exams.animals.models import Animal

@pytest.mark.django_db
class TestAnimalViews:
    def test_animal_list_auth(self, auth_client, user):
        # Create an animal for the authenticated user
        animal1 = baker.make(Animal, guardian=user)
        # Create an animal for another user
        another_user = baker.make('users.BaseUser')
        baker.make(Animal, guardian=another_user)
        
        url = reverse('animal-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        
        # Should only see their own animal
        # Note: Check if pagination is enabled (default is 10)
        assert 'results' in response.data
        assert response.data['count'] == 1
        assert response.data['results'][0]['id'] == animal1.id

    def test_animal_list_unauth(self, api_client):
        url = reverse('animal-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
