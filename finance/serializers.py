from rest_framework import serializers

from .models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            'id',
            'type',
            'category',
            'amount',
            'currency',
            'date',
            'related_milk_record',
            'description',
            'is_auto',
            'source_key',
            'recorded_by',
            'created_at',
        )
        read_only_fields = ('id', 'recorded_by', 'created_at', 'is_auto', 'source_key')

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Amount must be greater than 0.')
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.is_auto:
            raise serializers.ValidationError(
                'Auto milk-income transactions are managed by the system. '
                'Change milk price in Settings or edit milk records instead.'
            )
        return attrs
