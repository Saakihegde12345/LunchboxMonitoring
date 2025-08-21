"""
ASGI config for lunchbox_monitoring project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.conf import settings


# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Import websocket routing from monitoring app (contains LunchboxConsumer patterns)
from monitoring.routing import websocket_urlpatterns

# Debug log to confirm ASGI websocket patterns loaded
import logging as _logging
_logging.getLogger(__name__).info("ASGI loaded websocket patterns: %s", [p.pattern.regex.pattern for p in websocket_urlpatterns])

# Build the base Django ASGI app and wrap for static files in DEBUG
_http_app = get_asgi_application()
if getattr(settings, 'DEBUG', False):
    _http_app = ASGIStaticFilesHandler(_http_app)

# Main application routing
application = ProtocolTypeRouter({
    # HTTP requests are handled by the standard Django ASGI application
    "http": _http_app,

    # WebSocket handler
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
