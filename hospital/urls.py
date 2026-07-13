from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/', include('patients.urls')),
    path('api/v1/', include('departments.urls')),
    path('api/v1/', include('tokens.urls')),
    path('api/v1/', include('notifications.urls')),
]
