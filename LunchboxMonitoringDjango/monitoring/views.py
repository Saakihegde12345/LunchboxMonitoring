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
    DashboardStatsSerializer,
    DeviceIngestReadingSerializer
)
from .permissions import IsOwnerOrReadOnly
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import Throttled
from django.conf import settings
from .throttles import DeviceIngestThrottle

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


class LunchboxDetailDataView(APIView):
    """Lightweight JSON detail + recent readings for modal display on dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request, lunchbox_id):
        # Ensure ownership
        lb = get_object_or_404(Lunchbox, id=lunchbox_id, owner=request.user, is_active=True)
    # Latest readings per sensor type (DB-agnostic; avoid distinct(field) which is Postgres-only)
        latest = {}
        ordered = SensorReading.objects.filter(lunchbox=lb).order_by('sensor_type', '-recorded_at')
        for r in ordered:
            if r.sensor_type not in latest:  # first encountered is latest due to -recorded_at within sensor grouping
                latest[r.sensor_type] = {
                    'value': r.value,
                    'unit': r.unit,
                    'recorded_at': r.recorded_at.isoformat()
                }
        # Recent history (last 15 readings regardless of type)
        recent_qs = SensorReading.objects.filter(lunchbox=lb).order_by('-recorded_at')[:15]
        history = [
            {
                'sensor_type': r.sensor_type,
                'label': r.get_sensor_type_display(),
                'value': r.value,
                'unit': r.unit,
                'recorded_at': r.recorded_at.isoformat(),
            }
            for r in recent_qs
        ]
        return Response({
            'lunchbox': {
                'id': lb.id,
                'name': lb.name,
                'description': lb.description,
            },
            'latest': latest,
            'recent_history': history,
        })

class LunchboxStatusList(APIView):
    """Return lightweight status for all of the authenticated user's active lunchboxes.

    Used for periodic dashboard polling to update readings & last_updated without full page reload.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lbs = Lunchbox.objects.filter(owner=request.user, is_active=True).order_by('id')
        # Fetch latest readings for all in one query
        readings = (
            SensorReading.objects
            .filter(lunchbox__in=lbs)
            .order_by('lunchbox_id', 'sensor_type', '-recorded_at')
        )
        latest_map = {}
        for r in readings:
            key = (r.lunchbox_id, r.sensor_type)
            if key not in latest_map:  # first is latest per ordering
                latest_map[key] = r
        data = []
        from django.utils.timezone import now as tznow
        current_time = tznow().isoformat()
        for lb in lbs:
            temp = latest_map.get((lb.id, SensorReading.TEMPERATURE))
            humi = latest_map.get((lb.id, SensorReading.HUMIDITY))
            gas = latest_map.get((lb.id, SensorReading.GAS))
            batt = latest_map.get((lb.id, SensorReading.BATTERY))
            prox = latest_map.get((lb.id, SensorReading.PROXIMITY))
            motion = latest_map.get((lb.id, SensorReading.MOTION))
            latest_dt_candidates = [r.recorded_at for r in (temp, humi, gas, batt, prox, motion) if r]
            last_updated = max(latest_dt_candidates).isoformat() if latest_dt_candidates else None
            data.append({
                'id': lb.id,
                'name': lb.name,
                'temp': temp.value if temp else None,
                'temp_unit': temp.unit if temp else None,
                'humi': humi.value if humi else None,
                'humi_unit': humi.unit if humi else None,
                'gas': gas.value if gas else None,
                'gas_unit': gas.unit if gas else None,
                'batt': batt.value if batt else None,
                'batt_unit': batt.unit if batt else None,
                'prox': prox.value if prox else None,
                'prox_unit': prox.unit if prox else None,
                'motion': (float(motion.value) > 0.0) if motion else None,
                'last_updated': last_updated,
            })
        return Response({'current_time': current_time, 'lunchboxes': data})


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


from rest_framework.pagination import LimitOffsetPagination

class AlertPagination(LimitOffsetPagination):
    default_limit = 10
    max_limit = 50

class AlertListView(generics.ListAPIView):
    """
    API endpoint that lists all alerts for the authenticated user, paginated.
    """
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = AlertPagination

    def get_queryset(self):
        # Base: all alerts for this user
        qs = Alert.objects.filter(
            lunchbox__owner=self.request.user
        ).order_by('-created_at')

        params = self.request.query_params
        # Filter by resolution status
        is_resolved = params.get('is_resolved')
        if is_resolved is not None:
            val = str(is_resolved).strip().lower()
            if val in ('1', 'true', 'yes'): qs = qs.filter(is_resolved=True)
            elif val in ('0', 'false', 'no'): qs = qs.filter(is_resolved=False)

        # Filter by lunchbox id
        lunchbox_id = params.get('lunchbox') or params.get('lunchbox_id')
        if lunchbox_id:
            try:
                qs = qs.filter(lunchbox_id=int(lunchbox_id))
            except (TypeError, ValueError):
                pass

        # Filter by alert_type / severity
        alert_type = params.get('alert_type')
        if alert_type:
            qs = qs.filter(alert_type=alert_type)
        severity = params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)

        # Text search in message
        q = params.get('q')
        if q:
            qs = qs.filter(message__icontains=q)

        # Date range on created_at: from/to (accept date or datetime)
        from django.utils.dateparse import parse_datetime, parse_date
        from datetime import datetime, time
        from django.utils import timezone as dj_tz

        start_s = params.get('from') or params.get('start')
        end_s = params.get('to') or params.get('end')
        if start_s:
            dt = parse_datetime(start_s)
            if not dt:
                d = parse_date(start_s)
                if d:
                    dt = datetime.combine(d, time.min)
            if dt:
                if dj_tz.is_naive(dt):
                    dt = dj_tz.make_aware(dt, dj_tz.get_current_timezone())
                qs = qs.filter(created_at__gte=dt)
        if end_s:
            dt = parse_datetime(end_s)
            if not dt:
                d = parse_date(end_s)
                if d:
                    dt = datetime.combine(d, time.max)
            if dt:
                if dj_tz.is_naive(dt):
                    dt = dj_tz.make_aware(dt, dj_tz.get_current_timezone())
                qs = qs.filter(created_at__lte=dt)

        return qs


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


class DeviceIngestView(APIView):
    """Endpoint for IoT devices to push sensor readings directly.

    Authentication: device_api_key passed in JSON body as api_key.
    This keeps device simple (single credential) and avoids per-reading auth headers.
    Throttling: uses default user anonymous throttle (optionally adjust later).
    """
    authentication_classes = []  # We'll authenticate via api_key field
    permission_classes = []
    throttle_classes = [DeviceIngestThrottle]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        # Optional shared secret header check (when configured)
        shared_secret = getattr(settings, 'DEVICE_INGEST_SHARED_SECRET', '')
        if shared_secret:
            header_secret = request.headers.get('X-Device-Secret') or request.META.get('HTTP_X_DEVICE_SECRET')
            if header_secret != shared_secret:
                logger.warning("Device ingest blocked by shared secret mismatch ip=%s", request.META.get('REMOTE_ADDR'))
                return Response({'detail': 'Invalid device secret'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = DeviceIngestReadingSerializer(data=request.data)
        if not serializer.is_valid():
            # Log invalid payload details (truncated) to help diagnose device issues
            raw_body = str(request.data)
            if len(raw_body) > 500:
                raw_body = raw_body[:500] + '...'
            logger.warning("Device ingest invalid payload ip=%s errors=%s body=%s", request.META.get('REMOTE_ADDR'), serializer.errors, raw_body)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        created = serializer.save()

        # Log source metadata
        remote_ip = request.META.get('REMOTE_ADDR')
        agent = request.META.get('HTTP_X_DEVICE_AGENT') or request.META.get('HTTP_USER_AGENT') or 'unknown'
        logger.info(
            "Device ingest: lunchbox=%s count=%s ip=%s agent=%s",
            serializer.validated_data.get('lunchbox').id,
            len(created),
            remote_ip,
            agent[:120]
        )

        # --- Simple alert threshold evaluation (initial minimal rules) ---
        THRESHOLDS = {
            'temp_high': 30.0,  # Celsius
            'humi_high': 75.0,  # Percent
            'gas_high': 200.0,  # ppm
            'batt_low': 20.0,   # Percent
            'prox_near': 10.0,  # cm
        }
        # Only (re)broadcast existing unresolved alerts if they are recent
        from datetime import timedelta
        recent_cutoff = timezone.now() - timedelta(hours=72)

        lunchbox = serializer.validated_data.get('lunchbox')
        alert_events = []
        try:
            latest_batch = {}
            for r in created:
                latest_batch[r.sensor_type] = r  # keep last occurrence per type in this POST

            # Temperature high
            temp_r = latest_batch.get(SensorReading.TEMPERATURE)
            if temp_r and temp_r.value > THRESHOLDS['temp_high']:
                existing = Alert.objects.filter(lunchbox=lunchbox, alert_type=Alert.TEMPERATURE_HIGH, is_resolved=False).order_by('-created_at').first()
                if existing and existing.created_at >= recent_cutoff:
                    # Broadcast existing recent alert so UI reflects current state
                    alert_events.append(existing)
                else:
                    alert_events.append(Alert.objects.create(
                        lunchbox=lunchbox,
                        alert_type=Alert.TEMPERATURE_HIGH,
                        severity=Alert.WARNING if temp_r.value < THRESHOLDS['temp_high'] + 5 else Alert.CRITICAL,
                        message=f"Temperature high: {temp_r.value}{temp_r.unit} > {THRESHOLDS['temp_high']}°C"
                    ))

            # Humidity high
            humi_r = latest_batch.get(SensorReading.HUMIDITY)
            if humi_r and humi_r.value > THRESHOLDS['humi_high']:
                existing = Alert.objects.filter(lunchbox=lunchbox, alert_type=Alert.HUMIDITY_HIGH, is_resolved=False).order_by('-created_at').first()
                if existing and existing.created_at >= recent_cutoff:
                    alert_events.append(existing)
                else:
                    alert_events.append(Alert.objects.create(
                        lunchbox=lunchbox,
                        alert_type=Alert.HUMIDITY_HIGH,
                        severity=Alert.WARNING,
                        message=f"Humidity high: {humi_r.value}{humi_r.unit} > {THRESHOLDS['humi_high']}%"
                    ))

            # Gas high
            gas_r = latest_batch.get(SensorReading.GAS)
            if gas_r and gas_r.value > THRESHOLDS['gas_high']:
                existing = Alert.objects.filter(lunchbox=lunchbox, alert_type=Alert.GAS_HIGH, is_resolved=False).order_by('-created_at').first()
                if existing and existing.created_at >= recent_cutoff:
                    alert_events.append(existing)
                else:
                    alert_events.append(Alert.objects.create(
                        lunchbox=lunchbox,
                        alert_type=Alert.GAS_HIGH,
                        severity=Alert.WARNING if gas_r.value < THRESHOLDS['gas_high'] + 100 else Alert.CRITICAL,
                        message=f"Gas level high: {gas_r.value}{gas_r.unit} > {THRESHOLDS['gas_high']}ppm"
                    ))

            # Battery low
            batt_r = latest_batch.get(SensorReading.BATTERY)
            if batt_r and batt_r.value < THRESHOLDS['batt_low']:
                existing = Alert.objects.filter(lunchbox=lunchbox, alert_type=Alert.BATTERY_LOW, is_resolved=False).order_by('-created_at').first()
                if existing and existing.created_at >= recent_cutoff:
                    alert_events.append(existing)
                else:
                    alert_events.append(Alert.objects.create(
                        lunchbox=lunchbox,
                        alert_type=Alert.BATTERY_LOW,
                        severity=Alert.WARNING if batt_r.value >= THRESHOLDS['batt_low'] - 5 else Alert.CRITICAL,
                        message=f"Battery low: {batt_r.value}{batt_r.unit} < {THRESHOLDS['batt_low']}%"
                    ))

            # Proximity near
            prox_r = latest_batch.get(SensorReading.PROXIMITY)
            if prox_r and prox_r.value <= THRESHOLDS['prox_near']:
                existing = Alert.objects.filter(lunchbox=lunchbox, alert_type=Alert.PROXIMITY_NEAR, is_resolved=False).order_by('-created_at').first()
                if existing and existing.created_at >= recent_cutoff:
                    alert_events.append(existing)
                else:
                    alert_events.append(Alert.objects.create(
                        lunchbox=lunchbox,
                        alert_type=Alert.PROXIMITY_NEAR,
                        severity=Alert.WARNING,
                        message=f"Object near: {prox_r.value}{prox_r.unit or 'cm'} <= {THRESHOLDS['prox_near']}cm"
                    ))

            # Motion detected (treat any non-zero as motion)
            motion_r = latest_batch.get(SensorReading.MOTION)
            if motion_r and float(motion_r.value) > 0:
                alert_events.append(Alert.objects.create(
                    lunchbox=lunchbox,
                    alert_type=Alert.MOTION_DETECTED,
                    severity=Alert.WARNING,
                    message="Motion detected"
                ))
        except Exception:
            logger.exception("Alert evaluation failed lunchbox=%s", lunchbox.id if 'lunchbox' in locals() else '?')

        # Broadcast last reading per sensor via channels (non-fatal if channel layer unavailable)
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:  # In-memory or redis layer
                group_name = f'lunchbox_{lunchbox.id}'
                latest_by_type = {}
                for r in created:
                    latest_by_type[r.sensor_type] = r
                for r in latest_by_type.values():
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'sensor_update',
                            'sensor_type': r.sensor_type,
                            'value': r.value,
                            'unit': r.unit,
                            'recorded_at': r.recorded_at.isoformat()
                        }
                    )
                # Broadcast any alerts generated
                for a in alert_events:
                    logger.debug("Broadcasting alert id=%s type=%s severity=%s", a.id, a.alert_type, a.severity)
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'alert_notification',
                            'alert_type': a.alert_type,
                            'severity': a.severity,
                            'message': a.message,
                            'created_at': a.created_at.isoformat(),
                        }
                    )
        except Exception as e:  # Log and continue (avoid ingestion failure due to Redis)
            import logging
            logging.getLogger(__name__).warning("Channel broadcast skipped: %s", e)

        return Response({'created': len(created)}, status=status.HTTP_201_CREATED)

    def get(self, request):  # Simple connectivity probe (device or user can GET to verify tunnel & path)
        return Response({'detail': 'Device ingest endpoint. Use POST with api_key & readings.'}, status=status.HTTP_200_OK)
