from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BirthRecordViewSet,
    BreedingEventViewSet,
    PregnancyViewSet,
    breeding_cattle_history,
    breeding_herd,
    breeding_upcoming,
)

router = DefaultRouter()
router.register('events', BreedingEventViewSet, basename='breeding-events')
router.register('pregnancies', PregnancyViewSet, basename='pregnancies')
router.register('births', BirthRecordViewSet, basename='births')

urlpatterns = [
    path('herd/', breeding_herd, name='breeding-herd'),
    path('herd/<int:cattle_id>/', breeding_cattle_history, name='breeding-cattle-history'),
    path('upcoming/', breeding_upcoming, name='breeding-upcoming'),
    path('', include(router.urls)),
]
