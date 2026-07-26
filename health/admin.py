from django.contrib import admin

from .models import HealthRecord, Treatment, Vaccination


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ('cattle', 'recorded_at', 'severity', 'recorded_by')
    list_filter = ('severity',)


@admin.register(Vaccination)
class VaccinationAdmin(admin.ModelAdmin):
    list_display = ('cattle', 'vaccine_name', 'administered_on', 'cost', 'next_due_on')


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ('cattle', 'diagnosis', 'start_date', 'cost', 'end_date')
