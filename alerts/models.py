from django.conf import settings
from django.db import models
from django.utils import timezone


class Alert(models.Model):
    class Category(models.TextChoices):
        MILK = 'MILK', 'Milk'
        HEALTH = 'HEALTH', 'Health'
        BREEDING = 'BREEDING', 'Breeding'
        FINANCE = 'FINANCE', 'Finance'
        SYSTEM = 'SYSTEM', 'System'

    class Severity(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        CRITICAL = 'CRITICAL', 'Critical'

    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        help_text='Null = visible to role-filtered inbox for all relevant users on the farm.',
    )
    cattle = models.ForeignKey(
        'cattle.Cattle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts',
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.INFO)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['farm', 'category', 'is_read']),
            models.Index(fields=['farm', 'created_at']),
            models.Index(fields=['farm', 'dedupe_key']),
        ]

    def __str__(self):
        return f'[{self.severity}] {self.title}'

    def mark_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])

    def acknowledge(self):
        self.is_read = True
        self.acknowledged_at = timezone.now()
        self.save(update_fields=['is_read', 'acknowledged_at'])
