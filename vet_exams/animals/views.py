from rest_framework import viewsets, permissions

from vet_exams.animals.models import Animal
from vet_exams.animals.serializers import AnimalSerializer


class AnimalViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnimalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Animal.objects.filter(guardian=user)

