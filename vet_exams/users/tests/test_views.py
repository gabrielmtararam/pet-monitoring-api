import pytest
from django.urls import reverse
from rest_framework import status
from model_bakery import baker
from vet_exams.users.models import BaseUser
from rest_framework_simplejwt.tokens import RefreshToken

@pytest.mark.django_db
class TestUserViews:
    def test_registration_success(self, api_client):
        url = reverse('register')
        data = {
            'email': 'newuser@example.com',
            'password': 'password123',
            'first_name': 'New',
            'last_name': 'User'
        }
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['email'] == 'newuser@example.com'

    def test_registration_invalid(self, api_client):
        url = reverse('register')
        data = {'email': 'invalid'}
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_success(self, api_client):
        user = BaseUser.objects.create_user(
            email='login@example.com',
            password='password123',
            first_name='Login',
            last_name='User'
        )
        url = reverse('api_login')
        data = {'email': 'login@example.com', 'password': 'password123'}
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'detail' in response.data

    def test_login_invalid_credentials(self, api_client):
        url = reverse('api_login')
        data = {'email': 'wrong@example.com', 'password': 'wrong'}
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_success(self, auth_client, user):
        refresh = RefreshToken.for_user(user)
        url = reverse('api_logout')
        response = auth_client.post(url, {'refresh': str(refresh)})
        assert response.status_code == status.HTTP_200_OK

    def test_logout_invalid_token(self, auth_client, user):
        url = reverse('api_logout')
        response = auth_client.post(url, {'refresh': 'invalid'})
        assert response.status_code == status.HTTP_200_OK # View handles exception and returns 200
