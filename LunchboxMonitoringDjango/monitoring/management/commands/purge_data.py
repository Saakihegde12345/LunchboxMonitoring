from django.core.management.base import BaseCommand
from monitoring.models import SensorReading, Alert, Lunchbox


class Command(BaseCommand):
    help = "Delete all sensor readings and alerts (optionally lunchboxes) for a clean slate."

    def add_arguments(self, parser):
        parser.add_argument('--keep-lunchboxes', action='store_true', help='Keep Lunchbox entries (default deletes them).')

    def handle(self, *args, **options):
        keep = options['keep_lunchboxes']
        sr_count = SensorReading.objects.count()
        alert_count = Alert.objects.count()
        SensorReading.objects.all().delete()
        Alert.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {sr_count} sensor readings and {alert_count} alerts."))
        if not keep:
            lb_count = Lunchbox.objects.count()
            Lunchbox.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {lb_count} lunchboxes."))
        else:
            self.stdout.write("Lunchboxes retained.")
