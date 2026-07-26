from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.farm_utils import require_user_farm
from core.permissions import IsOwner
from .serializers import (
    EmailTokenObtainPairSerializer,
    RegisterSerializer,
    StaffSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        refresh['role'] = user.role
        refresh['email'] = user.email
        refresh['farm_id'] = user.farm_id
        return Response(
            {
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EmailTokenObtainPairSerializer


class LogoutView(APIView):
    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response({'detail': 'refresh token required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except Exception:
            return Response({'detail': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class StaffListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsOwner]
    serializer_class = StaffSerializer

    def get_queryset(self):
        farm = require_user_farm(self.request.user)
        return User.objects.filter(
            farm=farm,
            role__in=[User.Role.WORKER, User.Role.VETERINARIAN],
        ).order_by('role', 'email')


class StaffDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOwner]
    serializer_class = StaffSerializer

    def get_queryset(self):
        farm = require_user_farm(self.request.user)
        return User.objects.filter(
            farm=farm,
            role__in=[User.Role.WORKER, User.Role.VETERINARIAN],
        )

    def perform_destroy(self, instance):
        instance.is_active_staff_member = False
        instance.is_active = False
        instance.save(update_fields=['is_active_staff_member', 'is_active'])
