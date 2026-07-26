from rest_framework import serializers

from .models import HusbandrySettings, HusbandryTask
from .services import life_stage


class HusbandrySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = HusbandrySettings
        fields = (
            'gestation_days',
            'voluntary_waiting_days',
            'dry_period_days',
            'lactation_target_days',
            'estrous_cycle_days',
            'pregnancy_check_days',
            'weaning_days',
            'first_breeding_age_days',
            'fresh_monitor_days',
            'calving_prep_days',
            'heat_watch_days',
            'task_alert_lead_days',
            'updated_at',
        )
        read_only_fields = ('updated_at',)


class HusbandryTaskSerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True)
    days_until = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    task_type_label = serializers.CharField(
        source='get_task_type_display', read_only=True
    )

    class Meta:
        model = HusbandryTask
        fields = (
            'id',
            'cattle',
            'cattle_tag',
            'task_type',
            'task_type_label',
            'title',
            'description',
            'due_date',
            'status',
            'priority',
            'is_auto',
            'source_key',
            'related_breeding',
            'related_pregnancy',
            'completed_at',
            'completed_by',
            'completion_notes',
            'days_until',
            'is_overdue',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'source_key',
            'is_auto',
            'completed_at',
            'completed_by',
            'created_at',
            'updated_at',
            'days_until',
            'is_overdue',
            'task_type_label',
            'cattle_tag',
        )


class HusbandryTaskCompleteSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class CattleLifeStageSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    focus = serializers.BooleanField()


def serialize_life_stage(cattle):
    return life_stage(cattle)
