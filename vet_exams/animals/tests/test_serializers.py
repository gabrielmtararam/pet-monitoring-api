import pytest
from vet_exams.animals.serializers import AnimalSerializer
from model_bakery import baker

@pytest.mark.django_db
class TestAnimalSerializer:
    def test_animal_serializer_fields(self):
        animal = baker.make('animals.Animal', name="Buddy", specie="Dog", breed="Labrador", type="cat")
        serializer = AnimalSerializer(instance=animal)
        data = serializer.data
        assert data['name'] == "Buddy"
        assert data['specie'] == "Dog"
        assert data['breed'] == "Labrador"
        assert data['type'] == "cat"
        assert set(data.keys()) == {'id', 'name', 'specie', 'breed', 'type'}
