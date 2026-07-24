import logging
from datetime import timedelta
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Hospital, InsuranceCompany, InsuranceHospitalNetwork, ScrapeLog
from .scrapers.base import ScrapedHospital
from .utils import geocode_address, normalize_text

logger = logging.getLogger(__name__)

STALE_AFTER_HOURS = getattr(settings, "INSURANCE_NETWORK_STALE_AFTER_HOURS", 24)


class InsuranceProviderNotSupported(ValueError):
    def __init__(self, identifier: str, suggestions: list[str] | None = None):
        self.identifier = identifier
        self.suggestions = suggestions or []
        super().__init__(f"Insurance provider is not supported: {identifier}")


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    earth_radius_km = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(value))


class InsuranceRepository:
    @staticmethod
    def active():
        return InsuranceCompany.objects.filter(is_active=True)

    @staticmethod
    def get_by_slug(slug: str) -> InsuranceCompany | None:
        return InsuranceCompany.objects.filter(slug=slug, is_active=True).first()

    @staticmethod
    def get_or_create_from_entry(entry) -> tuple[InsuranceCompany, bool]:
        insurance, created = InsuranceCompany.objects.get_or_create(
            slug=entry.slug,
            defaults={
                "name": entry.name,
                "website": entry.website,
                "logo_url": entry.logo_url,
                "is_active": True,
            },
        )

        update_fields = []
        for field in ["name", "website", "logo_url"]:
            value = getattr(entry, field)
            if getattr(insurance, field) != value:
                setattr(insurance, field, value)
                update_fields.append(field)

        if not insurance.is_active:
            insurance.is_active = True
            update_fields.append("is_active")

        if update_fields:
            insurance.save(update_fields=update_fields)

        return insurance, created


class HospitalRepository:
    @staticmethod
    def has_network(insurance: InsuranceCompany) -> bool:
        return InsuranceHospitalNetwork.objects.filter(
            insurance=insurance,
            is_active=True,
        ).exists()

    @staticmethod
    def by_insurance(insurance_slug: str):
        return (
            Hospital.objects.filter(
                insurance_networks__insurance__slug=insurance_slug,
                insurance_networks__is_active=True,
            )
            .distinct()
            .order_by("name")
        )


class InsuranceService:
    @staticmethod
    def _normalized_text(value: str) -> str:
        return normalize_text(value or "")

    @staticmethod
    def _match_score(query: str, candidate: str) -> float:
        query_norm = InsuranceService._normalized_text(query)
        candidate_norm = InsuranceService._normalized_text(candidate)
        if not query_norm or not candidate_norm:
            return 0.0
        if query_norm == candidate_norm:
            return 1.0
        if query_norm in candidate_norm or candidate_norm in query_norm:
            return 0.95
        return SequenceMatcher(None, query_norm, candidate_norm).ratio()

    @staticmethod
    def _entry_matches_query(entry, query: str) -> bool:
        if not query:
            return True
        values = [entry.slug, entry.name, *entry.aliases]
        return any(
            query.lower() in value.lower()
            or InsuranceService._match_score(query, value) >= 0.45
            for value in values
        )

    @staticmethod
    def search(query: str) -> list[InsuranceCompany]:
        from .scrapers.registry import all_known_insurers

        query = (query or "").strip()
        db_by_slug = {
            insurance.slug: insurance
            for insurance in InsuranceRepository.active()
        }

        results: list[InsuranceCompany] = []
        for entry in all_known_insurers():
            if not InsuranceService._entry_matches_query(entry, query):
                continue
            results.append(
                db_by_slug.get(entry.slug)
                or InsuranceCompany(
                    name=entry.name,
                    slug=entry.slug,
                    website=entry.website,
                    logo_url=entry.logo_url,
                    is_active=True,
                )
            )

        return results

    @staticmethod
    def supported_provider_names() -> list[str]:
        from .scrapers.registry import all_known_insurers

        return [entry.name for entry in all_known_insurers()]

    @staticmethod
    def suggestions(identifier: str, limit: int = 5) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()

        from .scrapers.registry import all_known_insurers

        for entry in all_known_insurers():
            for value in [entry.name, entry.slug, *entry.aliases]:
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)

        return sorted(
            values,
            key=lambda value: (
                -InsuranceService._match_score(identifier, value),
                value.lower(),
            ),
        )[:limit]

    @staticmethod
    def get_or_create_supported(identifier: str) -> tuple[InsuranceCompany, bool]:
        from .scrapers.registry import get_scraper_entry

        entry = get_scraper_entry(identifier)
        if entry is None:
            raise InsuranceProviderNotSupported(
                identifier,
                suggestions=InsuranceService.suggestions(identifier),
            )
        return InsuranceRepository.get_or_create_from_entry(entry)


class SyncService:
    @staticmethod
    def is_stale(insurance: InsuranceCompany) -> bool:
        if insurance.last_scraped_at is None:
            return True
        threshold = timezone.now() - timedelta(hours=STALE_AFTER_HOURS)
        return insurance.last_scraped_at < threshold

    @staticmethod
    def has_hospitals(insurance: InsuranceCompany) -> bool:
        return HospitalRepository.has_network(insurance)

    @staticmethod
    def trigger_background_sync(insurance: InsuranceCompany) -> bool:
        try:
            from .tasks import sync_insurance_network

            sync_insurance_network.delay(insurance.slug)
            logger.info("Queued insurance network sync for %s", insurance.slug)
            return True
        except Exception:
            logger.exception("Could not queue insurance network sync for %s", insurance.slug)
            return False

    @staticmethod
    def _finish_log(
        log: ScrapeLog,
        status: str,
        hospitals_found: int = 0,
        error_message: str = "",
    ) -> ScrapeLog:
        log.status = status
        log.hospitals_found = hospitals_found
        log.error_message = error_message
        log.finished_at = timezone.now()
        log.save(update_fields=["status", "hospitals_found", "error_message", "finished_at"])
        return log

    @staticmethod
    def sync(insurance_slug: str, geocode: bool = True) -> ScrapeLog:
        from .scrapers.registry import get_scraper, get_scraper_entry

        insurance, _ = InsuranceService.get_or_create_supported(insurance_slug)
        log = ScrapeLog.objects.create(
            insurance=insurance,
            status="running",
            started_at=timezone.now(),
        )

        try:
            entry = get_scraper_entry(insurance.slug)
            if entry is None:
                message = f"No scraper registered for {insurance.slug}"
                logger.warning(message)
                return SyncService._finish_log(log, "failed", error_message=message)

            scraped = get_scraper(entry.slug).run()
            if not scraped:
                message = f"Scraper returned no hospitals for {entry.name}"
                logger.warning(message)
                return SyncService._finish_log(log, "failed", error_message=message)

            saved = SyncService._save_scraped_hospitals(insurance, scraped, geocode=geocode)
            insurance.last_scraped_at = timezone.now()
            insurance.save(update_fields=["last_scraped_at"])

            logger.info("Insurance network sync complete for %s: %s hospitals", insurance.slug, saved)
            return SyncService._finish_log(log, "success", hospitals_found=saved)
        except Exception as exc:
            logger.exception("Insurance network sync failed for %s", insurance.slug)
            return SyncService._finish_log(log, "failed", error_message=str(exc))

    @staticmethod
    def _save_scraped_hospitals(
        insurance: InsuranceCompany,
        scraped: list[ScrapedHospital],
        geocode: bool = True,
    ) -> int:
        saved = 0

        for item in scraped:
            normalized_name = normalize_text(item.name)
            normalized_address = normalize_text(item.address)

            with transaction.atomic():
                hospital, created = Hospital.objects.get_or_create(
                    normalized_name=normalized_name,
                    normalized_address=normalized_address,
                    pincode=item.pincode,
                    defaults={
                        "name": item.name,
                        "address": item.address,
                        "city": item.city,
                        "state": item.state,
                        "phone": item.phone,
                    },
                )

                update_fields = []
                if not created:
                    for field, value in {
                        "name": item.name,
                        "address": item.address,
                        "normalized_address": normalized_address,
                        "city": item.city,
                        "state": item.state,
                        "phone": item.phone,
                    }.items():
                        if value and getattr(hospital, field) != value:
                            setattr(hospital, field, value)
                            update_fields.append(field)

                if geocode and hospital.latitude is None:
                    lat, lon = geocode_address(item.address, item.city, item.state, item.pincode)
                    if lat is not None and lon is not None:
                        hospital.latitude = lat
                        hospital.longitude = lon
                        hospital.geocoded_at = timezone.now()
                        update_fields.extend(["latitude", "longitude", "geocoded_at"])

                if update_fields:
                    hospital.save(update_fields=list(dict.fromkeys(update_fields)))

                InsuranceHospitalNetwork.objects.update_or_create(
                    insurance=insurance,
                    hospital=hospital,
                    defaults={
                        "plan_types": item.plan_types,
                        "source_url": item.source_url,
                        "is_active": True,
                    },
                )
                saved += 1

        return saved


class HospitalService:
    @staticmethod
    def by_insurance(insurance_slug: str):
        return HospitalRepository.by_insurance(insurance_slug)

    @staticmethod
    def nearby(lat: float, lon: float, radius_km: float = 10) -> list:
        candidates = Hospital.objects.exclude(latitude=None).values(
            "id",
            "name",
            "address",
            "city",
            "state",
            "latitude",
            "longitude",
            "phone",
        )
        return _filter_by_radius(candidates, lat, lon, radius_km)

    @staticmethod
    def nearby_by_insurance(lat: float, lon: float, insurance_slug: str, radius_km: float = 10) -> list:
        candidates = (
            Hospital.objects.filter(
                insurance_networks__insurance__slug=insurance_slug,
                insurance_networks__is_active=True,
            )
            .exclude(latitude=None)
            .values("id", "name", "address", "city", "state", "latitude", "longitude", "phone")
            .distinct()
        )
        return _filter_by_radius(candidates, lat, lon, radius_km)


def _filter_by_radius(candidates, lat, lon, radius_km) -> list:
    results = []
    for hospital in candidates:
        distance = _haversine_km(lat, lon, float(hospital["latitude"]), float(hospital["longitude"]))
        if distance <= radius_km:
            hospital["distance_km"] = round(distance, 2)
            results.append(hospital)

    results.sort(key=lambda item: item["distance_km"])
    return results
