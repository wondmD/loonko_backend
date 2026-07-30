from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    FeedScheduleViewSet,
    MilkRecordViewSet,
    milk_cattle_history,
    milk_herd,
    milk_summary,
    milk_trends,
)

router = DefaultRouter()
router.register('records', MilkRecordViewSet, basename='milk-records')
router.register('feed-schedules', FeedScheduleViewSet, basename='feed-schedules')

urlpatterns = [
    path('summary/', milk_summary, name='milk-summary'),
    path('trends/', milk_trends, name='milk-trends'),
    path('herd/', milk_herd, name='milk-herd'),
    path('herd/<int:cattle_id>/', milk_cattle_history, name='milk-cattle-history'),
    path('', include(router.urls)),
]
