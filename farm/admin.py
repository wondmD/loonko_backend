from django.contrib import admin

from .models import Farm


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'region',
        'location',
        'milk_price_per_liter',
        'currency',
        'milk_income_mode',
        'auto_milk_income',
        'updated_at',
    )
    fieldsets = (
        (None, {'fields': ('name', 'location', 'region', 'woreda', 'phone', 'notes')}),
        (
            'Milk pricing',
            {
                'fields': (
                    'milk_price_per_liter',
                    'currency',
                    'milk_income_mode',
                    'auto_milk_income',
                )
            },
        ),
    )
