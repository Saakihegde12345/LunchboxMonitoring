"""
Initialize Celery and PyMySQL for the Lunchbox Monitoring System.

This module ensures that Celery is loaded when Django starts so that shared_task
will use this app, and configures PyMySQL as the MySQL driver.
"""

# Configure PyMySQL as MySQL driver
import pymysql
pymysql.install_as_MySQLdb()

# This will make sure the Celery app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ('celery_app',)