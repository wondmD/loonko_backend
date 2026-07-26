from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import HealthRecordViewSet, TreatmentViewSet, VaccinationViewSet, upcoming_vaccinations

router = DefaultRouter()
router.register('records', HealthRecordViewSet, basename='health-records')
router.register('vaccinations', VaccinationViewSet, basename='vaccinations')
router.register('treatments', TreatmentViewSet, basename='treatments')

urlpatterns = [
    path('upcoming-vaccinations/', upcoming_vaccinations, name='upcoming-vaccinations'),
    path('', include(router.urls)),
]
