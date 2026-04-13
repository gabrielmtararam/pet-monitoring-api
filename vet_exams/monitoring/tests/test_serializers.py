import pytest
from decimal import Decimal
from django.utils import timezone
from model_bakery import baker
from vet_exams.monitoring.serializers import (
    WaterWeightLogSerializer,
    FoodWeightLogSerializer
)

@pytest.mark.django_db
class TestMonitoringSerializers:
    def test_water_weight_log_serializer_valid(self, animal, rf):
        bowl = baker.make('monitoring.WaterBowl', animal=animal)
        data = {
            'bowl': bowl.id,
            'weight': '450.50',
            'entry_type': 'reading',
            'observed_at': timezone.now().isoformat()
        }
        request = rf.post('/')
        request.user = animal.guardian
        serializer = WaterWeightLogSerializer(data=data, context={'request': request})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data['weight'] == Decimal('450.50')

    def test_food_weight_log_serializer_valid(self, animal, rf):
        data = {
            'animal': animal.id,
            'weight': '120.00',
            'entry_type': 'reading',
            'observed_at': timezone.now().isoformat()
        }
        request = rf.post('/')
        request.user = animal.guardian
        serializer = FoodWeightLogSerializer(data=data, context={'request': request})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data['weight'] == Decimal('120.00')

    def test_water_weight_log_negative_weight_invalid(self, animal, rf):
        bowl = baker.make('monitoring.WaterBowl', animal=animal)
        data = {
            'bowl': bowl.id,
            'weight': '-10.00',
            'entry_type': 'reading',
            'observed_at': timezone.now().isoformat()
        }
        request = rf.post('/')
        request.user = animal.guardian
        serializer = WaterWeightLogSerializer(data=data, context={'request': request})
        assert serializer.is_valid()
