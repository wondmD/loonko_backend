from django.urls import path

from .views import FarmView, SupervisorAnalyticsView

urlpatterns = [
    path('supervisor/', SupervisorAnalyticsView.as_view(), name='supervisor-analytics'),
    path('', FarmView.as_view(), name='farm-profile'),
]
