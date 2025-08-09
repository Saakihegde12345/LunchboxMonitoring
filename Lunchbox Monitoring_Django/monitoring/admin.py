from django.contrib import admin
from .models import Lunchbox, SensorReading, Alert

@admin.register(Lunchbox)
class LunchboxAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description', 'owner__username')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'owner', 'description', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

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
