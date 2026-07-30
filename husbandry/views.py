from datetime import timedelta

from django.db.models import F
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser, IsOwner, IsOwnerOrWorker
from core.scoping import FarmScopedQuerySetMixin
from .models import HusbandrySettings, HusbandryTask
from .serializers import (
    HusbandrySettingsSerializer,
    HusbandryTaskCompleteSerializer,
    HusbandryTaskSerializer,
)
from .services import generate_husbandry_alerts, sync_all_female_cattle, sync_cattle_husbandry


def _exclude_pre_registration(qs):
    """Ignore auto care due before the animal was added to Loonkoo."""
    return qs.annotate(
        _registered_on=TruncDate('cattle__created_at'),
    ).filter(due_date__gte=F('_registered_on'))


class HusbandryTaskViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = HusbandryTask.objects.select_related('cattle').all()
    serializer_class = HusbandryTaskSerializer
    permission_classes = [IsAppUser]
    filterset_fields = ['cattle', 'task_type', 'status', 'priority', 'is_auto']
    search_fields = ['title', 'cattle__tag_id', 'description']
    ordering_fields = ['due_date', 'priority', 'created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        female_only = self.request.query_params.get('female_only', 'true').lower()
        if female_only in ('1', 'true', 'yes'):
            qs = qs.filter(cattle__sex='FEMALE')

        today = timezone.localdate()
        due = self.request.query_params.get('due')
        if due == 'today':
            qs = qs.filter(due_date=today, status=HusbandryTask.Status.PENDING)
        elif due == 'overdue':
            qs = qs.filter(due_date__lt=today, status=HusbandryTask.Status.PENDING)
        elif due == 'upcoming':
            days = int(self.request.query_params.get('days', '14'))
            qs = qs.filter(
                status=HusbandryTask.Status.PENDING,
                due_date__gte=today,
                due_date__lte=today + timedelta(days=days),
            )
        elif due == 'open':
            qs = qs.filter(status=HusbandryTask.Status.PENDING)

        if due in ('today', 'overdue', 'upcoming', 'open'):
            qs = _exclude_pre_registration(qs)
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'board'):
            return [IsAppUser()]
        if self.action in ('create', 'complete', 'skip'):
            return [IsOwnerOrWorker()]
        if self.action in ('update', 'partial_update', 'destroy'):
            return [IsOwner()]
        return [IsAppUser()]

    def perform_create(self, serializer):
        farm = require_user_farm(self.request.user)
        cattle = serializer.validated_data['cattle']
        if cattle.farm_id != farm.id:
            raise PermissionDenied('Cattle does not belong to your farm.')
        if cattle.sex != cattle.Sex.FEMALE:
            raise ValidationError(
                {'cattle': 'Husbandry tasks are for female cattle only.'}
            )
        source_key = serializer.validated_data.get('source_key')
        if not source_key:
            tag = f'manual-{cattle.id}-{timezone.now().timestamp()}'
            serializer.save(farm=farm, is_auto=False, source_key=tag)
        else:
            serializer.save(farm=farm, is_auto=False)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        if task.status != HusbandryTask.Status.PENDING:
            raise ValidationError({'status': 'Only pending tasks can be completed.'})
        ser = HusbandryTaskCompleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        task.mark_completed(user=request.user, notes=ser.validated_data.get('notes', ''))
        sync_cattle_husbandry(task.cattle)
        return Response(HusbandryTaskSerializer(task).data)

    @action(detail=True, methods=['post'])
    def skip(self, request, pk=None):
        task = self.get_object()
        if request.user.role not in ('OWNER', 'WORKER'):
            raise PermissionDenied()
        if task.status != HusbandryTask.Status.PENDING:
            raise ValidationError({'status': 'Only pending tasks can be skipped.'})
        task.status = HusbandryTask.Status.SKIPPED
        task.completed_at = timezone.now()
        task.completed_by = request.user
        task.completion_notes = request.data.get('notes', '')
        task.save(
            update_fields=[
                'status',
                'completed_at',
                'completed_by',
                'completion_notes',
                'updated_at',
            ]
        )
        return Response(HusbandryTaskSerializer(task).data)

    @action(detail=False, methods=['get'])
    def board(self, request):
        farm = require_user_farm(request.user)
        today = timezone.localdate()
        days = int(request.query_params.get('days', '14'))
        qs = _exclude_pre_registration(
            HusbandryTask.objects.filter(
                farm=farm,
                status=HusbandryTask.Status.PENDING,
                cattle__sex='FEMALE',
                cattle__status='ACTIVE',
                due_date__lte=today + timedelta(days=days),
            )
            .select_related('cattle')
            .order_by('due_date')
        )
        overdue = qs.filter(due_date__lt=today)
        due_today = qs.filter(due_date=today)
        upcoming = qs.filter(due_date__gt=today)
        return Response(
            {
                'overdue': HusbandryTaskSerializer(overdue, many=True).data,
                'due_today': HusbandryTaskSerializer(due_today, many=True).data,
                'upcoming': HusbandryTaskSerializer(upcoming, many=True).data,
                'counts': {
                    'overdue': overdue.count(),
                    'due_today': due_today.count(),
                    'upcoming': upcoming.count(),
                },
            }
        )


class HusbandrySettingsView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAppUser()]
        return [IsOwner()]

    def get(self, request):
        farm = require_user_farm(request.user)
        return Response(
            HusbandrySettingsSerializer(HusbandrySettings.load(farm)).data
        )

    def patch(self, request):
        farm = require_user_farm(request.user)
        settings_obj = HusbandrySettings.load(farm)
        ser = HusbandrySettingsSerializer(settings_obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class HusbandrySyncView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        farm = require_user_farm(request.user)
        cattle_id = request.data.get('cattle_id')
        if cattle_id:
            from cattle.models import Cattle

            cow = Cattle.objects.get(pk=cattle_id, farm=farm)
            result = sync_cattle_husbandry(cow)
            return Response(result)
        results = sync_all_female_cattle(farm=farm)
        alerts = generate_husbandry_alerts(farm=farm)
        return Response({'synced': len(results), 'alerts_created': alerts})
