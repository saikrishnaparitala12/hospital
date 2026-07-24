import logging
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_insurance_network(self, insurance_slug: str):
    """Scrape and sync hospital network for a single insurance provider."""
    from .services import SyncService

    try:
        log = SyncService.sync(insurance_slug)
        if log.status == "failed":
            raise RuntimeError(log.error_message or f"Sync failed for {insurance_slug}")
        return {"status": log.status, "hospitals_found": log.hospitals_found}
    except Exception as exc:
        logger.exception("Task failed for %s, retrying...", insurance_slug)
        raise self.retry(exc=exc)


@shared_task
def refresh_all_insurance_networks():
    """Periodic task: refresh all active insurance providers that have a registered scraper."""
    from .scrapers.registry import SCRAPER_REGISTRY
    from .services import InsuranceService

    for slug in SCRAPER_REGISTRY.keys():
        insurance, _ = InsuranceService.get_or_create_supported(slug)
        sync_insurance_network.delay(insurance.slug)

    logger.info("Queued refresh for %d insurance providers", len(SCRAPER_REGISTRY))
