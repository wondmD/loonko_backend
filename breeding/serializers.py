from rest_framework import serializers

from cattle.models import Cattle

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
            
        from husbandry.models import HusbandrySettings
        settings = HusbandrySettings.load(dam.farm)
        if dam.age_days is not None and dam.age_days < settings.first_breeding_age_days:
            raise serializers.ValidationError(f'Cattle is too young for insemination. Minimum age is {settings.first_breeding_age_days} days.')
            
        active_pregnancies = dam.pregnancies.filter(status=Pregnancy.Status.PREGNANT)
        if active_pregnancies.exists():
            raise serializers.ValidationError(
                'Cannot add insemination record. This cattle already has a confirmed pregnancy.'
            )
        return dam


class PregnancySerializer(serializers.ModelSerializer):
    cattle_tag = serializers.CharField(source='cattle.tag_id', read_only=True)
    sire = serializers.IntegerField(source='breeding_event.sire_id', read_only=True)
    sire_external_id = serializers.CharField(source='breeding_event.sire_external_id', read_only=True)

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
            'sire',
            'sire_external_id',
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
    calf_sire = serializers.PrimaryKeyRelatedField(
        queryset=Cattle.objects.all(), required=False, allow_null=True, write_only=True
    )
    calf_sire_external_id = serializers.CharField(
        required=False, allow_blank=True, write_only=True
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
            'calf_sire',
            'calf_sire_external_id',
            'complications',
            'notes',
            'created_at',
        )
        read_only_fields = ('id', 'calf', 'created_at', 'cattle', 'cattle_tag', 'pregnancy_status', 'expected_calving_date')

    def validate_pregnancy(self, pregnancy):
        if pregnancy.status != Pregnancy.Status.PREGNANT:
            raise serializers.ValidationError('Calving can only be recorded for confirmed pregnancies.')
        if not self.instance and hasattr(pregnancy, 'birth'):
            raise serializers.ValidationError('This pregnancy already has a calving record.')
        return pregnancy

    def validate(self, attrs):
        from django.utils import timezone
        from husbandry.services import get_settings

        pregnancy = attrs.get('pregnancy') or getattr(self.instance, 'pregnancy', None)
        calving_date = attrs.get('calving_date') or getattr(self.instance, 'calving_date', None)

        if not pregnancy or not calving_date:
            return attrs

        dam = pregnancy.cattle
        today = timezone.localdate()
        settings = get_settings(dam.farm)

        if calving_date > today:
            raise serializers.ValidationError(
                {'calving_date': 'Calving date cannot be in the future.'}
            )

        if dam.sex != dam.Sex.FEMALE:
            raise serializers.ValidationError(
                {'pregnancy': f'Dam {dam.tag_id} must be female.'}
            )

        if dam.date_of_birth:
            if calving_date < dam.date_of_birth:
                raise serializers.ValidationError(
                    {'calving_date': 'Calving date cannot be before the dam’s date of birth.'}
                )
            age_at_calving = (calving_date - dam.date_of_birth).days
            if age_at_calving < settings.weaning_days:
                raise serializers.ValidationError(
                    {
                        'pregnancy': (
                            f'Calving cannot be recorded for a calf. Dam {dam.tag_id} is '
                            f'a calf (only {age_at_calving} days old on {calving_date}).'
                        )
                    }
                )

        # Enforce minimum 9 months (270 days) between calvings for the same dam
        min_interval_days = 270
        existing_births = BirthRecord.objects.filter(pregnancy__cattle=dam)
        if self.instance and self.instance.pk:
            existing_births = existing_births.exclude(pk=self.instance.pk)

        for prior in existing_births:
            interval = abs((calving_date - prior.calving_date).days)
            if interval < min_interval_days:
                raise serializers.ValidationError(
                    {
                        'calving_date': (
                            f'Cannot register calving on {calving_date}. Dam {dam.tag_id} '
                            f'has another calving recorded on {prior.calving_date} '
                            f'({interval} days apart). A minimum interval of 9 months '
                            f'(270 days) between calvings is required.'
                        )
                    }
                )

        return attrs

    def create(self, validated_data):
        calf_sire = validated_data.pop('calf_sire', None)
        calf_sire_external_id = validated_data.pop('calf_sire_external_id', None)
        record = BirthRecord(**validated_data)
        if calf_sire:
            record._calf_sire_override = calf_sire
        if calf_sire_external_id:
            record._calf_sire_external_override = calf_sire_external_id
        record.save()
        return record
