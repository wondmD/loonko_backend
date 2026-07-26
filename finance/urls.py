from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TransactionViewSet, finance_by_category, finance_summary

router = DefaultRouter()
router.register('transactions', TransactionViewSet, basename='transactions')

urlpatterns = [
    path('summary/', finance_summary, name='finance-summary'),
    path('by-category/', finance_by_category, name='finance-by-category'),
    path('', include(router.urls)),
]
