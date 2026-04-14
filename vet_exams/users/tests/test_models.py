import pytest
from model_bakery import baker
from vet_exams.users.models import BaseUser

@pytest.mark.django_db
class TestUserModel:
    def test_user_creation(self):
        user = baker.make(BaseUser, first_name="John", last_name="Doe", email="john@example.com")
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.email == "john@example.com"
        assert str(user) == "john@example.com"

    def test_create_user_manager(self):
        user = BaseUser.objects.create_user(
            email="test@example.com",
            password="password123",
            first_name="Test",
            last_name="User"
        )
        assert user.email == "test@example.com"
        assert user.check_password("password123")
        assert not user.is_staff
        assert not user.is_superuser

    def test_create_superuser(self):
        user = BaseUser.objects.create_superuser(
            email="admin@example.com",
            password="password123",
            first_name="Admin",
            last_name="User"
        )
        assert user.email == "admin@example.com"
        assert user.is_staff
        assert user.is_superuser
