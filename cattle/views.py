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

        if self.action == 'retrieve':
            return qs.prefetch_related(
                'breeding_as_dam',
                'pregnancies',
                'milk_records',
                'alerts',
                'vaccinations',
                'husbandry_tasks',
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
