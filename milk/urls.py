from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FeedScheduleViewSet, MilkRecordViewSet, milk_summary, milk_trends

router = DefaultRouter()
router.register('records', MilkRecordViewSet, basename='milk-records')
router.register('feed-schedules', FeedScheduleViewSet, basename='feed-schedules')

urlpatterns = [
    path('summary/', milk_summary, name='milk-summary'),
    path('trends/', milk_trends, name='milk-trends'),
    path('', include(router.urls)),
]
