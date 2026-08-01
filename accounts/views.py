from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.auth.tokens import default_token_generator

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
        return Response(
            {'detail': 'Registration successful. Please check your email to verify your account.'},
            status=status.HTTP_201_CREATED,
        )

class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        
        if not uidb64 or not token:
            return Response({'detail': 'Missing uid or token'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
            
        if user is not None and default_token_generator.check_token(user, token):
            user.is_active = True
            user.save()
            return Response({'detail': 'Email verified successfully.'})
        else:
            return Response({'detail': 'Invalid verification link.'}, status=status.HTTP_400_BAD_REQUEST)

class SetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        password = request.data.get('password')
        
        if not uidb64 or not token or not password:
            return Response({'detail': 'Missing parameters'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
            
        if user is not None and default_token_generator.check_token(user, token):
            user.set_password(password)
            user.is_active = True
            user.save()
            return Response({'detail': 'Password set successfully.'})
        else:
            return Response({'detail': 'Invalid or expired link.'}, status=status.HTTP_400_BAD_REQUEST)


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
        instance.delete()


class StaffDeactivateView(generics.GenericAPIView):
    permission_classes = [IsOwner]
    serializer_class = StaffSerializer

    def get_queryset(self):
        farm = require_user_farm(self.request.user)
        return User.objects.filter(
            farm=farm,
            role__in=[User.Role.WORKER, User.Role.VETERINARIAN],
        )

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active_staff_member = False
        instance.is_active = False
        instance.save(update_fields=['is_active_staff_member', 'is_active'])
        return Response(self.get_serializer(instance).data)
