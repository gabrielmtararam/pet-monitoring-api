import pytest
from model_bakery import baker
from vet_exams.animals.models import Animal, Cat, Bird

@pytest.mark.django_db
class TestAnimalModels:
    def test_animal_creation(self, user):
        animal = baker.make(Animal, guardian=user, name="Rex")
        assert animal.name == "Rex"
        assert str(animal) == f"Rex - {user.first_name} ({user.last_name})"

    def test_cat_creation(self, user):
        cat = baker.make(Cat, guardian=user, name="Mimi", fur_color="white")
        assert cat.name == "Mimi"
        assert cat.fur_color == "white"
        assert isinstance(cat, Animal)

    def test_bird_creation(self, user):
        bird = baker.make(Bird, guardian=user, name="Piu", feather_color="black")
        assert bird.name == "Piu"
        assert bird.feather_color == "black"
        assert isinstance(bird, Animal)
