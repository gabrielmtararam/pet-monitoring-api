from rest_framework import serializers

from vet_exams.animals.models import Animal


class AnimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Animal
        fields = ('id', 'name', 'specie', 'breed', 'type')

