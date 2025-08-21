from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import SensorReading, Alert

# Thresholds for alerts (in appropriate units)
THRESHOLDS = {
    'temp': {'min': 4.0, 'max': 60.0},  # °C
    'humi': {'min': 20.0, 'max': 80.0},  # %
    'gas': {'max': 1000.0},  # ppm
}

@receiver(post_save, sender=SensorReading)
def check_sensor_reading(sender, instance, created, **kwargs):
    """
    Check if a sensor reading exceeds thresholds and create alerts if needed.
    """
    if not created:  # Only check new readings
        return
    
    sensor_type = instance.sensor_type
    value = instance.value
    
    # Get thresholds for this sensor type
    thresholds = THRESHOLDS.get(sensor_type, {})
    
    # Check for out-of-range conditions
    if 'min' in thresholds and value < thresholds['min']:
        if sensor_type == 'temp':
            alert_type = 'temp_low'
            severity = 'critical'
        else:
            alert_type = f"{sensor_type}_low"
            severity = 'warning'
            
        Alert.objects.create(
            lunchbox=instance.lunchbox,
            alert_type=alert_type,
            severity=severity,
            message=f"{instance.get_sensor_type_display()} is below minimum threshold: {value}{instance.unit} < {thresholds['min']}{instance.unit}"
        )
    
    elif 'max' in thresholds and value > thresholds['max']:
        if sensor_type == 'temp':
            alert_type = 'temp_high'
            severity = 'critical'
        else:
            alert_type = f"{sensor_type}_high"
            severity = 'warning' if sensor_type != 'gas' else 'critical'
            
        Alert.objects.create(
            lunchbox=instance.lunchbox,
            alert_type=alert_type,
            severity=severity,
            message=f"{instance.get_sensor_type_display()} is above maximum threshold: {value}{instance.unit} > {thresholds['max']}{instance.unit}"
        )
