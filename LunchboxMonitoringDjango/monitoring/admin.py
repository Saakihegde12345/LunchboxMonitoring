from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.http import HttpResponseForbidden

# Custom admin login view to block non-staff users
class StaffOnlyAdminLoginView(LoginView):
    def form_valid(self, form):
        user = form.get_user()
        if not user.is_staff:
            return HttpResponseForbidden("Access denied: Only admin users can log in here.")
        return super().form_valid(form)
from .models import Lunchbox, SensorReading, Alert
from django.contrib.auth.models import Group, User
try:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    admin.site.unregister(BlacklistedToken)
    admin.site.unregister(OutstandingToken)
except Exception:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(Lunchbox)
class LunchboxAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_active', 'device_api_key', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description', 'owner__username', 'device_api_key')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at', 'device_api_key')
    actions = ['regenerate_api_key']
    fieldsets = (
        (None, {
            'fields': ('name', 'owner', 'description', 'is_active')
        }),
        ('Device Access', {
            'fields': ('device_api_key',),
            'description': 'Share this key securely with the physical device; treat as a secret.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.action(description='Regenerate API key for selected lunchboxes')
    def regenerate_api_key(self, request, queryset):
        for lunchbox in queryset:
            lunchbox.regenerate_api_key()
        self.message_user(request, f"Regenerated API keys for {queryset.count()} lunchboxes.")

@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ('sensor_type_display', 'value_with_unit', 'lunchbox', 'recorded_at')
    list_filter = ('sensor_type', 'recorded_at')
    search_fields = ('lunchbox__name', 'lunchbox__owner__username')
    date_hierarchy = 'recorded_at'
    readonly_fields = ('created_at',)
    
    def sensor_type_display(self, obj):
        return obj.get_sensor_type_display()
    sensor_type_display.short_description = 'Sensor Type'
    
    def value_with_unit(self, obj):
        return f"{obj.value} {obj.unit}"
    value_with_unit.short_description = 'Value'

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('alert_type_display', 'severity_display', 'lunchbox', 'is_resolved', 'created_at')
    list_filter = ('severity', 'is_resolved', 'alert_type', 'created_at')
    search_fields = ('message', 'lunchbox__name', 'lunchbox__owner__username')
    date_hierarchy = 'created_at'
    actions = ['mark_as_resolved']
    
    def alert_type_display(self, obj):
        return obj.get_alert_type_display()
    alert_type_display.short_description = 'Alert Type'
    
    def severity_display(self, obj):
        return obj.get_severity_display()
    severity_display.short_description = 'Severity'
    
    @admin.action(description='Mark selected alerts as resolved')
    def mark_as_resolved(self, request, queryset):
        updated = 0
        for alert in queryset.filter(is_resolved=False):
            alert.resolve()
            updated += 1
        self.message_user(request, f"Successfully marked {updated} alerts as resolved.")

# Unregister celery beat and token blacklist models at the end
try:
    from django_celery_results.models import GroupResult, TaskResult
    from django_celery_beat.models import ClockedSchedule, CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule
    admin.site.unregister(GroupResult)
    admin.site.unregister(TaskResult)
    admin.site.unregister(ClockedSchedule)
    admin.site.unregister(CrontabSchedule)
    admin.site.unregister(IntervalSchedule)
    admin.site.unregister(PeriodicTask)
    admin.site.unregister(SolarSchedule)
except Exception:
    pass

try:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    admin.site.unregister(BlacklistedToken)
    admin.site.unregister(OutstandingToken)
except Exception:
    pass
