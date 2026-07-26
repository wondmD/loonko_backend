from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'type',
        'category',
        'amount',
        'currency',
        'date',
        'is_auto',
        'recorded_by',
    )
    list_filter = ('type', 'category', 'is_auto')
    search_fields = ('description', 'source_key')
