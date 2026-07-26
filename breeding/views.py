from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser, IsOwner, IsOwnerOrVeterinarian, IsOwnerOrWorker
from core.scoping import FarmScopedQuerySetMixin
from .models import BirthRecord, BreedingEvent, Pregnancy
from .serializers import BirthRecordSerializer, BreedingEventSerializer, PregnancySerializer


class BreedingEventViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = BreedingEvent.objects.select_related('dam', 'sire').all()
    serializer_class = BreedingEventSerializer
    filterset_fields = ['dam', 'method']
    ordering_fields = ['mating_date']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAppUser()]
        if self.action == 'create':
            return [IsOwnerOrWorker()]
        return [IsOwner()]

    def perform_create(self, serializer):
        farm = require_user_farm(self.request.user)
        dam = serializer.validated_data['dam']
        if dam.farm_id != farm.id:
            raise PermissionDenied('Dam does not belong to your farm.')
        sire = serializer.validated_data.get('sire')
        if sire is not None and sire.farm_id != farm.id:
            raise PermissionDenied('Sire does not belong to your farm.')
        serializer.save(farm=farm)


class PregnancyViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Pregnancy.objects.select_related('cattle', 'breeding_event').all()
    serializer_class = PregnancySerializer
    filterset_fields = ['cattle', 'status']
    ordering_fields = ['expected_calving_date', 'created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAppUser()]
        if self.action in ('update', 'partial_update'):
            return [IsOwnerOrVeterinarian()]
        if self.action == 'create':
            return [IsOwnerOrVeterinarian()]
        return [IsOwner()]

    def perform_create(self, serializer):
        farm = require_user_farm(self.request.user)
        cattle = serializer.validated_data['cattle']
        if cattle.farm_id != farm.id:
            raise PermissionDenied('Cattle does not belong to your farm.')
        serializer.save(farm=farm)

    def perform_update(self, serializer):
        user = self.request.user
        if user.role == 'VETERINARIAN':
            allowed = {'status', 'clinical_notes', 'confirmed_on', 'expected_calving_date'}
            data_keys = set(self.request.data.keys())
            if not data_keys.issubset(allowed):
                raise PermissionDenied(
                    'Veterinarians may only update clinical pregnancy fields.'
                )
        serializer.save()


class BirthRecordViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = BirthRecord.objects.select_related('pregnancy', 'pregnancy__cattle', 'calf').all()
    serializer_class = BirthRecordSerializer
    filterset_fields = ['pregnancy', 'calving_date']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAppUser()]
        if self.action == 'create':
            return [IsOwnerOrWorker()]
        return [IsOwner()]

    def perform_create(self, serializer):
        farm = require_user_farm(self.request.user)
        pregnancy = serializer.validated_data['pregnancy']
        if pregnancy.farm_id != farm.id:
            raise PermissionDenied('Pregnancy does not belong to your farm.')
        serializer.save(farm=farm)
