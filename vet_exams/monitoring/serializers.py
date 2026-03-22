from rest_framework import serializers

from django.utils import timezone

from vet_exams.monitoring.models import (
    AnimalDiaryEntry,
    DailyFoodConsumption,
    DailyWaterConsumption,
    FoodBrand,
    FoodType,
    FoodWeightLog,
    WaterBowl,
    WaterWeightLog,
    recalculate_daily_food_consumption_for_log,
    recalculate_daily_water_consumption_for_log,
)


class FoodBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodBrand
        fields = ('id', 'name')


class FoodTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodType
        fields = ('id', 'name')


class WaterBowlSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterBowl
        fields = ('id', 'animal', 'name', 'description', 'is_reference')

class WaterWeightLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterWeightLog
        fields = ('id', 'bowl', 'weight', 'entry_type', 'observed_at')

    def validate_bowl(self, value):
        user = self.context['request'].user
        if value.animal.guardian != user:
            raise serializers.ValidationError("Você não tem permissão para adicionar logs a este pote.")
        return value

    def create(self, validated_data):
        # Se o cliente não enviar observed_at, usar data/hora atual
        if not validated_data.get('observed_at'):
            validated_data['observed_at'] = timezone.now()
        instance = super().create(validated_data)
        recalculate_daily_water_consumption_for_log(instance)
        return instance


class FoodWeightLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodWeightLog
        fields = ('id', 'animal', 'brand', 'type', 'weight', 'entry_type', 'observed_at')

    def validate_animal(self, value):
        user = self.context['request'].user
        if value.guardian != user:
            raise serializers.ValidationError("Você não tem permissão para adicionar logs a este animal.")
        return value

    def create(self, validated_data):
        # Se o cliente não enviar observed_at, usar data/hora atual
        if not validated_data.get('observed_at'):
            validated_data['observed_at'] = timezone.now()
        instance = super().create(validated_data)
        recalculate_daily_food_consumption_for_log(instance)
        return instance


class AnimalDiaryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AnimalDiaryEntry
        fields = ('id', 'animal', 'text', 'observed_at')

    def validate_animal(self, value):
        user = self.context['request'].user
        if value.guardian != user:
            raise serializers.ValidationError("Você não tem permissão para adicionar diário a este animal.")
        return value

    def create(self, validated_data):
        if not validated_data.get('observed_at'):
            validated_data['observed_at'] = timezone.now()
        return super().create(validated_data)


class DailyWaterConsumptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyWaterConsumption
        fields = (
            'id',
            'animal',
            'date',
            'gross_consumption',
            'evaporation',
            'net_consumption',
            'negative_periods',
            'missing_readings',
            'created_at',
        )


class DailyFoodConsumptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyFoodConsumption
        fields = (
            'id',
            'animal',
            'date',
            'total_consumption',
            'negative_periods',
            'missing_readings',
            'created_at',
        )