"""
Celery configuration for the Lunchbox Monitoring System.
"""
import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Create Celery app
app = Celery('lunchbox_monitoring')

# Configure Celery using settings from Django settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Configure periodic tasks
app.conf.beat_schedule = {
    # Check for alerts every minute
    'check-alerts-every-minute': {
        'task': 'monitoring.tasks.check_for_alerts',
        'schedule': 60.0,  # Every minute
    },
    # Clean up old data every day at midnight
    'cleanup-old-data': {
        'task': 'monitoring.tasks.cleanup_old_data',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
}

# Configure timezone
app.conf.timezone = settings.TIME_ZONE

# Configure task routing
app.conf.task_routes = {
    'monitoring.tasks.*': {'queue': 'monitoring'},
}

# Configure task serialization
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']

# Configure task time limits
app.conf.task_time_limit = 30 * 60  # 30 minutes
app.conf.task_soft_time_limit = 25 * 60  # 25 minutes

# Enable task events
app.conf.worker_send_task_events = True
app.conf.task_send_sent_event = True

# Configure result backend
app.conf.result_backend = 'django-db'
app.conf.cache_backend = 'django-cache'

# Add periodic task to check for long-running tasks
app.conf.beat_schedule.update({
    'monitor-long-running-tasks': {
        'task': 'monitoring.tasks.monitor_long_running_tasks',
        'schedule': 300.0,  # Every 5 minutes
    },
})

# Configure task error handling
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True
app.conf.worker_prefetch_multiplier = 1

# Configure task retries
app.conf.task_default_retry_delay = 60  # 1 minute
app.conf.task_max_retries = 3

# Configure task result expiration
app.conf.result_expires = 60 * 60 * 24 * 7  # 7 days

# Configure task compression
app.conf.task_compression = 'gzip'

# Configure task routing
app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'lunchbox_monitoring'
app.conf.task_default_routing_key = 'task.default'
