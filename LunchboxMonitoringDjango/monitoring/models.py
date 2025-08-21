from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

User = get_user_model()

class Lunchbox(models.Model):
    """Model representing a lunchbox being monitored."""
    name = models.CharField(max_length=100, help_text="A friendly name for the lunchbox")
    description = models.TextField(blank=True, help_text="Optional description of the lunchbox")
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lunchboxes',
        help_text="User who owns this lunchbox",
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True, help_text="Whether this lunchbox is currently active")
    device_api_key = models.CharField(
        max_length=64,
        unique=True,
        default=uuid.uuid4,  # stored as UUID str
        help_text="API key devices use to authenticate when pushing sensor data"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Lunchboxes'

    def __str__(self):
        return f"{self.name} ({self.owner.username})"

    def regenerate_api_key(self, save: bool = True):
        """Generate a new device_api_key (e.g., if compromised)."""
        self.device_api_key = uuid.uuid4().hex
        if save:
            self.save(update_fields=["device_api_key", "updated_at"])
        return self.device_api_key

class SensorReading(models.Model):
    """Model to store sensor readings from the lunchbox."""
    TEMPERATURE = 'temp'
    HUMIDITY = 'humi'
    GAS = 'gas'
    BATTERY = 'batt'
    PROXIMITY = 'prox'
    MOTION = 'motion'
    
    SENSOR_TYPES = [
        (TEMPERATURE, 'Temperature'),
        (HUMIDITY, 'Humidity'),
        (GAS, 'Gas Level'),
        (BATTERY, 'Battery Level'),
        (PROXIMITY, 'Proximity/Distance'),
        (MOTION, 'Motion/PIR'),
    ]

    lunchbox = models.ForeignKey(
        Lunchbox,
        on_delete=models.CASCADE,
        related_name='sensor_readings',
        help_text="The lunchbox this reading belongs to"
    )
    sensor_type = models.CharField(
        max_length=12,
        choices=SENSOR_TYPES,
        help_text="Type of sensor reading"
    )
    value = models.FloatField(help_text="The sensor reading value")
    unit = models.CharField(max_length=10, help_text="Unit of measurement (e.g., °C, %, ppm)")
    recorded_at = models.DateTimeField(help_text="When the reading was taken")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['lunchbox', 'sensor_type', 'recorded_at']),
        ]

    def __str__(self):
        return f"{self.get_sensor_type_display()}: {self.value}{self.unit} at {self.recorded_at}"

class Alert(models.Model):
    """Model to store alerts for abnormal conditions."""
    CRITICAL = 'critical'
    WARNING = 'warning'
    INFO = 'info'
    
    SEVERITY_LEVELS = [
        (CRITICAL, 'Critical'),
        (WARNING, 'Warning'),
        (INFO, 'Information'),
    ]

    TEMPERATURE_HIGH = 'temp_high'
    TEMPERATURE_LOW = 'temp_low'
    HUMIDITY_HIGH = 'humi_high'
    GAS_HIGH = 'gas_high'
    BATTERY_LOW = 'batt_low'
    PROXIMITY_NEAR = 'prox_near'
    MOTION_DETECTED = 'motion_detected'
    
    ALERT_TYPES = [
        (TEMPERATURE_HIGH, 'Temperature Too High'),
        (TEMPERATURE_LOW, 'Temperature Too Low'),
        (HUMIDITY_HIGH, 'High Humidity'),
        (GAS_HIGH, 'High Gas Level'),
        (BATTERY_LOW, 'Low Battery'),
        (PROXIMITY_NEAR, 'Object Too Near'),
        (MOTION_DETECTED, 'Motion Detected'),
    ]

    lunchbox = models.ForeignKey(
        Lunchbox,
        on_delete=models.CASCADE,
        related_name='alerts',
        help_text="The lunchbox this alert is for"
    )
    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPES,
        help_text="Type of alert"
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_LEVELS,
        default=WARNING,
        help_text="Severity level of the alert"
    )
    message = models.TextField(help_text="Detailed alert message")
    is_resolved = models.BooleanField(default=False, help_text="Whether the alert has been resolved")
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="When the alert was resolved")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lunchbox', 'is_resolved', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_severity_display().upper()}: {self.get_alert_type_display()} - {self.message[:50]}..."

    def resolve(self):
        """Mark the alert as resolved."""
        if not self.is_resolved:
            self.is_resolved = True
            self.save(update_fields=['is_resolved', 'resolved_at'])
            return True
        return False
