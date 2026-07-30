from rest_framework import serializers

from .models import BirthRecord, BreedingEvent, Pregnancy


class BreedingEventSerializer(serializers.ModelSerializer):
    dam_tag = serializers.CharField(source='dam.tag_id', read_only=True)

    class Meta:
        model = BreedingEvent
        fields = (
            'id',
            'dam',
            'dam_tag',
            'sire',
            'sire_external_id',
            'mating_date',
            'method',
            'notes',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def validate_dam(self, dam):
        if dam.sex != dam.Sex.FEMALE:
            raise serializers.ValidationError(
                'Dam must be female. This system focuses on female cattle husbandry.'
            )
        if dam.status != dam.Status.ACTIVE:
            raise serializers.ValidationError('Dam must be an active animal.')
            
        active_pregnancies = dam.pregnancies.filter(status__in=[Pregnancy.Status.OPEN, Pregnancy.Status.PREGNANT])
        if active_pregnancies.exists():
            raise serializers.ValidationError(
                'Cannot add insemination record. This cattle already has an active or unconfirmed pregnancy. '
                'Please record the outcome (calved or failed) before adding a new insemination.'
            )
        return dam


class PregnancySerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True)

    class Meta:
        model = Pregnancy
        fields = (
            'id',
            'cattle',
            'cattle_tag',
            'breeding_event',
            'confirmed_on',
            'expected_calving_date',
            'status',
            'clinical_notes',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_cattle(self, cattle):
        if cattle.sex != cattle.Sex.FEMALE:
            raise serializers.ValidationError(
                'Pregnancy records are for female cattle only.'
            )
        if cattle.status != cattle.Status.ACTIVE:
            raise serializers.ValidationError('Cannot add pregnancy for inactive cattle.')
            
        if not self.instance:
            active_pregnancies = cattle.pregnancies.filter(status__in=[Pregnancy.Status.OPEN, Pregnancy.Status.PREGNANT])
            if active_pregnancies.exists():
                raise serializers.ValidationError(
                    'This cattle already has an active or unconfirmed pregnancy.'
                )
        return cattle

    def validate(self, attrs):
        status = attrs.get('status', getattr(self.instance, 'status', None))
        confirmed = attrs.get('confirmed_on', getattr(self.instance, 'confirmed_on', None))
        if status == Pregnancy.Status.PREGNANT and not confirmed:
            from django.utils import timezone

            attrs['confirmed_on'] = timezone.localdate()
        return attrs


class BirthRecordSerializer(serializers.ModelSerializer):
    cattle = serializers.IntegerField(source='pregnancy.cattle_id', read_only=True)
    cattle_tag = serializers.CharField(source='pregnancy.cattle.tag_id', read_only=True)
    pregnancy_status = serializers.CharField(source='pregnancy.status', read_only=True)
    expected_calving_date = serializers.DateField(
        source='pregnancy.expected_calving_date',
        read_only=True,
    )

    class Meta:
        model = BirthRecord
        fields = (
            'id',
            'pregnancy',
            'cattle',
            'cattle_tag',
            'pregnancy_status',
            'expected_calving_date',
            'calving_date',
            'calf',
            'calf_tag_id',
            'calf_sex',
            'complications',
            'notes',
            'created_at',
        )
        read_only_fields = ('id', 'calf', 'created_at', 'cattle', 'cattle_tag', 'pregnancy_status', 'expected_calving_date')

    def validate_pregnancy(self, pregnancy):
        if pregnancy.status == Pregnancy.Status.CALVED and not self.instance:
            raise serializers.ValidationError('This pregnancy already has a calving record.')
        if pregnancy.status == Pregnancy.Status.FAILED:
            raise serializers.ValidationError('Cannot record calving for a failed pregnancy.')
        return pregnancy

    def validate(self, attrs):
        pregnancy = attrs.get('pregnancy') or getattr(self.instance, 'pregnancy', None)
        calving_date = attrs.get('calving_date')
        if pregnancy and calving_date and pregnancy.cattle.date_of_birth:
            if calving_date < pregnancy.cattle.date_of_birth:
                raise serializers.ValidationError(
                    {'calving_date': 'Calving date cannot be before the dam’s date of birth.'}
                )
        return attrs
