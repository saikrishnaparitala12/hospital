import logging
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_insurance_network(self, insurance_slug: str):
    """Scrape and sync hospital network for a single insurance provider."""
    from .services import InsuranceNetworkService
    try:
        log = InsuranceNetworkService.sync_insurance(insurance_slug)
        return {"status": log.status, "hospitals_found": log.hospitals_found}
    except Exception as exc:
        logger.exception("Task failed for %s, retrying...", insurance_slug)
        raise self.retry(exc=exc)


@shared_task
def refresh_all_insurance_networks():
    """Periodic task: refresh all active insurance providers."""
    from .models import InsuranceCompany
    slugs = InsuranceCompany.objects.filter(is_active=True).values_list("slug", flat=True)
    for slug in slugs:
        sync_insurance_network.delay(slug)
    logger.info("Queued refresh for %d insurance providers", len(slugs))
