from django.conf import settings
from django.db import models


class HealthRecord(models.Model):
    class Severity(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'

    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='health_records',
    )
    cattle = models.ForeignKey('cattle.Cattle', on_delete=models.CASCADE, related_name='health_records')
    recorded_at = models.DateTimeField()
    symptoms = models.JSONField(default=list, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.LOW)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='health_records',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [models.Index(fields=['farm', 'recorded_at'])]

    def __str__(self):
        return f'Health {self.cattle.tag_id} @ {self.recorded_at:%Y-%m-%d}'


class Vaccination(models.Model):
    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='vaccinations',
    )
    cattle = models.ForeignKey('cattle.Cattle', on_delete=models.CASCADE, related_name='vaccinations')
    vaccine_name = models.CharField(max_length=128)
    administered_on = models.DateField()
    next_due_on = models.DateField(null=True, blank=True)
    veterinarian_name = models.CharField(max_length=128, blank=True)
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Optional cost booked as a veterinary expense.',
    )
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vaccinations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-administered_on']
        indexes = [models.Index(fields=['farm', 'next_due_on'])]

    def __str__(self):
        return f'{self.vaccine_name} — {self.cattle.tag_id}'


class Treatment(models.Model):
    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='treatments',
    )
    cattle = models.ForeignKey('cattle.Cattle', on_delete=models.CASCADE, related_name='treatments')
    diagnosis = models.CharField(max_length=255)
    medication = models.CharField(max_length=255, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    veterinarian_name = models.CharField(max_length=128, blank=True)
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Optional cost booked as a veterinary expense.',
    )
    outcome = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='treatments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']
        indexes = [models.Index(fields=['farm', 'start_date'])]

    def __str__(self):
        return f'{self.diagnosis} — {self.cattle.tag_id}'
