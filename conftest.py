import pytest
from model_bakery import baker
from vet_exams.users.models import BaseUser as User
from vet_exams.animals.models import Animal
import pgcrypto

baker.generators.add('pgcrypto.fields.EncryptedEmailField', 'model_bakery.random_gen.gen_email')
baker.generators.add('pgcrypto.fields.EncryptedCharField', 'model_bakery.random_gen.gen_string')
baker.generators.add('pgcrypto.fields.EncryptedTextField', 'model_bakery.random_gen.gen_text')

@pytest.fixture
def user(db):
    return baker.make(User)

@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()

@pytest.fixture
def auth_client(user, api_client):
    api_client.force_authenticate(user=user)
    return api_client

@pytest.fixture
def animal(user):
    return baker.make(Animal, guardian=user)
