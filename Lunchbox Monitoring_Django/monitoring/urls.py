from django.urls import path, include
from . import views
from .views_home import HomeView, DashboardTemplateView

app_name = 'monitoring'

urlpatterns = [
    # Home page
    path('', HomeView.as_view(), name='home'),
    
    # API endpoints
    path('api/', include([
        # Lunchbox endpoints
        path('lunchboxes/', views.LunchboxListCreateView.as_view(), name='lunchbox-list'),
        path('lunchboxes/<int:pk>/', views.LunchboxDetailView.as_view(), name='lunchbox-detail'),
        
        # Sensor reading endpoints
        path('lunchboxes/<int:lunchbox_id>/readings/', 
             views.SensorReadingListCreateView.as_view(), 
             name='sensor-reading-list'),
        
        # Alert endpoints
        path('alerts/', views.AlertListView.as_view(), name='alert-list'),
        path('alerts/<int:pk>/resolve/', 
             views.AlertResolveView.as_view(), 
             name='alert-resolve'),
        
        # Dashboard
        path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    ])),
    
    # Web interface
    path('dashboard/', DashboardTemplateView.as_view(), name='dashboard-ui'),
]
