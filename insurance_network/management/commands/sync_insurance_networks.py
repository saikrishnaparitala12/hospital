from django.core.management.base import BaseCommand
from insurance_network.scrapers.registry import SCRAPER_REGISTRY


class Command(BaseCommand):
    help = "Trigger insurance hospital network sync. Use --slug to sync one provider."

    def add_arguments(self, parser):
        parser.add_argument("--slug", type=str, help="Insurance slug (omit to sync all registered)")
        parser.add_argument("--sync", action="store_true", help="Run synchronously instead of via Celery")
        parser.add_argument(
            "--no-geocode",
            action="store_true",
            help="Skip geocoding during a synchronous sync. Useful for fast scraper smoke tests.",
        )

    def handle(self, *args, **options):
        slug = options.get("slug")
        run_sync = options.get("sync")

        slugs = [slug] if slug else list(SCRAPER_REGISTRY.keys())

        for s in slugs:
            from insurance_network.services import InsuranceProviderNotSupported, InsuranceService

            try:
                insurance, created = InsuranceService.get_or_create_supported(s)
            except InsuranceProviderNotSupported as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                continue

            if run_sync:
                from insurance_network.services import SyncService

                if created:
                    self.stdout.write(self.style.WARNING(f"Auto-created InsuranceCompany: {insurance.slug}"))
                log = SyncService.sync(insurance.slug, geocode=not options.get("no_geocode"))
                self.stdout.write(self.style.SUCCESS(f"{insurance.slug}: {log.status} — {log.hospitals_found} hospitals"))
            else:
                from insurance_network.tasks import sync_insurance_network

                sync_insurance_network.delay(insurance.slug)
                self.stdout.write(self.style.SUCCESS(f"Queued sync for: {insurance.slug}"))
