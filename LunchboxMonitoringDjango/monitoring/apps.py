from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'monitoring'
    verbose_name = 'Lunchbox Monitoring'
    
    def ready(self):
        """
        Import signals and other startup code here.
        This method is called when Django starts.
        """
        import monitoring.signals  # noqa
