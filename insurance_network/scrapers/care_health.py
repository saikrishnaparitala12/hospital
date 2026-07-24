import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from .base import BaseInsuranceScraper, ScrapedHospital

logger = logging.getLogger(__name__)

CARE_HEALTH_OFFICIAL_NETWORK_URL = "https://www.careinsurance.com/health-plan-network-hospitals.html"
TURTLEMINT_CARE_NETWORK_URL = "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/"
REQUEST_TIMEOUT_SECONDS = 20
MAX_CITY_PAGES = int(os.environ.get("CARE_HEALTH_MAX_CITY_PAGES", "350"))
MAX_WORKERS = int(os.environ.get("CARE_HEALTH_SCRAPER_WORKERS", "10"))
PINCODE_RE = re.compile(r"\b(\d{6})\b")
SPACE_RE = re.compile(r"\s+")
CARE_CITY_URL_RE = re.compile(
    r"https://www\.turtlemintinsurance\.com/health-insurance/care/network-hospitals/[^/#?]+/?",
    re.IGNORECASE,
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

CITY_STATE = {
    "ahmedabad": "Gujarat",
    "bangalore": "Karnataka",
    "bengaluru": "Karnataka",
    "chandigarh": "Chandigarh",
    "chennai": "Tamil Nadu",
    "delhi": "Delhi",
    "faridabad": "Haryana",
    "gurgaon": "Haryana",
    "hyderabad": "Telangana",
    "kolkata": "West Bengal",
    "mumbai": "Maharashtra",
    "new-delhi": "Delhi",
    "noida": "Uttar Pradesh",
    "pune": "Maharashtra",
    "surat": "Gujarat",
}

SEED_CITY_URLS = [
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/delhi/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/mumbai/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/pune/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/hyderabad/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/bangalore/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/chennai/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/kolkata/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/ahmedabad/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/gurgaon/",
    "https://www.turtlemintinsurance.com/health-insurance/care/network-hospitals/noida/",
]


def _clean(value: str) -> str:
    value = unescape(value or "")
    value = value.replace("\xa0", " ")
    value = SPACE_RE.sub(" ", value)
    return value.strip(" -|,")


def _title_case(value: str) -> str:
    value = _clean(value)
    return value.title() if value.islower() or value.isupper() else value


def _extract_pincode(value: str) -> str:
    match = PINCODE_RE.search(value or "")
    return match.group(1) if match else ""


def _city_slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].lower()


def _city_from_url(url: str) -> str:
    return _city_slug_from_url(url).replace("-", " ").title()


def _state_from_city_slug(city_slug: str) -> str:
    return CITY_STATE.get(city_slug, "")


class _CareHospitalTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_target_table = False
        self._table_depth = 0
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table" and attrs_dict.get("id") == "hospitals-table":
            self._in_target_table = True
            self._table_depth = 1
            return

        if not self._in_target_table:
            return

        if tag == "table":
            self._table_depth += 1
        elif tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._current_cell = []
        elif self._current_cell is not None and tag in {"br", "p", "div"}:
            self._current_cell.append(" ")

    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag):
        if not self._in_target_table:
            return

        if tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(_clean(" ".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            row = [cell for cell in self._current_row if cell]
            if row:
                self.rows.append(row)
            self._current_row = None
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._in_target_table = False


def parse_care_health_page(html: str, source_url: str) -> list[ScrapedHospital]:
    parser = _CareHospitalTableParser()
    parser.feed(html or "")

    city_slug = _city_slug_from_url(source_url)
    city = _city_from_url(source_url)
    state = _state_from_city_slug(city_slug)
    hospitals: list[ScrapedHospital] = []

    for row in parser.rows:
        if row and row[0].lower() in {"hospital name", "address"}:
            continue

        if row and row[0].isdigit() and len(row) >= 3:
            name = row[1]
            address = row[2]
        elif len(row) >= 2:
            name = row[0]
            address = row[1]
        else:
            continue

        if not name or not address:
            continue

        hospitals.append(
            ScrapedHospital(
                name=_title_case(name),
                address=_title_case(address),
                city=city,
                state=state,
                pincode=_extract_pincode(address),
                phone="",
                plan_types=["Cashless Network Hospital"],
                source_url=source_url,
            )
        )

    return hospitals


def discover_care_health_city_urls(html: str) -> list[str]:
    urls: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', html or "", re.IGNORECASE):
        absolute_url = urljoin(TURTLEMINT_CARE_NETWORK_URL, href)
        if not CARE_CITY_URL_RE.fullmatch(absolute_url):
            continue
        if absolute_url.rstrip("/") == TURTLEMINT_CARE_NETWORK_URL.rstrip("/"):
            continue
        urls.add(absolute_url if absolute_url.endswith("/") else f"{absolute_url}/")

    return sorted(urls)


class CareHealthScraper(BaseInsuranceScraper):
    insurance_slug = "care-health"

    def scrape(self) -> list[ScrapedHospital]:
        city_urls = self._discover_city_pages()
        if MAX_CITY_PAGES > 0:
            city_urls = city_urls[:MAX_CITY_PAGES]

        hospitals: list[ScrapedHospital] = []
        with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as executor:
            future_to_url = {
                executor.submit(self._scrape_city_page, url): url
                for url in city_urls
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    page_hospitals = future.result()
                except Exception as exc:
                    logger.warning("Care Health scraper failed for %s: %s", url, exc)
                    continue

                logger.info("Care Health: parsed %d hospitals from %s", len(page_hospitals), url)
                hospitals.extend(page_hospitals)

        return self._dedupe(hospitals)

    def _discover_city_pages(self) -> list[str]:
        try:
            response = requests.get(
                TURTLEMINT_CARE_NETWORK_URL,
                headers=REQUEST_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            city_urls = discover_care_health_city_urls(response.text)
            if city_urls:
                return city_urls
        except requests.RequestException as exc:
            logger.warning("Care Health city discovery failed: %s", exc)

        return SEED_CITY_URLS

    def _scrape_city_page(self, url: str) -> list[ScrapedHospital]:
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return parse_care_health_page(response.text, url)

    def _dedupe(self, hospitals: list[ScrapedHospital]) -> list[ScrapedHospital]:
        deduped: list[ScrapedHospital] = []
        seen: set[tuple[str, str, str]] = set()

        for hospital in hospitals:
            key = (hospital.name.lower(), hospital.pincode, hospital.address.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(hospital)

        if not deduped:
            logger.warning(
                "Care Health scraper found no hospitals. Official reference: %s. "
                "Fallback source checked: %s",
                CARE_HEALTH_OFFICIAL_NETWORK_URL,
                TURTLEMINT_CARE_NETWORK_URL,
            )

        return deduped
