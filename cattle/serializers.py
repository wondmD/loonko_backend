from rest_framework import serializers

from alerts.serializers import AlertSerializer
from breeding.serializers import BirthRecordSerializer, BreedingEventSerializer, PregnancySerializer
from health.serializers import VaccinationSerializer
from husbandry.serializers import HusbandryTaskSerializer
from husbandry.services import life_stage
from husbandry.planning import suggested_windows
from milk.serializers import MilkRecordSerializer

from .models import Cattle, CattleGrowthLog
from .reproductive_intake import apply_reproductive_intake


class CattleGrowthLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CattleGrowthLog
        fields = ('id', 'cattle', 'date', 'weight_kg', 'bcs', 'notes', 'recorded_by', 'created_at')
        read_only_fields = ('id', 'cattle', 'recorded_by', 'created_at')



def _abs_url(request, field):
    if not field:
        return None
    url = field.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def _apply_photo_files(validated_data, request):
    if request is None:
        return validated_data
    for field in ('photo_front', 'photo_left', 'photo_right'):
        if field not in validated_data and field in request.FILES:
            validated_data[field] = request.FILES[field]
    return validated_data


def _parse_bool(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', '1', 'yes'):
            return True
        if lowered in ('false', '0', 'no'):
            return False
    return bool(value)


class CattleSerializer(serializers.ModelSerializer):
    photo_front_url = serializers.SerializerMethodField()
    photo_left_url = serializers.SerializerMethodField()
    photo_right_url = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    life_stage = serializers.SerializerMethodField()
    lactation = serializers.SerializerMethodField()
    next_event = serializers.SerializerMethodField()
    husbandry_plan = serializers.SerializerMethodField()

    # Write-only reproductive onboarding (create only)
    is_pregnant = serializers.CharField(required=False, allow_blank=True, write_only=True)
    insemination_date = serializers.DateField(required=False, allow_null=True, write_only=True)
    breeding_method = serializers.ChoiceField(
        choices=['AI', 'NATURAL'],
        required=False,
        write_only=True,
        default='AI',
    )
    previous_calvings = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=20,
        write_only=True,
        default=0,
    )
    last_calving_date = serializers.DateField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Cattle
        fields = (
            'id',
            'tag_id',
            'name',
            'breed',
            'sex',
            'date_of_birth',
            'status',
            'sale_price',
            'sale_date',
            'cull_reason',
            'mother',
            'mother_external_id',
            'father',
            'father_external_id',
            'notes',
            'photo_front',
            'photo_left',
            'photo_right',
            'photo_front_url',
            'photo_left_url',
            'photo_right_url',
            'photo_url',
            'life_stage',
            'lactation',
            'next_event',
            'husbandry_plan',
            'is_pregnant',
            'insemination_date',
            'breeding_method',
            'previous_calvings',
            'last_calving_date',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'created_at',
            'updated_at',
            'photo_front_url',
            'photo_left_url',
            'photo_right_url',
            'photo_url',
            'life_stage',
            'lactation',
            'next_event',
            'husbandry_plan',
        )
        extra_kwargs = {
            'photo_front': {'write_only': True, 'required': False},
            'photo_left': {'write_only': True, 'required': False},
            'photo_right': {'write_only': True, 'required': False},
            'sex': {'default': Cattle.Sex.FEMALE},
            'tag_id': {'required': False},
        }

    def get_photo_front_url(self, obj):
        return _abs_url(self.context.get('request'), obj.photo_front)

    def get_photo_left_url(self, obj):
        return _abs_url(self.context.get('request'), obj.photo_left)

    def get_photo_right_url(self, obj):
        return _abs_url(self.context.get('request'), obj.photo_right)

    def get_photo_url(self, obj):
        return self.get_photo_front_url(obj)

    def get_life_stage(self, obj):
        return life_stage(obj)

    def get_lactation(self, obj):
        return obj.lactation_info()

    def get_next_event(self, obj):
        events = obj.upcoming_events()
        return events[0] if events else None

    def get_husbandry_plan(self, obj):
        plan = suggested_windows(obj)
        return {
            'animal_class': plan['animal_class'],
            'windows': plan['windows'][:4],
            'warnings': plan['warnings'][:3],
        }

    def validate(self, attrs):
        if self.instance is None:
            request = self.context.get('request')
            files = getattr(request, 'FILES', {}) if request else {}
            missing = [
                name
                for name in ('photo_front', 'photo_left', 'photo_right')
                if name not in attrs and name not in files
            ]
            if missing:
                raise serializers.ValidationError(
                    {field: 'This photo is required for identification.' for field in missing}
                )
            attrs.setdefault('sex', Cattle.Sex.FEMALE)

            if 'is_pregnant' in attrs:
                attrs['is_pregnant'] = _parse_bool(attrs.get('is_pregnant'))

            is_pregnant = attrs.get('is_pregnant')
            previous = attrs.get('previous_calvings') or 0
            if is_pregnant and not attrs.get('insemination_date'):
                raise serializers.ValidationError(
                    {'insemination_date': 'Required when the animal is pregnant.'}
                )
            if previous and not attrs.get('last_calving_date') and not is_pregnant:
                # Optional but recommended — leave to service to estimate
                pass
        else:
            # Intake fields are create-only
            for key in (
                'is_pregnant',
                'insemination_date',
                'breeding_method',
                'previous_calvings',
                'last_calving_date',
            ):
                attrs.pop(key, None)
        return attrs

    def create(self, validated_data):
        validated_data = _apply_photo_files(validated_data, self.context.get('request'))
        intake = {
            'is_pregnant': validated_data.pop('is_pregnant', None),
            'insemination_date': validated_data.pop('insemination_date', None),
            'breeding_method': validated_data.pop('breeding_method', 'AI'),
            'previous_calvings': validated_data.pop('previous_calvings', 0) or 0,
            'last_calving_date': validated_data.pop('last_calving_date', None),
        }
        cattle = super().create(validated_data)
        apply_reproductive_intake(cattle, **intake)
        return cattle

    def update(self, instance, validated_data):
        validated_data = _apply_photo_files(validated_data, self.context.get('request'))
        old_status = instance.status
        instance = super().update(instance, validated_data)

        if instance.status in ('SOLD', 'DEAD', 'CULLED') and old_status not in ('SOLD', 'DEAD', 'CULLED'):
            # 1. Cancel pending care tasks
            from husbandry.models import HusbandryTask
            HusbandryTask.objects.filter(
                cattle=instance,
                status=HusbandryTask.Status.PENDING,
            ).update(status=HusbandryTask.Status.CANCELLED)

        if instance.status == 'SOLD' and instance.sale_price and instance.sale_price > 0:
            # 2. Auto-post Cattle Sale Income to Finance
            from finance.models import Transaction
            from django.utils import timezone
            sale_date = instance.sale_date or timezone.localdate()
            Transaction.objects.update_or_create(
                farm=instance.farm,
                source_key=f'cattle-sale-{instance.id}',
                defaults={
                    'type': Transaction.Type.INCOME,
                    'category': Transaction.Category.CATTLE_SALE,
                    'amount': instance.sale_price,
                    'currency': instance.farm.currency or 'ETB',
                    'date': sale_date,
                    'description': f'Cattle Sale: {instance.tag_id} ({instance.name or instance.breed or "cattle"})',
                    'is_auto': True,
                    'recorded_by': self.context.get('request').user if self.context.get('request') else None,
                }
            )
        return instance


class CattleWorkerUpdateSerializer(serializers.ModelSerializer):
    photo_front_url = serializers.SerializerMethodField()
    photo_left_url = serializers.SerializerMethodField()
    photo_right_url = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Cattle
        fields = (
            'notes',
            'status',
            'photo_front',
            'photo_left',
            'photo_right',
            'photo_front_url',
            'photo_left_url',
            'photo_right_url',
            'photo_url',
        )
        read_only_fields = (
            'photo_front_url',
            'photo_left_url',
            'photo_right_url',
            'photo_url',
        )
        extra_kwargs = {
            'photo_front': {'write_only': True, 'required': False},
            'photo_left': {'write_only': True, 'required': False},
            'photo_right': {'write_only': True, 'required': False},
        }

    def get_photo_front_url(self, obj):
        return _abs_url(self.context.get('request'), obj.photo_front)

    def get_photo_left_url(self, obj):
        return _abs_url(self.context.get('request'), obj.photo_left)

    def get_photo_right_url(self, obj):
        return _abs_url(self.context.get('request'), obj.photo_right)

    def get_photo_url(self, obj):
        return self.get_photo_front_url(obj)

    def update(self, instance, validated_data):
        validated_data = _apply_photo_files(validated_data, self.context.get('request'))
        return super().update(instance, validated_data)


class CattleDetailSerializer(CattleSerializer):
    age_days = serializers.SerializerMethodField()
    upcoming_events = serializers.SerializerMethodField()
    milk_summary = serializers.SerializerMethodField()
    breeding_history = serializers.SerializerMethodField()
    recent_milk = serializers.SerializerMethodField()
    alerts = serializers.SerializerMethodField()
    upcoming_vaccinations = serializers.SerializerMethodField()
    husbandry_tasks = serializers.SerializerMethodField()

    pedigree_tree = serializers.SerializerMethodField()
    growth_logs = serializers.SerializerMethodField()
    latest_bcs = serializers.SerializerMethodField()
    latest_weight = serializers.SerializerMethodField()

    class Meta(CattleSerializer.Meta):
        fields = CattleSerializer.Meta.fields + (
            'age_days',
            'upcoming_events',
            'milk_summary',
            'breeding_history',
            'recent_milk',
            'alerts',
            'upcoming_vaccinations',
            'husbandry_tasks',
            'pedigree_tree',
            'growth_logs',
            'latest_bcs',
            'latest_weight',
        )

    def get_husbandry_plan(self, obj):
        return suggested_windows(obj)

    def get_age_days(self, obj):
        return obj.age_days

    def get_upcoming_events(self, obj):
        return obj.upcoming_events()

    def get_milk_summary(self, obj):
        return obj.milk_summary()

    def get_breeding_history(self, obj):
        from breeding.models import BirthRecord

        events = obj.breeding_as_dam.all()[:20]
        pregnancies = obj.pregnancies.select_related('breeding_event').all()[:20]
        birth_qs = BirthRecord.objects.filter(pregnancy__cattle=obj).select_related(
            'pregnancy', 'calf'
        )[:20]
        return {
            'events': BreedingEventSerializer(events, many=True).data,
            'pregnancies': PregnancySerializer(pregnancies, many=True).data,
            'births': BirthRecordSerializer(birth_qs, many=True).data,
        }

    def get_recent_milk(self, obj):
        records = obj.milk_records.order_by('-date')[:14]
        return MilkRecordSerializer(records, many=True).data

    def get_alerts(self, obj):
        alerts = obj.alerts.order_by('-created_at')[:20]
        return AlertSerializer(alerts, many=True).data

    def get_upcoming_vaccinations(self, obj):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        qs = obj.vaccinations.filter(
            next_due_on__isnull=False,
            next_due_on__gte=today,
            next_due_on__lte=today + timedelta(days=60),
        ).order_by('next_due_on')
        return VaccinationSerializer(qs, many=True).data

    def get_husbandry_tasks(self, obj):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        qs = obj.husbandry_tasks.filter(
            status='PENDING',
            due_date__lte=today + timedelta(days=90),
        ).order_by('due_date')[:30]
        return HusbandryTaskSerializer(qs, many=True).data

    def get_pedigree_tree(self, obj):
        return obj.pedigree_tree()

    def get_growth_logs(self, obj):
        logs = obj.growth_logs.order_by('-date', '-created_at')[:10]
        return CattleGrowthLogSerializer(logs, many=True).data

    def get_latest_bcs(self, obj):
        log = obj.growth_logs.exclude(bcs__isnull=True).order_by('-date', '-created_at').first()
        return float(log.bcs) if log else None

    def get_latest_weight(self, obj):
        log = obj.growth_logs.exclude(weight_kg__isnull=True).order_by('-date', '-created_at').first()
        return float(log.weight_kg) if log else None
