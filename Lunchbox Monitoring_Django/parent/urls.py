from django.urls import path
from . import views

app_name = 'parent'

urlpatterns = [
    # Authentication
    path('login/', views.ParentLoginView.as_view(), name='login'),
    path('logout/', views.parent_logout, name='logout'),
    
    # Dashboard and child views
    path('', views.dashboard, name='dashboard'),
    path('child/<int:child_id>/', views.child_detail, name='child_detail'),
    
    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/count/', views.get_notification_count, name='notification_count'),
    
    # Settings
    path('settings/', views.settings_view, name='settings'),
]
