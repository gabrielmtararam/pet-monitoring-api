from decimal import Decimal
from datetime import date as date_type, datetime, time, timedelta

from django.db import models
from django.utils import timezone

from vet_exams.animals.models import Animal


class FoodBrand(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class FoodType(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class WaterBowl(models.Model):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='water_bowls')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_reference = models.BooleanField(default=False, help_text='Indica se este pote é usado como referência (evaporação) e não para consumo do animal.')

    def __str__(self):
        return f"{self.name} - {self.animal.name}"

class WaterWeightLog(models.Model):
    ENTRY_TYPES = (
        ('reading', 'Leitura de Consumo'),
        ('refill', 'Troca / Abastecimento'),
    )

    bowl = models.ForeignKey(WaterBowl, on_delete=models.CASCADE, related_name='weight_logs')
    weight = models.DecimalField(max_digits=10, decimal_places=2)
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES, default='reading')
    observed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-observed_at']

    def __str__(self):
        return f"{self.get_entry_type_display()} - {self.weight}g ({self.observed_at})"


class FoodWeightLog(models.Model):
    ENTRY_TYPES = (
        ('reading', 'Leitura de Consumo'),
        ('refill', 'Troca / Abastecimento'),
    )

    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='food_weight_logs')
    brand = models.ForeignKey(FoodBrand, on_delete=models.SET_NULL, null=True, blank=True, related_name='food_weight_logs')
    type = models.ForeignKey(FoodType, on_delete=models.SET_NULL, null=True, blank=True, related_name='food_weight_logs')
    weight = models.DecimalField(max_digits=10, decimal_places=2)
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES, default='reading')
    observed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-observed_at']

    def __str__(self):
        return f"Ração - {self.get_entry_type_display()} - {self.weight}g ({self.observed_at})"


class AnimalDiaryEntry(models.Model):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='diary_entries')
    text = models.TextField()
    observed_at = models.DateTimeField(default=timezone.now, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-observed_at']

    def __str__(self):
        return f"Diário - {self.animal.name} ({self.observed_at})"


class AnimalExam(models.Model):
    file_name = models.CharField(max_length=255, unique=True)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='exams')
    source_url = models.URLField(blank=True, null=True)
    file = models.FileField(upload_to='exams/', blank=True, null=True)
    source_exam_type_label = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text='Texto do tipo de exame extraído da página do SimplesPet (ex.: Ultrassonografia, Hemograma + Bioquímico).',
    )
    source_observed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Data/hora do exame extraída da página do SimplesPet (fallback quando a IA não encontrar no documento).',
    )
    identified_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-identified_at']

    def __str__(self):
        return f"{self.file_name} - {self.animal.name}"


class Remedio(models.Model):
    """Medicine for registration and use in prescriptions (e.g., Vonau)."""
    name = models.CharField(max_length=200)
    principio_ativo = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text='Nome do princípio ativo ou substância.',
    )

    class Meta:
        verbose_name = 'Remédio'
        verbose_name_plural = 'Remédios'
        ordering = ['name']

    def __str__(self):
        return self.name


class Receita(models.Model):
    """Veterinary prescription (e.g., extracted from SimplesPet page), with date and list of indications."""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='receitas')
    data = models.DateField(help_text='Data da receita.')
    source_identifier = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        help_text='Identificador único da receita na origem (ex.: id do evento no SimplesPet).',
    )
    source_url = models.URLField(blank=True, null=True)
    file = models.FileField(upload_to='receitas/', blank=True, null=True)
    identified_at = models.DateTimeField(default=timezone.now)
    gemini_prompt_tokens = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Tokens de prompt consumidos no processamento com Gemini.',
    )
    gemini_completion_tokens = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Tokens de resposta (completion) consumidos no processamento com Gemini.',
    )
    gemini_total_tokens = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Total de tokens consumidos no processamento com Gemini.',
    )

    class Meta:
        ordering = ['-data', '-identified_at']
        verbose_name_plural = 'Receitas'


class DailyWaterConsumption(models.Model):
    """
    Daily water consumption aggregated by animal, considering:
    - All consumption bowls (non-reference)
    - Reference bowls to estimate evaporation
    - Periods between readings, respecting refills
    """

    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='daily_water_consumptions')
    date = models.DateField()


    gross_consumption = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Soma do consumo bruto de água em todos os potes de consumo no dia.',
    )
    evaporation = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Evaporação estimada a partir do pote de referência no dia.',
    )
    net_consumption = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Consumo líquido (gross_consumption - evaporation), truncado em zero quando negativo.',
    )


    negative_periods = models.PositiveIntegerField(
        default=0,
        help_text='Quantidade de períodos em que o consumo bruto calculado ficou negativo (possível refill não marcado).',
    )
    missing_readings = models.BooleanField(
        default=False,
        help_text='True se foram detectadas faltas de leitura para algum pote em períodos relevantes no dia.',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ('animal', 'date')
        verbose_name = 'Consumo diário de água'
        verbose_name_plural = 'Consumos diários de água'

    def __str__(self):
        return f"Água - {self.animal.name} em {self.date}"


class DailyFoodConsumption(models.Model):
    """
    Daily food consumption aggregated by animal, using FoodWeightLog.
    """

    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='daily_food_consumptions')
    date = models.DateField()


    total_consumption = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Consumo total de ração no dia (soma líquida considerando refills).',
    )

    negative_periods = models.PositiveIntegerField(
        default=0,
        help_text='Quantidade de períodos em que o consumo bruto calculado ficou negativo (possível refill não marcado).',
    )
    missing_readings = models.BooleanField(
        default=False,
        help_text='True se foram detectadas faltas de leitura de ração em períodos relevantes no dia.',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ('animal', 'date')
        verbose_name = 'Consumo diário de ração'
        verbose_name_plural = 'Consumos diários de ração'

    def __str__(self):
        return f"Ração - {self.animal.name} em {self.date}"


def recalculate_daily_water_consumption_for_log(
    log: WaterWeightLog,
    for_date: date_type | None = None,
) -> None:
    """
    Recalculate daily water consumption for the animal/date of the given log.

    The last log *before* the day starts is used as opening balance for each bowl,
    so cross-day consumption (one reading per day pattern) is accounted for correctly.

    Consumption bowls: gross consumption = sum of (prev - curr) when curr is a reading.
    Reference bowls:   evaporation  = sum of (prev - curr) when delta > 0 (weight dropped).
    Refill pairs are skipped for consumption; any delta is used for reference evaporation.
    """
    if for_date is not None:
        log_date = for_date
    elif not log.observed_at:
        log_date = timezone.localdate()
    else:
        log_date = timezone.localdate(log.observed_at)

    animal = log.bowl.animal

    local_tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(log_date, time.min), local_tz)
    end_dt = timezone.make_aware(datetime.combine(log_date, time.max), local_tz)

    bowls_qs = WaterBowl.objects.filter(animal=animal)
    if not bowls_qs.exists():
        DailyWaterConsumption.objects.filter(animal=animal, date=log_date).delete()
        return

    ref_bowls = bowls_qs.filter(is_reference=True)
    consumption_bowls = bowls_qs.filter(is_reference=False)

    gross_total = Decimal('0')
    evaporation_total = Decimal('0')
    negative_periods = 0
    missing_readings = False

    for bowl in consumption_bowls:
        # Opening balance: last log for this bowl before today.
        prev_log = (
            WaterWeightLog.objects.filter(
                bowl=bowl,
                observed_at__lt=start_dt,
                observed_at__isnull=False,
            )
            .order_by('-observed_at')
            .first()
        )

        logs_qs = (
            WaterWeightLog.objects.filter(
                bowl=bowl,
                observed_at__gte=start_dt,
                observed_at__lte=end_dt,
            )
            .order_by('observed_at')
        )
        logs_list = list(logs_qs)

        if not logs_list:
            continue

        extended = ([prev_log] + logs_list) if prev_log else logs_list

        # Need at least a pair to measure consumption.
        if len(extended) < 2:
            missing_readings = True
            continue

        for prev, curr in zip(extended, extended[1:]):
            if curr.entry_type == 'refill':
                continue

            if prev.weight is None or curr.weight is None:
                continue

            delta = prev.weight - curr.weight
            if delta < 0:
                negative_periods += 1
                continue

            gross_total += delta

    for bowl in ref_bowls:
        # Same opening balance logic for reference (evaporation) bowls.
        prev_log = (
            WaterWeightLog.objects.filter(
                bowl=bowl,
                observed_at__lt=start_dt,
                observed_at__isnull=False,
            )
            .order_by('-observed_at')
            .first()
        )

        logs_qs = (
            WaterWeightLog.objects.filter(
                bowl=bowl,
                observed_at__gte=start_dt,
                observed_at__lte=end_dt,
            )
            .order_by('observed_at')
        )
        logs_list = list(logs_qs)

        if not logs_list:
            continue

        extended = ([prev_log] + logs_list) if prev_log else logs_list

        if len(extended) < 2:
            missing_readings = True
            continue

        for prev, curr in zip(extended, extended[1:]):
            if prev.weight is None or curr.weight is None:
                continue
            delta = prev.weight - curr.weight
            if delta > 0:
                evaporation_total += delta

    net = gross_total - evaporation_total
    if net < 0:
        net = Decimal('0')

    if gross_total == 0 and evaporation_total == 0:
        DailyWaterConsumption.objects.filter(animal=animal, date=log_date).delete()
        return

    DailyWaterConsumption.objects.update_or_create(
        animal=animal,
        date=log_date,
        defaults={
            'gross_consumption': gross_total,
            'evaporation': evaporation_total,
            'net_consumption': net,
            'negative_periods': negative_periods,
            'missing_readings': missing_readings,
        },
    )


def recalculate_daily_food_consumption_for_log(
    log: FoodWeightLog,
    for_date: date_type | None = None,
) -> None:
    """
    Recalculate daily food consumption for the animal/date of the given log.

    `for_date` allows recalculating a specific date (e.g. the next day) without
    a real log for that date.

    The last food log *before* the day starts is included as an opening balance,
    so cross-day consumption (e.g. a reading on day N-1 and one on day N) is
    correctly accounted for.

    Pairs processed (in observed_at order):
    - reading -> reading: delta = prev - curr  (net consumption)
    - refill  -> reading: delta = prev - curr  (consumption since last refill)
    - *       -> refill : skip (bowl was topped up, not consumed)
    - refill  -> refill : skip (consecutive refills, no consumption measured)
    """
    if for_date is not None:
        log_date = for_date
    elif not log.observed_at:
        log_date = timezone.localdate()
    else:
        log_date = timezone.localdate(log.observed_at)

    animal = log.animal

    local_tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(log_date, time.min), local_tz)
    end_dt = timezone.make_aware(datetime.combine(log_date, time.max), local_tz)

    # Opening balance: last log *before* today (any entry_type).
    last_prev_log = (
        FoodWeightLog.objects.filter(
            animal=animal,
            observed_at__lt=start_dt,
            observed_at__isnull=False,
        )
        .order_by('-observed_at')
        .first()
    )

    logs_qs = (
        FoodWeightLog.objects.filter(
            animal=animal,
            observed_at__gte=start_dt,
            observed_at__lte=end_dt,
        )
        .order_by('observed_at')
    )
    logs_list = list(logs_qs)

    if not logs_list:
        DailyFoodConsumption.objects.filter(animal=animal, date=log_date).delete()
        return

    # Prepend previous day's last entry as opening balance for cross-day deltas.
    extended_logs = ([last_prev_log] + logs_list) if last_prev_log else logs_list

    total = Decimal('0')
    negative_periods = 0

    # Count measurable pairs (those where curr is a reading, not a refill).
    measurable_pairs = sum(
        1 for _, curr in zip(extended_logs, extended_logs[1:]) if curr.entry_type != 'refill'
    )
    missing_readings = measurable_pairs == 0

    for prev, curr in zip(extended_logs, extended_logs[1:]):
        # Skip any pair where the bowl was refilled — that represents a top-up, not consumption.
        if curr.entry_type == 'refill':
            continue

        if prev.weight is None or curr.weight is None:
            continue

        delta = prev.weight - curr.weight
        if delta < 0:
            # Negative delta suggests an unregistered refill between readings.
            negative_periods += 1
            continue

        total += delta

    if total < 0:
        total = Decimal('0')

    # No useful data: not enough measurable periods or all periods summed to zero.
    if missing_readings or (total == 0 and measurable_pairs > 0):
        DailyFoodConsumption.objects.filter(animal=animal, date=log_date).delete()
        return

    DailyFoodConsumption.objects.update_or_create(
        animal=animal,
        date=log_date,
        defaults={
            'total_consumption': total,
            'negative_periods': negative_periods,
            'missing_readings': missing_readings,
        },
    )





class IndicacaoMedicamento(models.Model):
    """Medication indication within a prescription: medicine, presentation, dosage, frequency, and period."""
    receita = models.ForeignKey(Receita, on_delete=models.CASCADE, related_name='indicacoes')
    remedio = models.ForeignKey(Remedio, on_delete=models.CASCADE, related_name='indicacoes')
    forma_apresentacao = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Forma de apresentação (ex.: frasco, comprimido).',
    )
    medida_apresentacao = models.CharField(
        max_length=80,
        blank=True,
        null=True,
        help_text='Medida da apresentação (ex.: 2mg/ml).',
    )
    dosagem = models.CharField(
        max_length=80,
        blank=True,
        null=True,
        help_text='Dosagem (ex.: 0,4ml).',
    )
    frequencia = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text='Frequência (ex.: a cada 12 horas).',
    )
    periodo = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text='Período (ex.: por 7 dias).',
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'remedio__name']
        verbose_name = 'Indicação de medicamento'
        verbose_name_plural = 'Indicações de medicamento'

    def __str__(self):
        return f"{self.remedio.name}: {self.dosagem or '—'} {self.frequencia or ''} {self.periodo or ''}".strip()


class ExamType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class ParameterType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class MeasurementUnit(models.Model):
    symbol = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.symbol


class ExtractedExam(models.Model):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='extracted_exams')
    source_file = models.ForeignKey(AnimalExam, on_delete=models.SET_NULL, blank=True, null=True, related_name='extracted_exams')
    exam_type = models.ForeignKey(ExamType, on_delete=models.SET_NULL, blank=True, null=True, related_name='extracted_exams')
    observed_at = models.DateTimeField(default=timezone.now, blank=True, null=True)
    observed_at_found_in_document = models.BooleanField(
        null=True,
        blank=True,
        help_text='True se a IA encontrou data/hora de realização/coleta no documento; False se usou sugestão da página.',
    )
    extracted_at = models.DateTimeField(auto_now_add=True)
    observations = models.TextField(
        blank=True,
        null=True,
        help_text='Impressão diagnóstica, conclusão ou observações gerais do exame (ex.: IMPRESSÃO DIAGNÓSTICA de ultrassom).',
    )
    gemini_prompt_tokens = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Tokens de prompt consumidos na extração com Gemini.',
    )
    gemini_completion_tokens = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Tokens de resposta (completion) consumidos na extração com Gemini.',
    )
    gemini_total_tokens = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='Total de tokens consumidos na extração com Gemini.',
    )
    parameters = models.ManyToManyField(ParameterType, through='ExamParameterResult', related_name='extracted_exams')

    class Meta:
        ordering = ['-observed_at']

    def __str__(self):
        exam_type = self.exam_type.name if self.exam_type else 'Unclassified exam'
        return f"{exam_type} - {self.animal.name} ({self.observed_at})"


class ExamOrganFinding(models.Model):
    """Finding by organ in imaging exams (e.g., ultrasound): organ + narrative description."""
    exam = models.ForeignKey(ExtractedExam, on_delete=models.CASCADE, related_name='organ_findings')
    organ_name = models.CharField(max_length=200, help_text='Nome do órgão ou estrutura (ex.: Rins, Vesícula urinária).')
    description = models.TextField(help_text='Descrição/achado para esse órgão.')
    order = models.PositiveSmallIntegerField(default=0, help_text='Ordem de exibição.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'organ_name']

    def __str__(self):
        return f"{self.organ_name}: {self.description[:50]}..."


class ExamParameterResult(models.Model):
    exam = models.ForeignKey(ExtractedExam, on_delete=models.CASCADE, related_name='parameter_results')
    parameter_type = models.ForeignKey(ParameterType, on_delete=models.CASCADE, related_name='results')
    unit = models.ForeignKey(MeasurementUnit, on_delete=models.SET_NULL, blank=True, null=True, related_name='results')
    measured_value = models.CharField(max_length=120)
    reference_range = models.CharField(max_length=120, blank=True, null=True)
    raw_parameter_name = models.CharField(max_length=120, blank=True, null=True)
    raw_unit = models.CharField(max_length=40, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['parameter_type__name']
        unique_together = ('exam', 'parameter_type')

    def __str__(self):
        unit = f" {self.unit.symbol}" if self.unit else ''
        return f"{self.parameter_type.name}: {self.measured_value}{unit}"
