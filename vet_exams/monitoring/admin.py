from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from vet_exams.monitoring.models import (
    AnimalDiaryEntry,
    AnimalExam,
    DailyFoodConsumption,
    DailyWaterConsumption,
    ExamOrganFinding,
    ExamParameterResult,
    ExamType,
    ExtractedExam,
    FoodBrand,
    FoodType,
    FoodWeightLog,
    IndicacaoMedicamento,
    MeasurementUnit,
    ParameterType,
    Receita,
    Remedio,
    WaterBowl,
    WaterWeightLog,
)


class WaterWeightLogInline(admin.TabularInline):
    model = WaterWeightLog
    extra = 1
    fields = ('observed_at', 'weight', 'entry_type')


@admin.register(WaterBowl)
class WaterBowlAdmin(ImportExportModelAdmin):
    list_display = ('name', 'animal')
    search_fields = ('name', 'animal__name')
    inlines = [WaterWeightLogInline]


@admin.register(WaterWeightLog)
class WaterWeightLogAdmin(ImportExportModelAdmin):
    list_display = ('bowl', 'weight', 'entry_type', 'observed_at')
    list_filter = ('entry_type', 'bowl', 'bowl__animal')
    search_fields = ('bowl__name', 'bowl__animal__name')
    date_hierarchy = 'observed_at'


@admin.register(FoodBrand)
class FoodBrandAdmin(ImportExportModelAdmin):
  list_display = ('id', 'name')
  search_fields = ('name',)


@admin.register(FoodType)
class FoodTypeAdmin(ImportExportModelAdmin):
  list_display = ('id', 'name')
  search_fields = ('name',)


@admin.register(FoodWeightLog)
class FoodWeightLogAdmin(ImportExportModelAdmin):
  list_display = ('animal', 'weight', 'entry_type', 'brand', 'type', 'observed_at')
  list_filter = ('entry_type', 'animal', 'brand', 'type')
  search_fields = ('animal__name', 'brand__name', 'type__name')
  autocomplete_fields = ('animal', 'brand', 'type')
  date_hierarchy = 'observed_at'
  ordering = ('-observed_at',)


@admin.register(AnimalDiaryEntry)
class AnimalDiaryEntryAdmin(ImportExportModelAdmin):
  list_display = ('animal', 'observed_at', 'created_at')
  list_filter = ('animal',)
  search_fields = ('animal__name', 'text')
  date_hierarchy = 'observed_at'


@admin.register(AnimalExam)
class AnimalExamAdmin(ImportExportModelAdmin):
  list_display = ('file_name', 'animal', 'source_exam_type_label', 'source_observed_at', 'identified_at', 'file')
  list_filter = ('animal',)
  search_fields = ('file_name', 'animal__name', 'source_exam_type_label')
  date_hierarchy = 'identified_at'


class IndicacaoMedicamentoInline(admin.TabularInline):
  model = IndicacaoMedicamento
  extra = 0
  autocomplete_fields = ('remedio',)
  fields = ('remedio', 'forma_apresentacao', 'medida_apresentacao', 'dosagem', 'frequencia', 'periodo', 'order')


@admin.register(Remedio)
class RemedioAdmin(ImportExportModelAdmin):
  list_display = ('id', 'name', 'principio_ativo')
  search_fields = ('name', 'principio_ativo')


@admin.register(Receita)
class ReceitaAdmin(ImportExportModelAdmin):
  list_display = ('animal', 'data', 'identified_at', 'gemini_total_tokens', 'source_url')
  list_filter = ('animal',)
  search_fields = ('animal__name',)
  date_hierarchy = 'data'
  inlines = [IndicacaoMedicamentoInline]
  readonly_fields = ('gemini_prompt_tokens', 'gemini_completion_tokens', 'gemini_total_tokens')


@admin.register(ExamType)
class ExamTypeAdmin(ImportExportModelAdmin):
  list_display = ('id', 'name')
  search_fields = ('name',)


@admin.register(ParameterType)
class ParameterTypeAdmin(ImportExportModelAdmin):
  list_display = ('id', 'name')
  search_fields = ('name',)


@admin.register(MeasurementUnit)
class MeasurementUnitAdmin(ImportExportModelAdmin):
  list_display = ('id', 'symbol', 'description')
  search_fields = ('symbol', 'description')


class ExamParameterResultInline(admin.TabularInline):
  model = ExamParameterResult
  extra = 0
  autocomplete_fields = ('parameter_type', 'unit')


class ExamOrganFindingInline(admin.TabularInline):
  model = ExamOrganFinding
  extra = 0
  fields = ('organ_name', 'description', 'order')


@admin.register(ExtractedExam)
class ExtractedExamAdmin(ImportExportModelAdmin):
  list_display = ('animal', 'exam_type', 'observed_at', 'observed_at_found_in_document', 'source_file', 'gemini_total_tokens')
  list_filter = ('animal', 'exam_type', 'observed_at_found_in_document')
  search_fields = ('animal__name', 'source_file__file_name', 'exam_type__name')
  date_hierarchy = 'observed_at'
  autocomplete_fields = ('animal', 'source_file', 'exam_type')
  inlines = [ExamParameterResultInline, ExamOrganFindingInline]
  readonly_fields = ('gemini_prompt_tokens', 'gemini_completion_tokens', 'gemini_total_tokens')


@admin.register(DailyWaterConsumption)
class DailyWaterConsumptionAdmin(ImportExportModelAdmin):
  list_display = ('animal', 'date', 'net_consumption', 'gross_consumption', 'evaporation', 'negative_periods', 'missing_readings')
  list_filter = ('animal', 'date')
  search_fields = ('animal__name',)
  date_hierarchy = 'date'


@admin.register(DailyFoodConsumption)
class DailyFoodConsumptionAdmin(ImportExportModelAdmin):
  list_display = ('animal', 'date', 'total_consumption', 'negative_periods', 'missing_readings', 'created_at')
  list_filter = ('animal', 'missing_readings')
  search_fields = ('animal__name',)
  date_hierarchy = 'date'
  ordering = ('-date',)
  readonly_fields = ('created_at',)