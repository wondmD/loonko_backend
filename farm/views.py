from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.farm_utils import require_user_farm
from core.permissions import IsAppUser, IsOwner
from .serializers import FarmSerializer


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
