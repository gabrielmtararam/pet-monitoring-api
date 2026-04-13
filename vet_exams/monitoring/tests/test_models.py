import pytest
from decimal import Decimal
from django.utils import timezone
from model_bakery import baker
from vet_exams.monitoring.models import (
    WaterBowl, WaterWeightLog, DailyWaterConsumption,
    FoodWeightLog, DailyFoodConsumption,
    recalculate_daily_water_consumption_for_log,
    recalculate_daily_food_consumption_for_log
)

@pytest.mark.django_db
class TestWaterConsumptionRecalculation:
    def test_recalculate_water_consumption_basic(self, animal):
        bowl = baker.make(WaterBowl, animal=animal, is_reference=False)
        now = timezone.now()
        
        # Initial reading
        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        # Second reading (consumed 50g)
        log2 = baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('450.00'), entry_type='reading', observed_at=now + timezone.timedelta(hours=1))
        
        recalculate_daily_water_consumption_for_log(log2)
        
        consumption = DailyWaterConsumption.objects.get(animal=animal, date=now.date())
        assert consumption.gross_consumption == Decimal('50.00')
        assert consumption.net_consumption == Decimal('50.00')

    def test_recalculate_water_with_evaporation(self, animal):
        bowl = baker.make(WaterBowl, animal=animal, is_reference=False)
        ref_bowl = baker.make(WaterBowl, animal=animal, is_reference=True)
        now = timezone.now()
        
        # Consumption bowl: 500 -> 450 (50g consumed)
        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('450.00'), entry_type='reading', observed_at=now + timezone.timedelta(hours=1))
        
        # Reference bowl: 500 -> 490 (10g evaporated)
        baker.make(WaterWeightLog, bowl=ref_bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        log_ref = baker.make(WaterWeightLog, bowl=ref_bowl, weight=Decimal('490.00'), entry_type='reading', observed_at=now + timezone.timedelta(hours=1))
        
        recalculate_daily_water_consumption_for_log(log_ref)
        
        consumption = DailyWaterConsumption.objects.get(animal=animal, date=now.date())
        assert consumption.gross_consumption == Decimal('50.00')
        assert consumption.evaporation == Decimal('10.00')
        assert consumption.net_consumption == Decimal('40.00')

@pytest.mark.django_db
class TestFoodConsumptionRecalculation:
    def test_recalculate_food_consumption_basic(self, animal):
        now = timezone.now()
        
        # Initial reading
        baker.make(FoodWeightLog, animal=animal, weight=Decimal('200.00'), entry_type='reading', observed_at=now)
        # Second reading (consumed 30g)
        log2 = baker.make(FoodWeightLog, animal=animal, weight=Decimal('170.00'), entry_type='reading', observed_at=now + timezone.timedelta(hours=1))
        
        recalculate_daily_food_consumption_for_log(log2)
        
        consumption = DailyFoodConsumption.objects.get(animal=animal, date=now.date())
        assert consumption.total_consumption == Decimal('30.00')

    def test_recalculate_food_with_refill(self, animal):
        now = timezone.now()
        
        # Reading 1
        baker.make(FoodWeightLog, animal=animal, weight=Decimal('100.00'), entry_type='reading', observed_at=now)
        # Refill (now has 300g)
        baker.make(FoodWeightLog, animal=animal, weight=Decimal('300.00'), entry_type='refill', observed_at=now + timezone.timedelta(minutes=30))
        # Reading 2 (consumed 50g)
        log2 = baker.make(FoodWeightLog, animal=animal, weight=Decimal('250.00'), entry_type='reading', observed_at=now + timezone.timedelta(hours=1))
        
        recalculate_daily_food_consumption_for_log(log2)
        
        consumption = DailyFoodConsumption.objects.get(animal=animal, date=now.date())
        # The logic in recalculate_daily_food_consumption_for_log skips refills in zip(logs_list, logs_list[1:])
        # If curr is refill, it continues. If prev was refill, it calculates delta.
        # Let's verify this logic.
        assert consumption.total_consumption == Decimal('50.00')
