from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from ...models import ActivityLog

class Command(BaseCommand):
    help = "Delete old activity logs"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=90)
        batch_size = 5000

        total_deleted = 0
        while True:
            qs = ActivityLog.objects.filter(timestamp__lt=cutoff)[:batch_size]
            if not qs.exists():
                break
            count = qs.count()
            qs.delete()
            total_deleted += count

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {total_deleted} old activity logs"
        ))
