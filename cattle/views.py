from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser
from core.scoping import FarmScopedQuerySetMixin
from .herd_filters import apply_category_filter, apply_herd_filter, herd_facet_counts
from .models import Cattle
from .serializers import (
    CattleDetailSerializer,
    CattleSerializer,
    CattleWorkerUpdateSerializer,
)


class CattleViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Cattle.objects.select_related('mother', 'father').all()
    permission_classes = [IsAppUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ['status', 'sex', 'breed']
    search_fields = ['tag_id', 'name', 'breed']
    ordering_fields = ['tag_id', 'date_of_birth', 'created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        sex = self.request.query_params.get('sex')
        if sex and sex.upper() not in ('', 'ALL'):
            qs = qs.filter(sex=sex.upper())

        if self.action == 'list':
            category = self.request.query_params.get('category')
            herd_filter = self.request.query_params.get('herd_filter')
            qs = apply_category_filter(qs, category)
            qs = apply_herd_filter(qs, herd_filter)
            
        if self.action in ('list', 'retrieve'):
            qs = qs.prefetch_related(
                'breeding_as_dam',
                'pregnancies',
                'pregnancies__birth',
                'husbandry_tasks',
            )

        if self.action == 'retrieve':
            return qs.prefetch_related(
                'milk_records',
                'alerts',
                'vaccinations',
            )
        return qs

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset)

    def get_serializer_class(self):
        user = self.request.user
        if self.action == 'retrieve':
            return CattleDetailSerializer
        if self.action in ('partial_update', 'update') and user.role == 'WORKER':
            return CattleWorkerUpdateSerializer
        return CattleSerializer

    @action(detail=False, methods=['get'])
    def facets(self, request):
        farm = require_user_farm(request.user)
        qs = Cattle.objects.filter(farm=farm)
        sex = request.query_params.get('sex')
        if sex and sex.upper() not in ('', 'ALL'):
            qs = qs.filter(sex=sex.upper())
        return Response(herd_facet_counts(qs))

    def create(self, request, *args, **kwargs):
        if request.user.role == 'VETERINARIAN':
            raise PermissionDenied('Veterinarians cannot create cattle.')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if request.user.role == 'VETERINARIAN':
            raise PermissionDenied('Veterinarians have read-only cattle access.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if request.user.role != 'OWNER':
            raise PermissionDenied('Only the owner can delete cattle.')
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get', 'post'])
    def growth(self, request, pk=None):
        cattle = self.get_object()
        from .models import CattleGrowthLog
        from .serializers import CattleGrowthLogSerializer
        from .growth_services import log_cattle_growth

        if request.method == 'GET':
            logs = CattleGrowthLog.objects.filter(cattle=cattle).order_by('-date', '-created_at')
            return Response(CattleGrowthLogSerializer(logs, many=True).data)

        if request.user.role == 'VETERINARIAN':
            raise PermissionDenied('Veterinarians have read-only access to growth logs.')
            
        weight_kg = request.data.get('weight_kg')
        bcs = request.data.get('bcs')
        date = request.data.get('date')
        notes = request.data.get('notes', '')
        
        log = log_cattle_growth(
            cattle=cattle,
            weight_kg=weight_kg,
            bcs=bcs,
            date=date,
            recorded_by=request.user,
            notes=notes,
        )
        return Response(CattleGrowthLogSerializer(log).data, status=201)

    @action(detail=True, methods=['get'])
    def inbreeding_check(self, request, pk=None):
        dam = self.get_object()
        sire_id = request.query_params.get('sire_id')
        if not sire_id:
            return Response({'error': 'sire_id query parameter is required.'}, status=400)
            
        try:
            sire = Cattle.objects.get(id=sire_id, farm=dam.farm)
        except Cattle.DoesNotExist:
            return Response({'error': 'Sire not found.'}, status=404)
            
        from .inbreeding import check_inbreeding_risk
        return Response(check_inbreeding_risk(dam, sire))

    @action(detail=True, methods=['post'])
    def dry_off(self, request, pk=None):
        cow = self.get_object()
        if cow.sex != cow.Sex.FEMALE:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'Only female cattle can be dried off.'})
        
        from husbandry.models import HusbandryTask
        from django.utils import timezone
        
        # Complete pending dry-off tasks
        pending_dry = cow.husbandry_tasks.filter(
            task_type=HusbandryTask.TaskType.DRY_OFF, 
            status=HusbandryTask.Status.PENDING
        )
        if pending_dry.exists():
            for task in pending_dry:
                task.mark_completed(user=request.user, notes='Manually dried off via action.')
        else:
            # Create a completed one
            HusbandryTask.objects.create(
                farm=cow.farm,
                cattle=cow,
                task_type=HusbandryTask.TaskType.DRY_OFF,
                title='Manual Dry-off',
                due_date=timezone.localdate(),
                status=HusbandryTask.Status.COMPLETED,
                completed_at=timezone.now(),
                completed_by=request.user,
                is_auto=False,
                source_key=f'manual-dry-off-{cow.id}-{timezone.now().timestamp()}'
            )
            
        # Dismiss related alerts
        cow.alerts.filter(is_read=False, title__icontains='Dry-off').update(is_read=True)
        cow.alerts.filter(is_read=False, title__icontains='Dry-off').update(is_read=True)
        
        return Response({'status': 'dried_off'})
