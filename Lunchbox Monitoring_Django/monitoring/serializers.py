from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Lunchbox, SensorReading, Alert

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer for the user object."""
    class Meta:
        model = User
        fields = ('id', 'username', 'email')
        read_only_fields = ('id',)


class LunchboxSerializer(serializers.ModelSerializer):
    """Serializer for the lunchbox object."""
    owner = UserSerializer(read_only=True)
    
    class Meta:
        model = Lunchbox
        fields = ('id', 'name', 'description', 'owner', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class SensorReadingSerializer(serializers.ModelSerializer):
    """Serializer for sensor readings."""
    sensor_type_display = serializers.CharField(source='get_sensor_type_display', read_only=True)
    
    class Meta:
        model = SensorReading
        fields = (
            'id', 'lunchbox', 'sensor_type', 'sensor_type_display', 
            'value', 'unit', 'recorded_at', 'created_at'
        )
        read_only_fields = ('id', 'created_at')
        extra_kwargs = {
            'lunchbox': {'required': True}
        }
    
    def validate_lunchbox(self, value):
        """Check that the lunchbox is active and owned by the user."""
        request = self.context.get('request')
        if value.owner != request.user:
            raise serializers.ValidationError("You don't have permission to add readings to this lunchbox.")
        if not value.is_active:
            raise serializers.ValidationError("Cannot add readings to an inactive lunchbox.")
        return value
    
    def validate_sensor_type(self, value):
        """Validate sensor type."""
        if value not in dict(SensorReading.SENSOR_TYPES).keys():
            raise serializers.ValidationError(f"Invalid sensor type. Must be one of: {', '.join(dict(SensorReading.SENSOR_TYPES).keys())}")
        return value


class AlertSerializer(serializers.ModelSerializer):
    """Serializer for alert objects."""
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    lunchbox_name = serializers.CharField(source='lunchbox.name', read_only=True)
    
    class Meta:
        model = Alert
        fields = (
            'id', 'lunchbox', 'lunchbox_name', 'alert_type', 'alert_type_display',
            'severity', 'severity_display', 'message', 'is_resolved',
            'resolved_at', 'created_at'
        )
        read_only_fields = ('id', 'created_at', 'resolved_at')


class DashboardStatsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics."""
    stats = serializers.DictField()
    recent_alerts = AlertSerializer(many=True)
    sensor_statistics = serializers.DictField()


class SensorReadingBulkCreateSerializer(serializers.ListSerializer):
    """Serializer for bulk creation of sensor readings."""
    def create(self, validated_data):
        return [
            self.child.create(attrs) for attrs in validated_data
        ]
    
    def validate(self, data):
        """Validate that all readings are for the same lunchbox."""
        lunchbox_ids = {item['lunchbox'].id for item in data}
        if len(lunchbox_ids) > 1:
            raise serializers.ValidationError("All readings must be for the same lunchbox.")
        return data


class SensorReadingBulkCreateItemSerializer(serializers.ModelSerializer):
    """Serializer for individual sensor reading in bulk create."""
    class Meta:
        model = SensorReading
        fields = ('sensor_type', 'value', 'unit', 'recorded_at')
        list_serializer_class = SensorReadingBulkCreateSerializer
    
    def create(self, validated_data):
        return self.Meta.model.objects.create(**validated_data)
