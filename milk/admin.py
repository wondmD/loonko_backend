from django.contrib import admin

from .models import FeedSchedule, MilkRecord


@admin.register(MilkRecord)
class MilkRecordAdmin(admin.ModelAdmin):
    list_display = ('cattle', 'date', 'morning_liters', 'evening_liters', 'recorded_by')
    list_filter = ('date',)
    search_fields = ('cattle__tag_id',)


@admin.register(FeedSchedule)
class FeedScheduleAdmin(admin.ModelAdmin):
    list_display = ('feed_type', 'cattle', 'quantity', 'cost', 'date')
