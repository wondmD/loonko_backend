from rest_framework import serializers

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True, default=None)

    class Meta:
        model = Alert
        fields = (
            'id',
            'user',
            'cattle',
            'cattle_tag',
            'category',
            'severity',
            'title',
            'message',
            'is_read',
            'acknowledged_at',
            'created_at',
        )
        read_only_fields = fields
