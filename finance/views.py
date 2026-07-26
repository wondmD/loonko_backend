from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.farm_utils import require_user_farm
from core.permissions import IsOwner
from core.scoping import FarmScopedQuerySetMixin
from .models import Transaction
from .serializers import TransactionSerializer
from .services import finance_period_totals, milk_finance_snapshot


class TransactionViewSet(FarmScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related('recorded_by', 'related_milk_record').all()
    serializer_class = TransactionSerializer
    permission_classes = [IsOwner]
    filterset_fields = ['type', 'category', 'date', 'is_auto']
    ordering_fields = ['date', 'amount', 'created_at']

    def perform_create(self, serializer):
        farm = require_user_farm(self.request.user)
        serializer.save(
            farm=farm,
            recorded_by=self.request.user,
            is_auto=False,
            source_key=None,
        )

    def perform_update(self, serializer):
        if serializer.instance.is_auto:
            raise PermissionDenied(
                'Cannot edit auto milk-income rows. Change milk price in Settings '
                'or edit milk records instead.'
            )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_auto:
            raise PermissionDenied(
                'Cannot delete auto milk-income rows. Disable auto milk income '
                'or change milk records / price in Settings.'
            )
        instance.delete()


@api_view(['GET'])
@permission_classes([IsOwner])
def finance_summary(request):
    farm = require_user_farm(request.user)
    days = int(request.query_params.get('days', 30))
    totals = finance_period_totals(farm, days=days)
    milk_snap = milk_finance_snapshot(farm, days=days)
    return Response(
        {
            'start': totals['start'],
            'end': totals['end'],
            'income': totals['income'],
            'expense': totals['expense'],
            'profit': totals['profit'],
            'mode': totals['mode'],
            'currency': milk_snap['currency'],
            'milk': milk_snap,
        }
    )


@api_view(['GET'])
@permission_classes([IsOwner])
def finance_by_category(request):
    farm = require_user_farm(request.user)
    today = timezone.localdate()
    days = int(request.query_params.get('days', 30))
    start = today - timedelta(days=days)
    qs = (
        Transaction.objects.filter(farm=farm, date__gte=start, date__lte=today)
        .values('type', 'category')
        .annotate(total=Sum('amount'))
        .order_by('type', 'category')
    )
    return Response({'start': start, 'end': today, 'breakdown': list(qs)})
