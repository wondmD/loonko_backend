from rest_framework import serializers

from .models import HealthRecord, Treatment, Vaccination


class HealthRecordSerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True)

    class Meta:
        model = HealthRecord
        fields = (
            'id',
            'cattle',
            'cattle_tag',
            'recorded_at',
            'symptoms',
            'temperature',
            'severity',
            'notes',
            'recorded_by',
            'created_at',
        )
        read_only_fields = ('id', 'recorded_by', 'created_at')


class VaccinationSerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True)

    class Meta:
        model = Vaccination
        fields = (
            'id',
            'cattle',
            'cattle_tag',
            'vaccine_name',
            'administered_on',
            'next_due_on',
            'veterinarian_name',
            'cost',
            'notes',
            'recorded_by',
            'created_at',
        )
        read_only_fields = ('id', 'recorded_by', 'created_at')

    def validate_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Cost cannot be negative.')
        return value


class TreatmentSerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True)

    class Meta:
        model = Treatment
        fields = (
            'id',
            'cattle',
            'cattle_tag',
            'diagnosis',
            'medication',
            'start_date',
            'end_date',
            'veterinarian_name',
            'cost',
            'outcome',
            'notes',
            'recorded_by',
            'created_at',
        )
        read_only_fields = ('id', 'recorded_by', 'created_at')

    def validate_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Cost cannot be negative.')
        return value
