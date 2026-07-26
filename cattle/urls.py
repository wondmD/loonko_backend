from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CattleViewSet

router = DefaultRouter()
router.register('', CattleViewSet, basename='cattle')

urlpatterns = [
    path('', include(router.urls)),
]
