from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.views.generic import TemplateView, ListView, DetailView
from django.utils import timezone
from django.db.models import Count, Q
from django.http import JsonResponse
from datetime import timedelta

from .models import Child, LunchboxAssignment, ParentNotification
from monitoring.models import SensorReading, Alert


class ParentLoginView(TemplateView):
    template_name = 'parent/login.html'
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('parent:dashboard')
        return super().get(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('parent:dashboard')
        else:
            messages.error(request, 'Invalid email or password.')
            return redirect('parent:login')


def parent_logout(request):
    logout(request)
    return redirect('parent:login')


@login_required(login_url='parent:login')
def dashboard(request):
    """Parent dashboard view showing overview of children's lunchboxes."""
    children = Child.objects.filter(parent=request.user).select_related('lunchbox_assignment')
    
    # Get recent alerts for all children
    recent_alerts = Alert.objects.filter(
        lunchbox_id__in=[child.lunchbox_assignment.lunchbox_id for child in children if hasattr(child, 'lunchbox_assignment')]
    ).order_by('-timestamp')[:5]
    
    # Get unread notifications
    unread_notifications = ParentNotification.objects.filter(
        parent=request.user,
        is_read=False
    ).order_by('-created_at') 
    
    context = {
        'children': children,
        'recent_alerts': recent_alerts,
        'unread_notifications': unread_notifications,
    }
    return render(request, 'parent/dashboard.html', context)


@login_required(login_url='parent:login')
def child_detail(request, child_id):
    """Detailed view for a specific child's lunchbox."""
    child = get_object_or_404(Child, id=child_id, parent=request.user)
    
    try:
        lunchbox = child.lunchbox_assignment
        # Get temperature readings for the last 24 hours
        time_threshold = timezone.now() - timedelta(hours=24)
        temperature_readings = TemperatureReading.objects.filter(
            lunchbox_id=lunchbox.lunchbox_id,
            timestamp__gte=time_threshold
        ).order_by('timestamp')
        
        # Get food consumption data
        food_consumption = FoodConsumption.objects.filter(
            lunchbox_id=lunchbox.lunchbox_id
        ).order_by('-timestamp').first()
        
        # Get alerts for this lunchbox
        alerts = Alert.objects.filter(
            lunchbox_id=lunchbox.lunchbox_id
        ).order_by('-timestamp')[:10]
        
    except (LunchboxAssignment.DoesNotExist, AttributeError):
        lunchbox = None
        temperature_readings = []
        food_consumption = None
        alerts = []
    
    context = {
        'child': child,
        'lunchbox': lunchbox,
        'temperature_readings': temperature_readings,
        'food_consumption': food_consumption,
        'alerts': alerts,
    }
    return render(request, 'parent/child_detail.html', context)


@login_required(login_url='parent:login')
def notifications(request):
    """View for displaying all notifications."""
    notifications = ParentNotification.objects.filter(parent=request.user).order_by('-created_at')
    
    # Mark notifications as read when viewed
    unread_notifications = notifications.filter(is_read=False)
    if unread_notifications.exists():
        unread_notifications.update(is_read=True)
    
    return render(request, 'parent/notifications.html', {'notifications': notifications})


@login_required(login_url='parent:login')
def mark_notification_read(request, notification_id):
    """Mark a notification as read via AJAX."""
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        notification = get_object_or_404(ParentNotification, id=notification_id, parent=request.user)
        notification.is_read = True
        notification.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)


@login_required(login_url='parent:login')
def get_notification_count(request):
    """Get unread notification count via AJAX."""
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        count = ParentNotification.objects.filter(
            parent=request.user,
            is_read=False
        ).count()
        return JsonResponse({'count': count})
    return JsonResponse({'status': 'error'}, status=400)


@login_required(login_url='parent:login')
def settings_view(request):
    """Parent account settings view."""
    if request.method == 'POST':
        # Handle settings form submission
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone_number = request.POST.get('phone_number', user.phone_number)
        user.address = request.POST.get('address', user.address)
        
        # Handle password change if provided
        new_password = request.POST.get('new_password')
        if new_password and len(new_password) >= 8:
            user.set_password(new_password)
            
        user.save()
        messages.success(request, 'Settings updated successfully.')
        return redirect('parent:settings')
        
    return render(request, 'parent/settings.html')
