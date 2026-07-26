from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser, IsOwnerOrVeterinarian
from core.scoping import FarmScopedQuerySetMixin
from .models import HealthRecord, Treatment, Vaccination
from .serializers import HealthRecordSerializer, TreatmentSerializer, VaccinationSerializer


def _stamp_farm_from_cattle(serializer, user, extra=None):
    farm = require_user_farm(user)
    cattle = serializer.validated_data['cattle']
    if cattle.farm_id != farm.id:
        raise PermissionDenied('Cattle does not belong to your farm.')
    payload = {'farm': farm}
    if extra:
        payload.update(extra)
    return serializer.save(**payload)


class HealthRecordViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = HealthRecord.objects.select_related('cattle', 'recorded_by').all()
    serializer_class = HealthRecordSerializer
    filterset_fields = ['cattle', 'severity']
    ordering_fields = ['recorded_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAppUser()]
        if self.action == 'create':
            return [IsAppUser()]
        return [IsOwnerOrVeterinarian()]

    def perform_create(self, serializer):
        if self.request.user.role not in ('OWNER', 'WORKER', 'VETERINARIAN'):
            raise PermissionDenied()
        _stamp_farm_from_cattle(
            serializer, self.request.user, {'recorded_by': self.request.user}
        )


class VaccinationViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Vaccination.objects.select_related('cattle', 'recorded_by').all()
    serializer_class = VaccinationSerializer
    filterset_fields = ['cattle']
    ordering_fields = ['administered_on', 'next_due_on']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAppUser()]
        return [IsOwnerOrVeterinarian()]

    def perform_create(self, serializer):
        _stamp_farm_from_cattle(
            serializer, self.request.user, {'recorded_by': self.request.user}
        )


class TreatmentViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Treatment.objects.select_related('cattle', 'recorded_by').all()
    serializer_class = TreatmentSerializer
    filterset_fields = ['cattle']
    ordering_fields = ['start_date']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAppUser()]
        return [IsOwnerOrVeterinarian()]

    def perform_create(self, serializer):
        _stamp_farm_from_cattle(
            serializer, self.request.user, {'recorded_by': self.request.user}
        )


@api_view(['GET'])
@permission_classes([IsAppUser])
def upcoming_vaccinations(request):
    farm = require_user_farm(request.user)
    days = int(request.query_params.get('days', settings.VACCINATION_DUE_DAYS))
    today = timezone.localdate()
    end = today + timedelta(days=days)
    qs = (
        Vaccination.objects.filter(
            farm=farm,
            next_due_on__isnull=False,
            next_due_on__gte=today,
            next_due_on__lte=end,
        )
        .select_related('cattle')
        .order_by('next_due_on')
    )
    return Response(VaccinationSerializer(qs, many=True).data)
