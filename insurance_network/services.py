import logging
from datetime import timedelta
from math import radians, cos, sin, asin, sqrt

from django.db import transaction
from django.utils import timezone

from .models import InsuranceCompany, Hospital, InsuranceHospitalNetwork, ScrapeLog
from .scrapers.registry import get_scraper
from .utils import normalize_text, geocode_address

logger = logging.getLogger(__name__)

STALE_AFTER_HOURS = 24  # re-scrape if data older than this


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


class InsuranceNetworkService:

    # ------------------------------------------------------------------ #
    #  Read operations (used by API views)                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def search_insurance(query: str):
        qs = InsuranceCompany.objects.filter(is_active=True)
        if query:
            qs = qs.filter(name__icontains=query)
        return qs

    @staticmethod
    def hospitals_by_insurance(insurance_slug: str):
        return (
            Hospital.objects.filter(
                insurance_networks__insurance__slug=insurance_slug,
                insurance_networks__is_active=True,
            )
            .select_related()
            .distinct()
        )

    @staticmethod
    def nearby_hospitals(lat: float, lon: float, radius_km: float = 10):
        """
        Pure-Python haversine filter (works without PostGIS).
        For large datasets, replace with a PostGIS ST_DWithin query.
        """
        candidates = Hospital.objects.exclude(latitude=None).values(
            "id", "name", "city", "state", "address", "latitude", "longitude", "phone"
        )
        results = []
        for h in candidates:
            dist = _haversine_km(lat, lon, float(h["latitude"]), float(h["longitude"]))
            if dist <= radius_km:
                h["distance_km"] = round(dist, 2)
                results.append(h)
        results.sort(key=lambda x: x["distance_km"])
        return results

    @staticmethod
    def nearby_hospitals_by_insurance(lat: float, lon: float, insurance_slug: str, radius_km: float = 10):
        candidates = (
            Hospital.objects.filter(
                insurance_networks__insurance__slug=insurance_slug,
                insurance_networks__is_active=True,
            )
            .exclude(latitude=None)
            .values("id", "name", "city", "state", "address", "latitude", "longitude", "phone")
            .distinct()
        )
        results = []
        for h in candidates:
            dist = _haversine_km(lat, lon, float(h["latitude"]), float(h["longitude"]))
            if dist <= radius_km:
                h["distance_km"] = round(dist, 2)
                results.append(h)
        results.sort(key=lambda x: x["distance_km"])
        return results

    # ------------------------------------------------------------------ #
    #  Staleness check — called before returning API data                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_data_stale(insurance: InsuranceCompany) -> bool:
        if insurance.last_scraped_at is None:
            return True
        return insurance.last_scraped_at < timezone.now() - timedelta(hours=STALE_AFTER_HOURS)

    # ------------------------------------------------------------------ #
    #  Sync — called by Celery task (never during API request)             #
    # ------------------------------------------------------------------ #

    @classmethod
    def sync_insurance(cls, insurance_slug: str) -> ScrapeLog:
        insurance = InsuranceCompany.objects.get(slug=insurance_slug)
        log = ScrapeLog.objects.create(insurance=insurance, status="running", started_at=timezone.now())

        try:
            scraper = get_scraper(insurance_slug)
            scraped = scraper.run()

            saved = 0
            for item in scraped:
                norm_name = normalize_text(item.name)
                norm_addr = normalize_text(item.address)

                with transaction.atomic():
                    hospital, created = Hospital.objects.get_or_create(
                        normalized_name=norm_name,
                        pincode=item.pincode,
                        defaults={
                            "name": item.name,
                            "normalized_address": norm_addr,
                            "address": item.address,
                            "city": item.city,
                            "state": item.state,
                            "phone": item.phone,
                        },
                    )

                    # Geocode only once
                    if hospital.latitude is None:
                        lat, lon = geocode_address(item.address, item.city, item.state, item.pincode)
                        if lat:
                            hospital.latitude = lat
                            hospital.longitude = lon
                            hospital.geocoded_at = timezone.now()
                            hospital.save(update_fields=["latitude", "longitude", "geocoded_at"])

                    InsuranceHospitalNetwork.objects.update_or_create(
                        insurance=insurance,
                        hospital=hospital,
                        defaults={"plan_types": item.plan_types, "source_url": item.source_url, "is_active": True},
                    )
                    saved += 1

            insurance.last_scraped_at = timezone.now()
            insurance.save(update_fields=["last_scraped_at"])

            log.status = "success"
            log.hospitals_found = saved
            log.finished_at = timezone.now()
            log.save()
            logger.info("Sync complete for %s — %d hospitals saved", insurance_slug, saved)

        except Exception as exc:
            log.status = "failed"
            log.error_message = str(exc)
            log.finished_at = timezone.now()
            log.save()
            logger.exception("Sync failed for %s", insurance_slug)

        return log
