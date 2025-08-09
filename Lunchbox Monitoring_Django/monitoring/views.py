from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Avg, Max, Min
from django.db.models.functions import TruncHour, TruncDay

from .models import Lunchbox, SensorReading, Alert
from .serializers import (
    LunchboxSerializer, 
    SensorReadingSerializer, 
    AlertSerializer,
    DashboardStatsSerializer
)
from .permissions import IsOwnerOrReadOnly

class LunchboxListCreateView(generics.ListCreateAPIView):
    """
    API endpoint that allows lunchboxes to be viewed or created.
    """
    serializer_class = LunchboxSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Lunchbox.objects.filter(owner=self.request.user, is_active=True)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class LunchboxDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint that allows a single lunchbox to be viewed, updated or deleted.
    """
    serializer_class = LunchboxSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        return Lunchbox.objects.filter(is_active=True)
    
    def perform_destroy(self, instance):
        # Soft delete
        instance.is_active = False
        instance.save()


class SensorReadingListCreateView(generics.ListCreateAPIView):
    """
    API endpoint that allows sensor readings to be viewed or created.
    """
    serializer_class = SensorReadingSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        lunchbox_id = self.kwargs['lunchbox_id']
        return SensorReading.objects.filter(
            lunchbox_id=lunchbox_id,
            lunchbox__owner=self.request.user
        ).order_by('-recorded_at')
    
    def perform_create(self, serializer):
        lunchbox = get_object_or_404(
            Lunchbox, 
            id=self.kwargs['lunchbox_id'],
            owner=self.request.user,
            is_active=True
        )
        serializer.save(lunchbox=lunchbox)
        
        # Notify WebSocket clients about the new reading
        self._notify_websocket_clients(serializer.instance)
    
    def _notify_websocket_clients(self, reading):
        """Send sensor reading to WebSocket consumers."""
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        group_name = f'lunchbox_{reading.lunchbox.id}'
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'sensor_update',
                'sensor_type': reading.sensor_type,
                'value': reading.value,
                'unit': reading.unit,
                'recorded_at': reading.recorded_at.isoformat()
            }
        )


class AlertListView(generics.ListAPIView):
    """
    API endpoint that lists all alerts for a lunchbox.
    """
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        lunchbox_id = self.kwargs['lunchbox_id']
        return Alert.objects.filter(
            lunchbox_id=lunchbox_id,
            lunchbox__owner=self.request.user
        ).order_by('-created_at')


class AlertResolveView(generics.UpdateAPIView):
    """
    API endpoint that allows resolving an alert.
    """
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        return Alert.objects.filter(
            lunchbox__owner=self.request.user,
            is_resolved=False
        )
    
    def update(self, request, *args, **kwargs):
        alert = self.get_object()
        alert.resolve()
        return Response({'status': 'alert resolved'})


class DashboardView(APIView):
    """
    API endpoint that provides dashboard statistics.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, format=None):
        user = request.user
        
        # Basic statistics
        stats = {
            'total_lunchboxes': Lunchbox.objects.filter(owner=user, is_active=True).count(),
            'active_alerts': Alert.objects.filter(
                lunchbox__owner=user, 
                is_resolved=False
            ).count(),
            'sensor_readings_today': SensorReading.objects.filter(
                lunchbox__owner=user,
                recorded_at__date=timezone.now().date()
            ).count(),
        }
        
        # Add recent alerts
        recent_alerts = Alert.objects.filter(
            lunchbox__owner=user
        ).order_by('-created_at')[:5]
        
        # Add sensor statistics
        sensor_stats = self._get_sensor_statistics(user)
        
        data = {
            'stats': stats,
            'recent_alerts': AlertSerializer(recent_alerts, many=True).data,
            'sensor_statistics': sensor_stats,
        }
        
        serializer = DashboardStatsSerializer(data)
        return Response(serializer.data)
    
    def _get_sensor_statistics(self, user):
        """Calculate statistics for sensor readings."""
        from django.db.models import Count
        
        # Get the latest readings for each sensor type
        latest_readings = {}
        for reading in SensorReading.objects.filter(
            lunchbox__owner=user
        ).order_by('sensor_type', '-recorded_at').distinct('sensor_type'):
            latest_readings[reading.sensor_type] = {
                'value': reading.value,
                'unit': reading.unit,
                'recorded_at': reading.recorded_at
            }
        
        # Calculate daily statistics for temperature (example)
        daily_stats = {}
        if 'temp' in latest_readings:
            today = timezone.now().date()
            readings = SensorReading.objects.filter(
                lunchbox__owner=user,
                sensor_type='temp',
                recorded_at__date=today
            ).annotate(
                hour=TruncHour('recorded_at')
            ).values('hour').annotate(
                avg_temp=Avg('value'),
                max_temp=Max('value'),
                min_temp=Min('value')
            ).order_by('hour')
            
            daily_stats = {
                'labels': [r['hour'].strftime('%H:%M') for r in readings],
                'avg_temps': [float(r['avg_temp']) for r in readings],
                'max_temps': [float(r['max_temp']) for r in readings],
                'min_temps': [float(r['min_temp']) for r in readings],
            }
        
        return {
            'latest_readings': latest_readings,
            'daily_stats': daily_stats
        }
