from rest_framework import serializers
from django.contrib.auth import get_user_model
from monitoring.models import Lunchbox, SensorReading, Alert

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff')
        read_only_fields = ('id', 'is_staff')

class LunchboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lunchbox
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'last_seen')

class SensorReadingSerializer(serializers.ModelSerializer):
    lunchbox_name = serializers.CharField(source='lunchbox.name', read_only=True)
    
    class Meta:
        model = SensorReading
        fields = '__all__'
        read_only_fields = ('id', 'timestamp')

class AlertSerializer(serializers.ModelSerializer):
    lunchbox_name = serializers.CharField(source='lunchbox.name', read_only=True)
    
    class Meta:
        model = Alert
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'resolved_at')

