from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BirthRecordViewSet, BreedingEventViewSet, PregnancyViewSet

router = DefaultRouter()
router.register('events', BreedingEventViewSet, basename='breeding-events')
router.register('pregnancies', PregnancyViewSet, basename='pregnancies')
router.register('births', BirthRecordViewSet, basename='births')

urlpatterns = [
    path('', include(router.urls)),
]
