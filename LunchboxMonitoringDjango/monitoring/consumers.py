import json
import asyncio
from datetime import datetime, timedelta
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db.models import Avg, Max, Min, Count, Q
from django.utils import timezone
from .models import Lunchbox, SensorReading, Alert
import logging
logger = logging.getLogger(__name__)

class LunchboxConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time lunchbox monitoring."""
    
    async def connect(self):
        """
        Handle WebSocket connection.
        Check if the user has permission to access this lunchbox.
        """
        self.lunchbox_id = self.scope['url_route']['kwargs']['lunchbox_id']
        self.room_group_name = f'lunchbox_{self.lunchbox_id}'
        
        # Check authentication
        user = self.scope["user"]
        if isinstance(user, AnonymousUser):
            logger.info("WS connect denied anonymous lunchbox=%s", self.lunchbox_id)
            await self.close()
            return
        
        # Check if the user has permission to access this lunchbox
        has_permission = await self.check_permission(user)
        if not has_permission:
            logger.info("WS connect denied unauthorized user=%s lunchbox=%s", user, self.lunchbox_id)
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info("WS connect accepted user=%s lunchbox=%s", user, self.lunchbox_id)

        # Send current state
        await self.send_current_state()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    @database_sync_to_async
    def check_permission(self, user):
        """Check if user has permission to access this lunchbox."""
        try:
            return Lunchbox.objects.filter(
                id=self.lunchbox_id,
                owner=user,
                is_active=True
            ).exists()
        except (ValueError, Lunchbox.DoesNotExist):
            return False
    
    @database_sync_to_async
    def get_latest_readings(self):
        """Get the latest sensor readings for this lunchbox."""
        latest_readings = {}
        qs = SensorReading.objects.filter(lunchbox_id=self.lunchbox_id).order_by('sensor_type', '-recorded_at')
        for r in qs:
            if r.sensor_type not in latest_readings:
                latest_readings[r.sensor_type] = {
                    'value': r.value,
                    'unit': r.unit,
                    'recorded_at': r.recorded_at.isoformat()
                }
        return latest_readings
    
    async def send_current_state(self):
        """Send the current state of the lunchbox to the client."""
        latest_readings = await self.get_latest_readings()
        
        await self.send(text_data=json.dumps({
            'type': 'current_state',
            'lunchbox_id': self.lunchbox_id,
            'readings': latest_readings,
        }))
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages from the client."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'subscribe':
                # Handle subscription to specific events
                pass
            elif message_type == 'command':
                # Handle incoming commands
                pass
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
    
    async def sensor_update(self, event):
        """
        Send sensor updates to the WebSocket.
        Called when a new sensor reading is received.
        """
        await self.send(text_data=json.dumps({
            'type': 'sensor_update',
            'sensor_type': event['sensor_type'],
            'value': event['value'],
            'unit': event['unit'],
            'recorded_at': event['recorded_at']
        }))
    
    async def alert_notification(self, event):
        """
        Send alert notifications to the WebSocket.
        Called when a new alert is generated.
        """
        await self.send(text_data=json.dumps({
            'type': 'alert',
            'alert_type': event['alert_type'],
            'severity': event['severity'],
            'message': event['message'],
            'created_at': event['created_at']
        }))
