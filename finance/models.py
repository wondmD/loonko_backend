from django.conf import settings
from django.db import models


class Transaction(models.Model):
    class Type(models.TextChoices):
        INCOME = 'INCOME', 'Income'
        EXPENSE = 'EXPENSE', 'Expense'

    class Category(models.TextChoices):
        MILK_PRODUCTION = 'milk_production', 'Milk production income'
        MILK_SALE = 'milk_sale', 'Milk cash sale'
        CATTLE_SALE = 'cattle_sale', 'Cattle sale income'
        FEED = 'feed', 'Feed'
        VET = 'vet', 'Veterinary'
        LABOR = 'labor', 'Labor'
        MAINTENANCE = 'maintenance', 'Maintenance'
        OTHER = 'other', 'Other'

    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    type = models.CharField(max_length=16, choices=Type.choices)
    category = models.CharField(max_length=32, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default='ETB')
    date = models.DateField()
    related_milk_record = models.ForeignKey(
        'milk.MilkRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
    )
    description = models.TextField(blank=True)
    is_auto = models.BooleanField(
        default=False,
        help_text='Generated automatically (e.g. milk production valuation).',
    )
    source_key = models.CharField(
        max_length=191,
        blank=True,
        null=True,
        default=None,
        help_text='Idempotent key for auto transactions.',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['farm', 'source_key'],
                condition=models.Q(source_key__isnull=False),
                name='uniq_txn_farm_source_key',
            ),
        ]
        indexes = [
            models.Index(fields=['farm', 'date', 'type']),
            models.Index(fields=['farm', 'is_auto', 'date']),
        ]

    def __str__(self):
        return f'{self.type} {self.amount} {self.currency} ({self.category})'
