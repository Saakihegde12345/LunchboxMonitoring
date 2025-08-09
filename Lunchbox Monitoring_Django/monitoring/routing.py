from django.urls import re_path
from . import consumers

# WebSocket URL patterns
websocket_urlpatterns = [
    re_path(r'ws/monitoring/(?P<lunchbox_id>\d+)/$', consumers.LunchboxConsumer.as_asgi()),
]
