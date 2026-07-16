import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ScrapedHospital:
    name: str
    address: str
    city: str
    state: str
    pincode: str = ""
    phone: str = ""
    plan_types: List[str] = field(default_factory=list)
    source_url: str = ""


class BaseInsuranceScraper(ABC):
    """
    Contract every insurance scraper must fulfill.
    Subclasses implement `scrape()` using Playwright.
    """

    insurance_slug: str  # must be set on subclass

    @abstractmethod
    def scrape(self) -> List[ScrapedHospital]:
        """Run Playwright scrape and return list of ScrapedHospital."""

    def run(self) -> List[ScrapedHospital]:
        logger.info("Starting scrape for %s", self.insurance_slug)
        results = self.scrape()
        logger.info("Finished scrape for %s — %d hospitals", self.insurance_slug, len(results))
        return results
