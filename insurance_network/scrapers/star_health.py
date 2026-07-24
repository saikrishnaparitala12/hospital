import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import List

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .base import BaseInsuranceScraper, ScrapedHospital

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_MS = 30_000
STAR_HEALTH_LOOKUP_URL = "https://www.starhealth.in/lookup/hospital/"

PINCODE_RE = re.compile(r"\b(\d{6})\b")
PHONE_RE = re.compile(r"[\d\s()+-]{6,}")
SPACE_RE = re.compile(r"\s+")

STAR_HEALTH_CITY_PAGES = [
    ("chennai", "Chennai", "Tamil Nadu"),
    ("hyderabad", "Hyderabad", "Telangana"),
    ("bangalore", "Bangalore", "Karnataka"),
    ("delhi", "Delhi", "Delhi"),
    ("mumbai", "Mumbai", "Maharashtra"),
    ("pune", "Pune", "Maharashtra"),
    ("kolkata", "Kolkata", "West Bengal"),
    ("ahmedabad", "Ahmedabad", "Gujarat"),
    ("nagpur", "Nagpur", "Maharashtra"),
]


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table_depth += 1
            self._current_table = []
        elif self._table_depth and tag == "tr":
            self._current_row = []
        elif self._table_depth and tag in {"td", "th"}:
            self._current_cell = []
        elif self._current_cell is not None and tag in {"br", "p", "div"}:
            self._current_cell.append(" ")

    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(_clean(" ".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            row = [cell for cell in self._current_row if cell]
            if row and self._current_table is not None:
                self._current_table.append(row)
            self._current_row = None
        elif tag == "table" and self._table_depth:
            if self._current_table:
                self.tables.append(self._current_table)
            self._table_depth -= 1
            self._current_table = None


def _clean(value: str) -> str:
    value = unescape(value or "")
    value = value.replace("\xa0", " ")
    value = SPACE_RE.sub(" ", value)
    return value.strip(" -|,")


def _page_url(city_slug: str) -> str:
    return f"https://www.starhealth.in/health-insurance/{city_slug}/"


def _extract_pincode(address: str) -> str:
    match = PINCODE_RE.search(address or "")
    return match.group(1) if match else ""


def _is_hospital_header(row: list[str]) -> bool:
    text = " ".join(row).lower()
    return "hospital" in text and "address" in text


def _is_noise_row(row: list[str]) -> bool:
    text = " ".join(row).lower()
    first = row[0].lower()
    return (
        first in {"hospital name", "network hospital name", "type"}
        or "branch office" in first
        or "area office" in first
        or "zonal office" in first
        or "click here" in text
        or "list of network hospitals" in text
    )


def _row_to_hospital(
    row: list[str],
    source_url: str,
    default_city: str,
    default_state: str,
) -> ScrapedHospital | None:
    if row and row[0].isdigit() and len(row) >= 3:
        row = row[1:]

    if len(row) < 2 or _is_noise_row(row):
        return None

    name = _clean(row[0])
    address = _clean(row[1])
    phone = _clean(row[2]) if len(row) >= 3 else ""
    plan_type = _clean(row[3]) if len(row) >= 4 else "Network Hospital"

    if len(row) == 2 and PHONE_RE.search(address):
        parts = address.rsplit(" ", 1)
        if len(parts) == 2 and PHONE_RE.fullmatch(parts[1]) and not PINCODE_RE.fullmatch(parts[1]):
            address, phone = parts

    if not name or not address or len(name) < 3:
        return None

    return ScrapedHospital(
        name=name.title() if name.isupper() else name,
        address=address.title() if address.isupper() else address,
        city=default_city,
        state=default_state,
        pincode=_extract_pincode(address),
        phone="" if phone in {"-", "NA", "N/A"} else phone,
        plan_types=[plan_type] if plan_type else ["Network Hospital"],
        source_url=source_url,
    )


def parse_star_health_page(html: str, source_url: str, city: str, state: str) -> list[ScrapedHospital]:
    parser = _TableParser()
    parser.feed(html)

    hospitals: list[ScrapedHospital] = []
    for table in parser.tables:
        if not any(_is_hospital_header(row) for row in table[:3]):
            continue

        for row in table:
            hospital = _row_to_hospital(row, source_url, city, state)
            if hospital:
                hospitals.append(hospital)

    return hospitals


class StarHealthScraper(BaseInsuranceScraper):
    insurance_slug = "star-health"

    def scrape(self) -> List[ScrapedHospital]:
        hospitals: list[ScrapedHospital] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_timeout(REQUEST_TIMEOUT_MS)

                for city_slug, city, state in STAR_HEALTH_CITY_PAGES:
                    url = _page_url(city_slug)
                    try:
                        page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT_MS)
                        page_hospitals = parse_star_health_page(page.content(), url, city, state)
                        logger.info("StarHealth: parsed %d hospitals from %s", len(page_hospitals), url)
                        hospitals.extend(page_hospitals)
                    except PlaywrightError as exc:
                        logger.warning("StarHealth: failed to scrape %s: %s", url, exc)

                browser.close()
        except PlaywrightError as exc:
            logger.exception("StarHealth: Playwright failed: %s", exc)
            return []

        return self._dedupe(hospitals)

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
            logger.warning("StarHealth: no hospitals parsed from configured pages")

        return deduped
