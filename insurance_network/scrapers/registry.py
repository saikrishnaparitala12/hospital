from dataclasses import dataclass
from typing import Type, Optional
from django.utils.text import slugify
from .base import BaseInsuranceScraper
from .hdfc_life import HdfcLifeScraper
from .star_health import StarHealthScraper


@dataclass(frozen=True)
class ScraperEntry:
    """Metadata + scraper class for one insurance provider."""
    slug: str
    name: str
    website: str
    logo_url: str
    scraper_class: Type[BaseInsuranceScraper]
    aliases: tuple[str, ...] = ()

    def make_scraper(self) -> BaseInsuranceScraper:
        return self.scraper_class()


# ---------------------------------------------------------------
# Registry — add a new provider by adding one entry here.
# No changes needed anywhere else.
# ---------------------------------------------------------------
SCRAPER_REGISTRY: dict[str, ScraperEntry] = {
    "star-health": ScraperEntry(
        slug="star-health",
        name="Star Health and Allied Insurance",
        website="https://www.starhealth.in",
        logo_url="https://www.starhealth.in/images/logo.png",
        scraper_class=StarHealthScraper,
        aliases=(
            "Star Health",
            "Star Health Insurance",
            "Star Health and Allied",
        ),
    ),
    "hdfc-life": ScraperEntry(
        slug="hdfc-life",
        name="HDFC Life Insurance",
        website="https://www.hdfclife.com/claims",
        logo_url="",
        scraper_class=HdfcLifeScraper,
        aliases=(
            "HDFC Life",
            "HDFC Life Insurance",
            "HDFC-Lif",
            "HDFC Life Health",
            "HDFC ERGO",
            "HDFC Ergo",
            "HDFC ERGO Health",
            "HDFC ERGO Health Insurance",
            "HDFC ERGO General Insurance",
            "hdfc-ergo",
            "Click 2 Protect Health",
            "Click 2 Protect Optima Secure",
        ),
    ),
    # To add a new provider:
    # "care-health": ScraperEntry(
    #     slug="care-health",
    #     name="Care Health Insurance",
    #     website="https://www.careinsurance.com",
    #     logo_url="",
    #     scraper_class=CareHealthScraper,
    # ),
}


def get_scraper_entry(slug: str) -> Optional[ScraperEntry]:
    """Returns ScraperEntry or None if no scraper exists for this slug."""
    normalized_slug = slugify(slug or "")
    if normalized_slug in SCRAPER_REGISTRY:
        return SCRAPER_REGISTRY[normalized_slug]

    for entry in SCRAPER_REGISTRY.values():
        aliases = (entry.slug, entry.name, *entry.aliases)
        if normalized_slug in {slugify(alias or "") for alias in aliases}:
            return entry

    return None


def get_scraper(slug: str) -> BaseInsuranceScraper:
    """Returns a scraper instance. Raises ValueError if not registered."""
    entry = get_scraper_entry(slug)
    if entry is None:
        raise ValueError(f"No scraper registered for: '{slug}'")
    return entry.make_scraper()


def all_known_insurers() -> list[ScraperEntry]:
    """Returns all registered insurance providers."""
    return list(SCRAPER_REGISTRY.values())
