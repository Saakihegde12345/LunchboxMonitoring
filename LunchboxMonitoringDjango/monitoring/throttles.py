from rest_framework.throttling import SimpleRateThrottle


class DeviceIngestThrottle(SimpleRateThrottle):
    """Rate limit device ingest by device API key, falling back to client IP.

    Scope name: 'device_ingest' (configure in DEFAULT_THROTTLE_RATES).
    """
    scope = 'device_ingest'

    def get_cache_key(self, request, view):
        # Prefer device API key from JSON body if present
        ident = None
        try:
            data = getattr(request, 'data', None)
            if isinstance(data, dict):
                api_key = data.get('api_key') or data.get('device_api_key')
                if api_key:
                    ident = f"devkey:{str(api_key)}"
        except Exception:
            ident = None
        if not ident:
            ident = self.get_ident(request)  # fall back to IP
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }
