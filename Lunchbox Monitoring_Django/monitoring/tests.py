from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import Lunchbox, SensorReading, Alert

User = get_user_model()

class ModelTests(TestCase):
    """Test cases for models."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.lunchbox = Lunchbox.objects.create(
            name='Test Lunchbox',
            description='A test lunchbox',
            owner=self.user
        )
    
    def test_lunchbox_creation(self):
        """Test lunchbox creation."""
        self.assertEqual(self.lunchbox.name, 'Test Lunchbox')
        self.assertEqual(self.lunchbox.owner, self.user)
        self.assertTrue(self.lunchbox.is_active)
    
    def test_sensor_reading_creation(self):
        """Test sensor reading creation."""
        reading = SensorReading.objects.create(
            lunchbox=self.lunchbox,
            sensor_type='temp',
            value=25.5,
            unit='°C',
            recorded_at=timezone.now()
        )
        self.assertEqual(reading.sensor_type, 'temp')
        self.assertEqual(reading.value, 25.5)
        self.assertEqual(reading.unit, '°C')
    
    def test_alert_creation(self):
        """Test alert creation."""
        alert = Alert.objects.create(
            lunchbox=self.lunchbox,
            alert_type='temp_high',
            severity='critical',
            message='Temperature is too high!'
        )
        self.assertEqual(alert.alert_type, 'temp_high')
        self.assertEqual(alert.severity, 'critical')
        self.assertFalse(alert.is_resolved)


class ViewTests(APITestCase):
    """Test cases for API views."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        self.lunchbox = Lunchbox.objects.create(
            name='Test Lunchbox',
            description='A test lunchbox',
            owner=self.user
        )
        
        self.reading_data = {
            'sensor_type': 'temp',
            'value': 22.5,
            'unit': '°C',
            'recorded_at': timezone.now().isoformat()
        }
    
    def test_create_lunchbox(self):
        """Test creating a lunchbox."""
        url = reverse('monitoring:lunchbox-list')
        data = {
            'name': 'New Lunchbox',
            'description': 'Another test lunchbox'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Lunchbox.objects.count(), 2)
        self.assertEqual(Lunchbox.objects.get(id=2).name, 'New Lunchbox')
    
    def test_create_sensor_reading(self):
        """Test creating a sensor reading."""
        url = reverse('monitoring:sensor-reading-list', args=[self.lunchbox.id])
        response = self.client.post(url, self.reading_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SensorReading.objects.count(), 1)
        self.assertEqual(SensorReading.objects.first().value, 22.5)
    
    def test_get_dashboard(self):
        """Test retrieving dashboard data."""
        # Create some test data
        SensorReading.objects.create(
            lunchbox=self.lunchbox,
            sensor_type='temp',
            value=25.0,
            unit='°C',
            recorded_at=timezone.now()
        )
        
        Alert.objects.create(
            lunchbox=self.lunchbox,
            alert_type='temp_high',
            severity='warning',
            message='Temperature is high!'
        )
        
        url = reverse('monitoring:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('stats', response.data)
        self.assertIn('recent_alerts', response.data)
        self.assertIn('sensor_statistics', response.data)
        self.assertEqual(len(response.data['recent_alerts']), 1)


class PermissionTests(APITestCase):
    """Test cases for custom permissions."""
    
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)
        
        self.lunchbox = Lunchbox.objects.create(
            name='User1 Lunchbox',
            description='User1\'s lunchbox',
            owner=self.user1
        )
    
    def test_user_can_access_own_lunchbox(self):
        """Test that a user can access their own lunchbox."""
        url = reverse('monitoring:lunchbox-detail', args=[self.lunchbox.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_user_cannot_access_other_users_lunchbox(self):
        """Test that a user cannot access another user's lunchbox."""
        self.client.force_authenticate(user=self.user2)
        url = reverse('monitoring:lunchbox-detail', args=[self.lunchbox.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_unauthorized_access(self):
        """Test that unauthorized users cannot access protected endpoints."""
        self.client.force_authenticate(user=None)
        url = reverse('monitoring:lunchbox-detail', args=[self.lunchbox.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
