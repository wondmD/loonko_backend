from decimal import Decimal

from django.db import models


class Farm(models.Model):
    """Tenant farm profile. Each owner manages exactly one farm."""

    class MilkIncomeMode(models.TextChoices):
        ACCRUAL = 'ACCRUAL', 'Accrual (value production)'
        CASH = 'CASH', 'Cash (sales only)'

    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=128, blank=True)
    woreda = models.CharField(max_length=128, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)
    milk_price_per_liter = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('40.00'),
        help_text='Farm-gate price per liter (ETB by default).',
    )
    currency = models.CharField(max_length=8, default='ETB')
    milk_income_mode = models.CharField(
        max_length=16,
        choices=MilkIncomeMode.choices,
        default=MilkIncomeMode.ACCRUAL,
        help_text=(
            'ACCRUAL books daily production as income (cash sales tracked separately). '
            'CASH only counts milk cash sales toward profit.'
        ),
    )
    auto_milk_income = models.BooleanField(
        default=True,
        help_text='When enabled (and mode is ACCRUAL), daily milk production creates income rows.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    @property
    def books_production_income(self):
        return (
            self.milk_income_mode == self.MilkIncomeMode.ACCRUAL
            and self.auto_milk_income
        )

    def __str__(self):
        return self.name
