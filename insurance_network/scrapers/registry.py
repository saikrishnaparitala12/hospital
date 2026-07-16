from .star_health import StarHealthScraper

# Registry: slug -> scraper class
# To add a new provider: create a scraper class and register it here.
SCRAPER_REGISTRY = {
    StarHealthScraper.insurance_slug: StarHealthScraper,
}


def get_scraper(slug: str):
    cls = SCRAPER_REGISTRY.get(slug)
    if cls is None:
        raise ValueError(f"No scraper registered for insurance slug: '{slug}'")
    return cls()
