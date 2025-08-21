from django.core.management.base import BaseCommand
from datetime import datetime, timezone

from monitoring.models import SensorReading, Alert


class Command(BaseCommand):
    help = "Remove initial prox/motion test rows and related alerts created during setup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cutoff",
            default="2025-08-16T18:30:02+00:00",
            help="ISO8601 UTC cutoff; delete prox/motion readings and alerts at or before this instant.",
        )

    def handle(self, *args, **opts):
        cutoff_str = opts["cutoff"].replace("Z", "+00:00")
        try:
            cutoff = datetime.fromisoformat(cutoff_str)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Invalid cutoff '{cutoff_str}': {e}"))
            return 1

        sr_qs = SensorReading.objects.filter(
            sensor_type__in=[SensorReading.PROXIMITY, SensorReading.MOTION],
            recorded_at__lte=cutoff,
        )
        sr_count = sr_qs.count()
        sr_qs.delete()

        alert_qs = Alert.objects.filter(
            alert_type__in=[Alert.PROXIMITY_NEAR, Alert.MOTION_DETECTED],
            created_at__lte=cutoff,
        )
        alert_count = alert_qs.count()
        alert_qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {sr_count} sensor readings and {alert_count} alerts at/before {cutoff.isoformat()}"
        ))
