from rest_framework import viewsets, status, permissions, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from monitoring.models import Lunchbox, SensorReading, Alert
from simulation.models import SimulationRun, SimulationSettings
from .serializers import (
    UserSerializer, LunchboxSerializer, SensorReadingSerializer,
    AlertSerializer, SimulationRunSerializer, SimulationSettingsSerializer
)
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from django.core.management import call_command
from django.db import transaction
import json

User = get_user_model()

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to edit objects.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows users to be viewed.
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

class LunchboxViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows lunchboxes to be viewed or edited.
    """
    queryset = Lunchbox.objects.all().order_by('-created_at')
    serializer_class = LunchboxSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    
    def get_queryset(self):
        """
        Optionally filter by user ownership if not admin.
        """
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            # Non-admin users can only see their own lunchboxes
            queryset = queryset.filter(owner=self.request.user)
        return queryset

class SensorReadingViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows sensor readings to be viewed.

    This viewset provides a list of sensor readings and allows filtering by lunchbox ID.
    """
    queryset = SensorReading.objects.all()
    serializer_class = SensorReadingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter sensor readings based on user permissions.
        """
        queryset = SensorReading.objects.select_related('lunchbox').order_by('-timestamp')
        
        # Filter by lunchbox if specified
        lunchbox_id = self.request.query_params.get('lunchbox_id')
        if lunchbox_id:
            queryset = queryset.filter(lunchbox_id=lunchbox_id)
        
        # Apply permission filtering
        if not self.request.user.is_staff:
            # Non-admin users can only see readings from their own lunchboxes
            queryset = queryset.filter(lunchbox__owner=self.request.user)
            
        return queryset

class AlertViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows alerts to be viewed and managed.
    """
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter alerts based on user permissions.
        """
        queryset = Alert.objects.select_related('lunchbox').order_by('-created_at')
        
        # Filter by resolved status if specified
        is_resolved = self.request.query_params.get('is_resolved')
        if is_resolved is not None:
            queryset = queryset.filter(is_resolved=json.loads(is_resolved.lower()))
        
        # Apply permission filtering
        if not self.request.user.is_staff:
            # Non-admin users can only see alerts for their own lunchboxes
            queryset = queryset.filter(lunchbox__owner=self.request.user)
            
        return queryset
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """
        Mark an alert as resolved.
        """
        alert = self.get_object()
        if not alert.is_resolved:
            alert.resolve()
            return Response({'status': 'alert resolved'})
        return Response({'status': 'alert was already resolved'}, status=status.HTTP_400_BAD_REQUEST)

class SimulationRunViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows simulation runs to be viewed and managed.
    """
    queryset = SimulationRun.objects.all()
    serializer_class = SimulationRunSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter simulation runs based on user permissions.
        """
        queryset = SimulationRun.objects.select_related('started_by').order_by('-start_time')
        
        # Filter by status if specified
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
            
        return queryset
    
    def perform_create(self, serializer):
        """
        Set the user who started the simulation.
        """
        serializer.save(started_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """
        Stop a running simulation.
        """
        simulation_run = self.get_object()
        if simulation_run.status == SimulationRun.RUNNING:
            simulation_run.stop()
            return Response({'status': 'simulation stopped'})
        return Response(
            {'status': f'simulation is not running (current status: {simulation_run.get_status_display()})'},
            status=status.HTTP_400_BAD_REQUEST
        )

class DashboardStatsView(APIView):
    """
    API endpoint that provides dashboard statistics.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, format=None):
        from django.db.models import Count, Avg, Q, F, Max, Min
        from django.utils import timezone
        from datetime import timedelta
        
        # Base querysets
        lunchboxes = Lunchbox.objects.all()
        sensor_readings = SensorReading.objects.all()
        alerts = Alert.objects.all()
        
        # Apply permission filtering
        if not request.user.is_staff:
            lunchboxes = lunchboxes.filter(owner=request.user)
            sensor_readings = sensor_readings.filter(lunchbox__owner=request.user)
            alerts = alerts.filter(lunchbox__owner=request.user)
        
        # Get counts
        stats = {
            'total_lunchboxes': lunchboxes.count(),
            'active_lunchboxes': lunchboxes.filter(is_active=True).count(),
            'total_sensor_readings': sensor_readings.count(),
            'active_alerts': alerts.filter(is_resolved=False).count(),
        }
        
        # Get temperature statistics (last 24 hours)
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
        recent_readings = sensor_readings.filter(timestamp__gte=twenty_four_hours_ago)
        
        if recent_readings.exists():
            temp_stats = recent_readings.aggregate(
                avg_temp=Avg('temperature'),
                max_temp=Max('temperature'),
                min_temp=Min('temperature')
            )
            stats.update({
                'avg_temperature': round(temp_stats['avg_temp'], 2) if temp_stats['avg_temp'] else None,
                'max_temperature': round(temp_stats['max_temp'], 2) if temp_stats['max_temp'] else None,
                'min_temperature': round(temp_stats['min_temp'], 2) if temp_stats['min_temp'] else None,
            })
        
        # Get alert statistics
        alert_stats = alerts.aggregate(
            total=Count('id'),
            resolved=Count('id', filter=Q(is_resolved=True)),
            critical=Count('id', filter=Q(severity=Alert.CRITICAL)),
            warning=Count('id', filter=Q(severity=Alert.WARNING)),
        )
        stats.update({
            'total_alerts': alert_stats['total'],
            'resolved_alerts': alert_stats['resolved'],
            'critical_alerts': alert_stats['critical'],
            'warning_alerts': alert_stats['warning'],
        })
        
        # Get recent alerts (last 5)
        recent_alerts = alerts.order_by('-created_at')[:5]
        stats['recent_alerts'] = [
            {
                'id': alert.id,
                'message': alert.message,
                'severity': alert.severity,
                'created_at': alert.created_at,
                'is_resolved': alert.is_resolved,
                'lunchbox': {
                    'id': alert.lunchbox.id,
                    'name': alert.lunchbox.name,
                } if alert.lunchbox else None
            }
            for alert in recent_alerts
        ]
        
        # Get sensor readings for the last 24 hours (for charts)
        time_series = []
        for hour in range(24, 0, -1):
            time_end = timezone.now() - timedelta(hours=hour-1)
            time_start = time_end - timedelta(hours=1)
            
            hour_readings = recent_readings.filter(
                timestamp__gte=time_start,
                timestamp__lt=time_end
            )
            
            if hour_readings.exists():
                hour_stats = hour_readings.aggregate(
                    avg_temp=Avg('temperature'),
                    avg_humidity=Avg('humidity'),
                    count=Count('id')
                )
                
                time_series.append({
                    'time': time_start.strftime('%H:%M'),
                    'timestamp': time_start.isoformat(),
                    'temperature': round(hour_stats['avg_temp'], 2) if hour_stats['avg_temp'] else None,
                    'humidity': round(hour_stats['avg_humidity'], 2) if hour_stats['avg_humidity'] else None,
                    'readings_count': hour_stats['count']
                })
        
        stats['time_series'] = time_series
        
        return Response(stats)

class SimulationSettingsViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows simulation settings to be viewed and edited.
    """
    serializer_class = SimulationSettingsSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        """
        Return the singleton settings instance.
        """
        return SimulationSettings.objects.all()
    
    def get_object(self):
        """
        Return the singleton settings instance, creating it if it doesn't exist.
        """
        return SimulationSettings.load()
    
    @action(detail=False, methods=['post'])
    def start_simulation(self, request):
        """
        Start a new simulation run with the current settings.
        """
        settings = self.get_object()
        
        # Check if there's already a running simulation
        if SimulationRun.objects.filter(status=SimulationRun.RUNNING).exists():
            return Response(
                {'error': 'A simulation is already running'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create a new simulation run
        simulation_run = SimulationRun.objects.create(
            started_by=request.user,
            duration_minutes=settings.default_duration,
            interval_seconds=settings.default_interval,
            status=SimulationRun.RUNNING
        )
        
        # Start the simulation in the background
        from simulation.tasks import generate_sensor_readings
        generate_sensor_readings.delay(simulation_run_id=simulation_run.id)
        
        # Return the simulation run details
        serializer = self.get_serializer(simulation_run)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
