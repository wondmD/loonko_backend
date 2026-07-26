from django.contrib import admin

from .models import BirthRecord, BreedingEvent, Pregnancy


@admin.register(BreedingEvent)
class BreedingEventAdmin(admin.ModelAdmin):
    list_display = ('dam', 'mating_date', 'method', 'sire')


@admin.register(Pregnancy)
class PregnancyAdmin(admin.ModelAdmin):
    list_display = ('cattle', 'status', 'expected_calving_date', 'confirmed_on')
    list_filter = ('status',)


@admin.register(BirthRecord)
class BirthRecordAdmin(admin.ModelAdmin):
    list_display = ('pregnancy', 'calving_date', 'calf', 'calf_tag_id')
