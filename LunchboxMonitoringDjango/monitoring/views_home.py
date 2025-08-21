from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.conf import settings
from django.db.models import Max
from .models import Lunchbox, SensorReading, Alert
from django.utils.timesince import timesince
from collections import defaultdict, OrderedDict
import json

class HomeView(TemplateView):
    """View for the home page."""
    template_name = 'home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context data here
        return context


class DashboardTemplateView(LoginRequiredMixin, TemplateView):
    """View for the dashboard page."""
    template_name = 'dashboard.html'
    # Use parent login route instead of admin login for authentication
    login_url = '/parent/login/'
    redirect_field_name = 'next'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # Active lunchboxes for this user
        lunchboxes_qs = Lunchbox.objects.filter(owner=user, is_active=True).order_by('id')

        # Latest reading per (lunchbox, sensor_type)
        readings = (
            SensorReading.objects
            .filter(lunchbox__in=lunchboxes_qs)
            .order_by('lunchbox_id', 'sensor_type', '-recorded_at')
        )
        latest_readings_map = {}
        seen_keys = set()
        for r in readings:
            key = (r.lunchbox_id, r.sensor_type)
            if key not in seen_keys:
                latest_readings_map[key] = r
                seen_keys.add(key)

        # Alert stats
        active_alerts = Alert.objects.filter(lunchbox__owner=user, is_resolved=False)
        critical_count = active_alerts.filter(severity=Alert.CRITICAL).count()
        warning_count = active_alerts.filter(severity=Alert.WARNING).count()
        active_count = lunchboxes_qs.count()
        normal_count = max(active_count - (critical_count + warning_count), 0)

        # Rows for table
        lunchbox_rows = []
        for lb in lunchboxes_qs:
            temp = latest_readings_map.get((lb.id, SensorReading.TEMPERATURE))
            humi = latest_readings_map.get((lb.id, SensorReading.HUMIDITY))
            gas = latest_readings_map.get((lb.id, SensorReading.GAS))
            batt = latest_readings_map.get((lb.id, SensorReading.BATTERY))
            prox = latest_readings_map.get((lb.id, SensorReading.PROXIMITY))
            motion = latest_readings_map.get((lb.id, SensorReading.MOTION))

            lb_alerts = active_alerts.filter(lunchbox=lb)
            if lb_alerts.filter(severity=Alert.CRITICAL).exists():
                status = 'critical'
            elif lb_alerts.filter(severity=Alert.WARNING).exists():
                status = 'warning'
            else:
                status = 'normal'

            latest_dt_candidates = [r.recorded_at for r in (temp, humi, gas, batt, prox, motion) if r]
            latest_dt = max(latest_dt_candidates) if latest_dt_candidates else None

            lunchbox_rows.append({
                'id': lb.id,
                'name': lb.name,
                'api_key': lb.device_api_key,
                'status': status,
                'temp': f"{temp.value:.1f}{temp.unit}" if temp else '-',
                'humi': f"{humi.value:.0f}{humi.unit}" if humi else '-',
                'gas': f"{gas.value:.0f}{gas.unit}" if gas else '-',
                'batt': f"{batt.value:.0f}{batt.unit}" if batt else '-',
                'prox': f"{prox.value:.0f}{prox.unit}" if prox else '-',
                'motion': (bool(motion.value) if motion else None),
                'last_updated': latest_dt,
            })

        context.update({
            'page_title': 'Dashboard',
            'current_time': now,
            'debug': settings.DEBUG,
            'stats': {
                'active': active_count,
                'normal': normal_count,
                'warning': warning_count,
                'critical': critical_count,
            },
            'lunchbox_rows': lunchbox_rows,
        })

        # Temperature chart data (last N points per lunchbox)
        temp_qs = list(
            SensorReading.objects
            .filter(lunchbox__in=lunchboxes_qs, sensor_type=SensorReading.TEMPERATURE)
            .order_by('-recorded_at')[:300]
        )

        per_lb = defaultdict(dict)
        label_pairs = []
        seen_label_keys = set()
        for r in temp_qs:
            dt_second = r.recorded_at.replace(microsecond=0)
            label = dt_second.strftime('%Y-%m-%d %H:%M:%S')
            if label not in per_lb[r.lunchbox_id]:
                per_lb[r.lunchbox_id][label] = r.value
            key = (dt_second, label)
            if key not in seen_label_keys:
                label_pairs.append(key)
                seen_label_keys.add(key)

        label_pairs.sort(key=lambda x: x[0])
        labels = [lp[1] for lp in label_pairs][-180:]

        palette = [
            ('#3498db', 'rgba(52,152,219,0.15)'),
            ('#2ecc71', 'rgba(46,204,113,0.15)'),
            ('#9b59b6', 'rgba(155,89,182,0.15)'),
            ('#e67e22', 'rgba(230,126,34,0.15)'),
            ('#e74c3c', 'rgba(231,76,60,0.15)'),
            ('#1abc9c', 'rgba(26,188,156,0.15)'),
        ]

        datasets = []
        if labels:
            for idx, lb in enumerate(lunchboxes_qs):
                line_color, fill_color = palette[idx % len(palette)]
                lb_map = per_lb.get(lb.id, {})
                data_points = [round(lb_map.get(label), 2) if label in lb_map else None for label in labels]
                datasets.append({
                    'label': lb.name,
                    'data': data_points,
                    'borderColor': line_color,
                    'backgroundColor': fill_color,
                    'tension': 0.3,
                    'spanGaps': True,
                    'fill': True,
                })

        temp_chart = {
            'labels': labels,
            'datasets': datasets,
            'generated_at': now.isoformat(),
        }
        context['temp_chart'] = temp_chart
        context['temp_chart_json'] = json.dumps(temp_chart)

        return context
