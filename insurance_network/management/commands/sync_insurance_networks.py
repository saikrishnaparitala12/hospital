from django.core.management.base import BaseCommand
from insurance_network.models import InsuranceCompany
from insurance_network.tasks import sync_insurance_network


class Command(BaseCommand):
    help = "Trigger insurance hospital network sync. Use --slug to sync one provider."

    def add_arguments(self, parser):
        parser.add_argument("--slug", type=str, help="Insurance company slug (omit to sync all)")
        parser.add_argument("--sync", action="store_true", help="Run synchronously instead of via Celery")

    def handle(self, *args, **options):
        slug = options.get("slug")
        run_sync = options.get("sync")

        slugs = [slug] if slug else list(InsuranceCompany.objects.filter(is_active=True).values_list("slug", flat=True))

        for s in slugs:
            if run_sync:
                from insurance_network.services import InsuranceNetworkService
                log = InsuranceNetworkService.sync_insurance(s)
                self.stdout.write(self.style.SUCCESS(f"{s}: {log.status} — {log.hospitals_found} hospitals"))
            else:
                sync_insurance_network.delay(s)
                self.stdout.write(self.style.SUCCESS(f"Queued sync for: {s}"))
