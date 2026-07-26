from rest_framework import serializers

from .models import Farm


class FarmSerializer(serializers.ModelSerializer):
    class Meta:
        model = Farm
        fields = (
            'id',
            'name',
            'location',
            'region',
            'woreda',
            'phone',
            'notes',
            'milk_price_per_liter',
            'currency',
            'milk_income_mode',
            'auto_milk_income',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_milk_price_per_liter(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Milk price cannot be negative.')
        return value
