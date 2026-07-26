from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser, IsOwner
from .models import Alert
from .serializers import AlertSerializer
from .services import generate_due_alerts


ROLE_CATEGORIES = {
    'OWNER': None,
    'WORKER': [
        Alert.Category.MILK,
        Alert.Category.SYSTEM,
        Alert.Category.HEALTH,
        Alert.Category.BREEDING,
    ],
    'VETERINARIAN': [Alert.Category.HEALTH, Alert.Category.BREEDING],
}


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AlertSerializer
    permission_classes = [IsAppUser]
    filterset_fields = ['category', 'severity', 'is_read']
    ordering_fields = ['created_at', 'severity']

    def get_queryset(self):
        user = self.request.user
        farm = require_user_farm(user)
        qs = Alert.objects.select_related('cattle', 'user').filter(farm=farm).filter(
            Q(user__isnull=True) | Q(user=user)
        )
        cats = ROLE_CATEGORIES.get(user.role)
        if cats is not None:
            qs = qs.filter(category__in=cats)
        return qs

    @action(detail=True, methods=['patch'], url_path='read')
    def mark_read(self, request, pk=None):
        alert = self.get_object()
        alert.mark_read()
        return Response(AlertSerializer(alert).data)

    @action(detail=True, methods=['post'], url_path='acknowledge')
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        alert.acknowledge()
        return Response(AlertSerializer(alert).data)

    @action(detail=False, methods=['post'], url_path='generate', permission_classes=[IsOwner])
    def generate(self, request):
        farm = require_user_farm(request.user)
        created = generate_due_alerts(farm=farm)
        return Response({'created': created}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAppUser])
def unread_count(request):
    user = request.user
    farm = require_user_farm(user)
    qs = Alert.objects.filter(farm=farm, is_read=False).filter(
        Q(user__isnull=True) | Q(user=user)
    )
    cats = ROLE_CATEGORIES.get(user.role)
    if cats is not None:
        qs = qs.filter(category__in=cats)
    return Response({'unread': qs.count()})
