"""
Fixed tests for models.py — correct field names and timezone-aware queries.
"""
import pytest
from decimal import Decimal
from datetime import date as date_cls
from django.utils import timezone
from model_bakery import baker
from vet_exams.monitoring.models import (
    WaterBowl, WaterWeightLog, DailyWaterConsumption,
    FoodWeightLog, DailyFoodConsumption, Animal,
    recalculate_daily_water_consumption_for_log,
    recalculate_daily_food_consumption_for_log,
    AnimalExam, Receita, ExamType, ParameterType, MeasurementUnit,
    ExtractedExam, ExamOrganFinding, Remedio, IndicacaoMedicamento,
    FoodBrand, FoodType, AnimalDiaryEntry
)


@pytest.fixture
def animal_with_user(user):
    Animal.objects.filter(guardian=user).delete()
    return Animal.objects.create(guardian=user, name="TestAnimal")


@pytest.mark.django_db
class TestWaterConsumptionRecalculation:
    def test_recalculate_water_consumption_basic(self, animal_with_user):
        animal = animal_with_user
        bowl = baker.make(WaterBowl, animal=animal, is_reference=False)
        # Use a fixed time (noon) to avoid midnight-crossing in UTC during the one-hour window
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())

        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        log2 = baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('450.00'), entry_type='reading',
                          observed_at=now + timezone.timedelta(hours=1))

        recalculate_daily_water_consumption_for_log(log2)

        # Use timezone.localdate() as the model does
        log_date = timezone.localdate(log2.observed_at)
        consumption = DailyWaterConsumption.objects.get(animal=animal, date=log_date)
        assert consumption.gross_consumption == Decimal('50.00')
        assert consumption.net_consumption == Decimal('50.00')

    def test_recalculate_water_with_evaporation(self, animal_with_user):
        animal = animal_with_user
        bowl = baker.make(WaterBowl, animal=animal, is_reference=False)
        ref_bowl = baker.make(WaterBowl, animal=animal, is_reference=True)
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())

        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('450.00'), entry_type='reading',
                   observed_at=now + timezone.timedelta(hours=1))
        baker.make(WaterWeightLog, bowl=ref_bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        log_ref = baker.make(WaterWeightLog, bowl=ref_bowl, weight=Decimal('490.00'), entry_type='reading',
                              observed_at=now + timezone.timedelta(hours=1))

        recalculate_daily_water_consumption_for_log(log_ref)

        log_date = timezone.localdate(log_ref.observed_at)
        consumption = DailyWaterConsumption.objects.get(animal=animal, date=log_date)
        assert consumption.gross_consumption == Decimal('50.00')
        assert consumption.evaporation == Decimal('10.00')
        assert consumption.net_consumption == Decimal('40.00')

    def test_recalculate_water_no_bowls(self, animal_with_user):
        animal = animal_with_user
        now = timezone.now()
        bowl = baker.make(WaterBowl, animal=animal)
        log = baker.make(WaterWeightLog, bowl=bowl, weight=100, observed_at=now)
        WaterBowl.objects.filter(animal=animal).delete()
        recalculate_daily_water_consumption_for_log(log)
        assert not DailyWaterConsumption.objects.filter(animal=animal).exists()

    def test_recalculate_water_single_log(self, animal_with_user):
        """Single log → missing_readings=True but gross=0 so record deleted."""
        animal = animal_with_user
        bowl = baker.make(WaterBowl, animal=animal, is_reference=False)
        now = timezone.now()
        log = baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        recalculate_daily_water_consumption_for_log(log)
        log_date = timezone.localdate(log.observed_at)
        assert not DailyWaterConsumption.objects.filter(animal=animal, date=log_date).exists()

    def test_recalculate_water_negative_delta(self, animal_with_user):
        """Weight goes up → negative period, gross=0 → record deleted."""
        animal = animal_with_user
        bowl = baker.make(WaterBowl, animal=animal, is_reference=False)
        now = timezone.now()
        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('400.00'), entry_type='reading', observed_at=now)
        log2 = baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('500.00'), entry_type='reading',
                          observed_at=now + timezone.timedelta(hours=1))
        recalculate_daily_water_consumption_for_log(log2)
        log_date = timezone.localdate(log2.observed_at)
        assert not DailyWaterConsumption.objects.filter(animal=animal, date=log_date).exists()


    def test_recalculate_water_ref_bowl_negative_evap(self, animal_with_user):
        """Ref bowl weight increases → not counted as evaporation."""
        animal = animal_with_user
        ref_bowl = baker.make(WaterBowl, animal=animal, is_reference=True)
        bowl = baker.make(WaterBowl, animal=animal, is_reference=False)
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())

        baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('500.00'), entry_type='reading', observed_at=now)
        log2 = baker.make(WaterWeightLog, bowl=bowl, weight=Decimal('450.00'), entry_type='reading',
                          observed_at=now + timezone.timedelta(hours=1))
        # Ref bowl goes up (not valid evaporation)
        baker.make(WaterWeightLog, bowl=ref_bowl, weight=Decimal('100.00'), entry_type='reading', observed_at=now)
        baker.make(WaterWeightLog, bowl=ref_bowl, weight=Decimal('110.00'), entry_type='reading',
                   observed_at=now + timezone.timedelta(hours=1))
        recalculate_daily_water_consumption_for_log(log2)
        log_date = timezone.localdate(log2.observed_at)
        cons = DailyWaterConsumption.objects.get(animal=animal, date=log_date)
        assert cons.evaporation == Decimal('0')


@pytest.mark.django_db
class TestFoodConsumptionRecalculation:
    def test_recalculate_food_consumption_basic(self, animal_with_user):
        animal = animal_with_user
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())

        baker.make(FoodWeightLog, animal=animal, weight=Decimal('200.00'), entry_type='reading', observed_at=now)
        log2 = baker.make(FoodWeightLog, animal=animal, weight=Decimal('170.00'), entry_type='reading',
                          observed_at=now + timezone.timedelta(hours=1))

        recalculate_daily_food_consumption_for_log(log2)

        log_date = timezone.localdate(log2.observed_at)
        consumption = DailyFoodConsumption.objects.get(animal=animal, date=log_date)
        assert consumption.total_consumption == Decimal('30.00')

    def test_recalculate_food_with_refill(self, animal_with_user):
        animal = animal_with_user
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())

        baker.make(FoodWeightLog, animal=animal, weight=Decimal('100.00'), entry_type='reading', observed_at=now)
        baker.make(FoodWeightLog, animal=animal, weight=Decimal('300.00'), entry_type='refill',
                   observed_at=now + timezone.timedelta(minutes=30))
        log2 = baker.make(FoodWeightLog, animal=animal, weight=Decimal('250.00'), entry_type='reading',
                          observed_at=now + timezone.timedelta(hours=1))

        recalculate_daily_food_consumption_for_log(log2)

        log_date = timezone.localdate(log2.observed_at)
        consumption = DailyFoodConsumption.objects.get(animal=animal, date=log_date)
        assert consumption.total_consumption == Decimal('50.00')

    def test_recalculate_food_no_logs(self, animal_with_user):
        animal = animal_with_user
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())
        log = baker.make(FoodWeightLog, animal=animal, weight=100, observed_at=now)
        FoodWeightLog.objects.filter(animal=animal).delete()
        recalculate_daily_food_consumption_for_log(log)
        assert not DailyFoodConsumption.objects.filter(animal=animal).exists()

    def test_recalculate_food_single_log(self, animal_with_user):
        """Single log → missing_readings=True → record deleted since no useful info."""
        animal = animal_with_user
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())
        log = baker.make(FoodWeightLog, animal=animal, weight=Decimal('200.00'), entry_type='reading', observed_at=now)
        recalculate_daily_food_consumption_for_log(log)
        log_date = timezone.localdate(log.observed_at)
        assert not DailyFoodConsumption.objects.filter(animal=animal, date=log_date).exists()

    def test_recalculate_food_negative_delta(self, animal_with_user):
        """Weight increases → negative delta → total stays 0 → no record."""
        animal = animal_with_user
        from datetime import datetime, time
        today = timezone.localdate()
        now = timezone.make_aware(datetime.combine(today, time(12, 0, 0)), timezone.get_current_timezone())

        baker.make(FoodWeightLog, animal=animal, weight=Decimal('100.00'), entry_type='reading', observed_at=now)
        log2 = baker.make(FoodWeightLog, animal=animal, weight=Decimal('150.00'), entry_type='reading',
                          observed_at=now + timezone.timedelta(hours=1))
        recalculate_daily_food_consumption_for_log(log2)
        log_date = timezone.localdate(log2.observed_at)
        assert not DailyFoodConsumption.objects.filter(animal=animal, date=log_date).exists()



@pytest.mark.django_db
class TestModelStrMethods:
    def test_animal_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Rex")
        assert "Rex" in str(animal)

    def test_water_bowl_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Rex")
        bowl = WaterBowl.objects.create(animal=animal, name="Main Bowl")
        assert "Main Bowl" in str(bowl)

    def test_water_weight_log_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Rex")
        bowl = WaterBowl.objects.create(animal=animal, name="B")
        log = baker.make(WaterWeightLog, bowl=bowl, weight=100)
        assert str(log)

    def test_food_brand_str(self):
        brand = baker.make(FoodBrand, name="Royal Canin")
        assert "Royal Canin" in str(brand)

    def test_food_type_str(self):
        ftype = baker.make(FoodType, name="Dry")
        assert "Dry" in str(ftype)

    def test_food_weight_log_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Pet")
        log = baker.make(FoodWeightLog, animal=animal, weight=200)
        assert str(log)

    def test_animal_diary_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Rex")
        entry = baker.make(AnimalDiaryEntry, animal=animal, text="Ate well today",
                           observed_at=timezone.now())
        assert str(entry)

    def test_exam_type_str(self):
        et = baker.make(ExamType, name="Hemogram")
        assert "Hemogram" in str(et)

    def test_parameter_type_str(self):
        pt = baker.make(ParameterType, name="Glucose")
        assert "Glucose" in str(pt)

    def test_measurement_unit_str(self):
        u = baker.make(MeasurementUnit, symbol="mg/dL")
        assert "mg/dL" in str(u)

    def test_animal_exam_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Buddy")
        exam = AnimalExam.objects.create(animal=animal, file_name="exam_str_test.pdf")
        assert str(exam)

    def test_extracted_exam_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Buddy")
        ex = baker.make(ExtractedExam, animal=animal)
        assert str(ex)

    def test_exam_organ_finding_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Buddy")
        ex = baker.make(ExtractedExam, animal=animal)
        finding = baker.make(ExamOrganFinding, exam=ex, organ_name="Kidney",
                             description="Normal structure and size")
        assert "Kidney" in str(finding)

    def test_receita_str(self, user):
        """Receita has no file_name, but has data (DateField)."""
        animal = Animal.objects.create(guardian=user, name="Buddy")
        rec = Receita.objects.create(animal=animal, source_identifier="s_str_1",
                                     data=date_cls(2025, 1, 1))
        assert str(rec) is not None

    def test_remedio_str(self):
        rem = baker.make(Remedio, name="Doxycycline")
        assert "Doxycycline" in str(rem)

    def test_daily_water_consumption_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Rex")
        dwc = baker.make(DailyWaterConsumption, animal=animal,
                         gross_consumption=100, evaporation=10, net_consumption=90)
        assert "Rex" in str(dwc)

    def test_daily_food_consumption_str(self, user):
        animal = Animal.objects.create(guardian=user, name="Rex")
        dfc = baker.make(DailyFoodConsumption, animal=animal, total_consumption=250)
        assert "Rex" in str(dfc)
