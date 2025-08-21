from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = 'Lunchbox API'
    
    def ready(self):
        # No signals to register
        pass
