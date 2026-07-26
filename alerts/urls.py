from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AlertViewSet, unread_count

router = DefaultRouter()
router.register('', AlertViewSet, basename='alerts')

urlpatterns = [
    path('unread-count/', unread_count, name='alerts-unread-count'),
    path('', include(router.urls)),
]
