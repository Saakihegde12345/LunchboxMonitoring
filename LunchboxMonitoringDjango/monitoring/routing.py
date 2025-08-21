from django.urls import re_path
from . import consumers

# WebSocket URL patterns (provide a couple of aliases for robustness)
websocket_urlpatterns = [
    re_path(r'ws/monitoring/(?P<lunchbox_id>\d+)/?$', consumers.LunchboxConsumer.as_asgi()),
    re_path(r'ws/lunchbox/(?P<lunchbox_id>\d+)/?$', consumers.LunchboxConsumer.as_asgi()),
]
