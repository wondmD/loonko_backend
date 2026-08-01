from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser, IsOwner
from .serializers import FarmSerializer
from rest_framework.permissions import IsAdminUser
from django.db.models import Sum, Count
from django.contrib.auth import get_user_model
from cattle.models import Cattle
from milk.models import MilkRecord


class FarmView(APIView):
    """Current user's farm only (no cross-tenant access)."""

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsOwner()]
        return [IsAppUser()]

    def get(self, request):
        farm = require_user_farm(request.user)
        return Response(FarmSerializer(farm).data)

    def patch(self, request):
        farm = require_user_farm(request.user)
        serializer = FarmSerializer(farm, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def put(self, request):
        return self.patch(request)

    def post(self, request):
        return Response(
            {'detail': 'Farm is created during registration. Use PATCH to update.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

class SupervisorAnalyticsView(APIView):
    """Global metrics for system administrators."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from .models import Farm
        User = get_user_model()
        
        total_farms = Farm.objects.count()
        total_users = User.objects.count()
        total_cattle = Cattle.objects.count()
        
        milk_aggs = MilkRecord.objects.aggregate(
            morning=Sum('morning_liters'),
            evening=Sum('evening_liters')
        )
        total_milk = (milk_aggs['morning'] or 0) + (milk_aggs['evening'] or 0)
        
        # Get list of farms with their stats
        farms_data = []
        farms = Farm.objects.annotate(
            cattle_count=Count('cattle', distinct=True),
            user_count=Count('users', distinct=True)
        ).order_by('-created_at')
        
        for f in farms:
            farms_data.append({
                'id': f.id,
                'name': f.name,
                'location': f.location,
                'created_at': f.created_at,
                'cattle_count': f.cattle_count,
                'user_count': f.user_count,
            })
            
        return Response({
            'total_farms': total_farms,
            'total_users': total_users,
            'total_cattle': total_cattle,
            'total_milk_liters': float(total_milk),
            'farms': farms_data,
        })
