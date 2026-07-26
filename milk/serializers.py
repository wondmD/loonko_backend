from rest_framework import serializers

from .models import FeedSchedule, MilkRecord


class MilkRecordSerializer(serializers.ModelSerializer):
    total_liters = serializers.SerializerMethodField()
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True)

    class Meta:
        model = MilkRecord
        fields = (
            'id',
            'cattle',
            'cattle_tag',
            'date',
            'morning_liters',
            'evening_liters',
            'total_liters',
            'recorded_by',
            'notes',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'recorded_by', 'created_at', 'updated_at', 'total_liters')

    def get_total_liters(self, obj):
        return obj.total_liters

    def validate_morning_liters(self, value):
        if value < 0:
            raise serializers.ValidationError('Must be >= 0')
        return value

    def validate_evening_liters(self, value):
        if value < 0:
            raise serializers.ValidationError('Must be >= 0')
        return value


class FeedScheduleSerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True, allow_null=True)

    class Meta:
        model = FeedSchedule
        fields = (
            'id',
            'cattle',
            'cattle_tag',
            'feed_type',
            'quantity',
            'unit',
            'date',
            'quality_score',
            'cost',
            'notes',
            'created_at',
        )
        read_only_fields = ('id', 'created_at', 'cattle_tag')

    def validate_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Cost cannot be negative.')
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError('Quantity must be >= 0')
        return value
