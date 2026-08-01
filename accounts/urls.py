from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    StaffDeactivateView,
    StaffDetailView,
    StaffListCreateView,
    VerifyEmailView,
    SetPasswordView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('verify-email/', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('set-password/', SetPasswordView.as_view(), name='auth-set-password'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('staff/', StaffListCreateView.as_view(), name='auth-staff-list'),
    path('staff/<int:pk>/', StaffDetailView.as_view(), name='auth-staff-detail'),
    path('staff/<int:pk>/deactivate/', StaffDeactivateView.as_view(), name='auth-staff-deactivate'),
]
