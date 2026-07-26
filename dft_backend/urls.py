from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/farm/', include('farm.urls')),
    path('api/cattle/', include('cattle.urls')),
    path('api/milk/', include('milk.urls')),
    path('api/health/', include('health.urls')),
    path('api/breeding/', include('breeding.urls')),
    path('api/husbandry/', include('husbandry.urls')),
    path('api/finance/', include('finance.urls')),
    path('api/alerts/', include('alerts.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
