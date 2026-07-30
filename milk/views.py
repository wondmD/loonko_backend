from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser, IsOwnerOrWorker
from core.scoping import FarmScopedQuerySetMixin
from .models import FeedSchedule, MilkRecord, cow_recent_average
from .serializers import FeedScheduleSerializer, MilkRecordSerializer


class MilkRecordViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = MilkRecord.objects.select_related('cattle', 'recorded_by').all()
    serializer_class = MilkRecordSerializer
    filterset_fields = ['cattle', 'date']
    ordering_fields = ['date', 'created_at']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwnerOrWorker()]
        return [IsAppUser()]

    def perform_create(self, serializer):
        farm = require_user_farm(self.request.user)
        cattle = serializer.validated_data['cattle']
        if cattle.farm_id != farm.id:
            raise PermissionDenied('Cattle does not belong to your farm.')
        record = serializer.save(farm=farm, recorded_by=self.request.user)
        self._maybe_low_milk_alert(record)
        from milk.services import clear_missed_milk_alert

        clear_missed_milk_alert(record)

    def perform_update(self, serializer):
        record = serializer.save()
        self._maybe_low_milk_alert(record)
        from milk.services import clear_missed_milk_alert

        clear_missed_milk_alert(record)

    def destroy(self, request, *args, **kwargs):
        if request.user.role == 'WORKER':
            obj = self.get_object()
            if obj.recorded_by_id != request.user.id:
                raise PermissionDenied('Workers can only delete their own milk records.')
        return super().destroy(request, *args, **kwargs)

    def _maybe_low_milk_alert(self, record):
        from alerts.services import create_alert_if_new

        avg = cow_recent_average(record.cattle, record.date)
        if avg is None:
            return
        ratio = Decimal(str(settings.LOW_MILK_THRESHOLD_RATIO))
        total = Decimal(record.total_liters)
        if total < (Decimal(avg) * ratio):
            create_alert_if_new(
                category='MILK',
                severity='WARNING',
                title=f'Low milk yield: {record.cattle.tag_id}',
                message=(
                    f'{record.cattle.tag_id} produced {total}L on {record.date}, '
                    f'below {ratio * 100:.0f}% of recent average ({avg:.2f}L).'
                ),
                cattle=record.cattle,
                farm=record.farm,
                dedupe_key=f'milk-low-{record.cattle_id}-{record.date}',
            )


class FeedScheduleViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = FeedSchedule.objects.select_related('cattle').all()
    serializer_class = FeedScheduleSerializer
    filterset_fields = ['cattle', 'date', 'feed_type']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwnerOrWorker()]
        return [IsAppUser()]

    def perform_create(self, serializer):
        farm = require_user_farm(self.request.user)
        cattle = serializer.validated_data.get('cattle')
        if cattle is not None and cattle.farm_id != farm.id:
            raise PermissionDenied('Cattle does not belong to your farm.')
        serializer.save(farm=farm)


@api_view(['GET'])
@permission_classes([IsAppUser])
def milk_herd(request):
    """Cattle milking overview table for the milk page."""
    farm = require_user_farm(request.user)
    from .services import herd_milk_overview

    return Response(herd_milk_overview(farm))


@api_view(['GET'])
@permission_classes([IsAppUser])
def milk_cattle_history(request, cattle_id):
    """Milk record history for one cow, grouped by calving cycle."""
    from cattle.models import Cattle

    from .services import cattle_milk_history_by_cycle

    farm = require_user_farm(request.user)
    try:
        cattle = Cattle.objects.get(pk=cattle_id, farm=farm)
    except Cattle.DoesNotExist:
        return Response({'detail': 'Cattle not found.'}, status=404)
    return Response(cattle_milk_history_by_cycle(cattle))


@api_view(['GET'])
@permission_classes([IsAppUser])
def milk_summary(request):
    farm = require_user_farm(request.user)
    today = timezone.localdate()
    qs = MilkRecord.objects.filter(farm=farm)
    period = request.query_params.get('period', 'day')

    if period == 'week':
        start = today - timedelta(days=7)
    elif period == 'month':
        start = today - timedelta(days=30)
    else:
        start = today

    filtered = qs.filter(date__gte=start, date__lte=today)
    annotated = filtered.annotate(total=F('morning_liters') + F('evening_liters'))
    total = annotated.aggregate(s=Sum('total'))['s'] or 0
    by_cattle = (
        annotated.values('cattle_id', 'cattle__tag_id')
        .annotate(liters=Sum('total'))
        .order_by('-liters')
    )
    return Response(
        {
            'period': period,
            'start': start,
            'end': today,
            'total_liters': total,
            'record_count': filtered.count(),
            'by_cattle': list(by_cattle),
        }
    )


@api_view(['GET'])
@permission_classes([IsAppUser])
def milk_trends(request):
    farm = require_user_farm(request.user)
    today = timezone.localdate()
    days = int(request.query_params.get('days', 30))
    group = request.query_params.get('group', 'day')
    start = today - timedelta(days=days)
    daily = (
        MilkRecord.objects.filter(farm=farm, date__gte=start, date__lte=today)
        .annotate(total=F('morning_liters') + F('evening_liters'))
        .values('date')
        .annotate(liters=Sum('total'))
        .order_by('date')
    )

    if group == 'day':
        points = [{'date': row['date'], 'liters': row['liters']} for row in daily]
    else:
        buckets = defaultdict(lambda: Decimal('0'))
        for row in daily:
            d = row['date']
            liters = row['liters'] or Decimal('0')
            if group == 'week':
                bucket = d - timedelta(days=d.weekday())
            elif group == 'month':
                bucket = d.replace(day=1)
            else:
                bucket = d
            buckets[bucket] += liters
        points = [
            {'date': bucket, 'liters': liters}
            for bucket, liters in sorted(buckets.items())
        ]

    return Response(
        {
            'group': group,
            'start': start,
            'end': today,
            'points': points,
        }
    )
