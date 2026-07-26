from django.contrib import admin

from .models import HusbandrySettings, HusbandryTask


@admin.register(HusbandrySettings)
class HusbandrySettingsAdmin(admin.ModelAdmin):
    list_display = (
        'gestation_days',
        'voluntary_waiting_days',
        'dry_period_days',
        'weaning_days',
        'first_breeding_age_days',
        'updated_at',
    )

    def has_add_permission(self, request):
        return not HusbandrySettings.objects.exists()


@admin.register(HusbandryTask)
class HusbandryTaskAdmin(admin.ModelAdmin):
    list_display = (
        'cattle',
        'task_type',
        'title',
        'due_date',
        'status',
        'priority',
        'is_auto',
    )
    list_filter = ('task_type', 'status', 'priority', 'is_auto')
    search_fields = ('title', 'cattle__tag_id', 'source_key')
    raw_id_fields = ('cattle', 'related_breeding', 'related_pregnancy', 'completed_by')
