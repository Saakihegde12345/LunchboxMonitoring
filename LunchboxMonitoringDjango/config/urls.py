"""lunchbox_monitoring URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework.schemas import get_schema_view as get_schema_view_rest
from rest_framework.documentation import include_docs_urls
from monitoring.views import DeviceIngestView  # Expose device ingest at top-level /api/

# Import the custom admin site
from django.contrib import admin as default_admin

API_TITLE = 'Lunchbox Monitoring API'
API_DESCRIPTION = 'A Web API for monitoring lunchbox conditions and managing simulations.'

# API Schema
schema_view = get_schema_view(
    openapi.Info(
        title="Lunchbox Monitoring API",
        default_version='v1',
        description="API for Lunchbox Monitoring System",
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="MIT License"),
    ),
    # Require authentication to view interactive API docs
    public=False,
    permission_classes=(permissions.IsAuthenticated,),
)

urlpatterns = [
    # Admin - using our custom admin site
    path('admin/', default_admin.site.urls),
    
    # API Documentation
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Device ingest (make explicit to avoid nested /monitoring/api/ conflicts)
    path('api/ingest/device/', DeviceIngestView.as_view(), name='device-ingest'),

    # API Endpoints
    path('api/', include('api.urls')),
    
    # Parent Portal
    path('parent/', include('parent.urls', namespace='parent')),
    
    # Monitoring App (public pages)
    path('', include('monitoring.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Debug Toolbar
    import debug_toolbar
    
    # Make sure to include the admin site in the debug toolbar URLs
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
