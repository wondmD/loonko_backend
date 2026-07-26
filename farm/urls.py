from django.urls import path

from .views import FarmView

urlpatterns = [
    path('', FarmView.as_view(), name='farm-profile'),
]
