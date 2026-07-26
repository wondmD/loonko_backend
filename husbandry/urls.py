from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import HusbandrySettingsView, HusbandrySyncView, HusbandryTaskViewSet

router = DefaultRouter()
router.register('tasks', HusbandryTaskViewSet, basename='husbandry-task')

urlpatterns = [
    path('settings/', HusbandrySettingsView.as_view(), name='husbandry-settings'),
    path('sync/', HusbandrySyncView.as_view(), name='husbandry-sync'),
    path('', include(router.urls)),
]
