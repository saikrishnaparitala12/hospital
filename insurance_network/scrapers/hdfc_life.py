import logging
import re
from dataclasses import dataclass
from typing import List
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .base import BaseInsuranceScraper, ScrapedHospital

logger = logging.getLogger(__name__)

HDFC_LIFE_CLAIMS_URL = "https://www.hdfclife.com/claims"
POLICYBAZAAR_HDFC_ERGO_NETWORK_URL = "https://www.policybazaar.com/network-hospitals/hdfc-ergo-network-hospitals/"

REQUEST_TIMEOUT_MS = 30_000
MAX_CITY_PAGES = 25
MAX_VIEW_MORE_CLICKS = 8
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-http2",
    "--disable-quic",
    "--no-sandbox",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
PINCODE_RE = re.compile(r"\b(\d{6})\b")
SPACE_RE = re.compile(r"\s+")
HOSPITAL_NAME_RE = re.compile(
    r"\b(hospitals?|medical|clinic|healthcare|nursing home|multispeciality|multi speciality)\b",
    re.IGNORECASE,
)
ADDRESS_RE = re.compile(
    r"(city\s*-|location\s*-|\b(?:road|rd|street|nagar|colony|sector|plot|floor|opp\.?|"
    r"opposite|near|main road|complex|building|tower|lane|marg|chowk|circle|pincode)\b)",
    re.IGNORECASE,
)
POLICYBAZAAR_CITY_URL_RE = re.compile(
    r"/network-hospitals/hdfc-ergo-hospitals-[^/]+/",
    re.IGNORECASE,
)
NOISE_RE = re.compile(
    r"\b(cashless hospitals|cashless network|network hospitals|preferred hospital network|"
    r"missing middle hospitals|locate hdfc|"
    r"happy customers|processed/min|always near you|search by state|hospital empanelment|"
    r"terms|privacy|download|newsletter|health insurance|motor insurance|policybazaar|"
    r"insurer highlights|people trust|registered consumers|insurance partners|policies sold|"
    r"select insurer|search hospital|consultation network|top hospitals|claim settled worth|"
    r"see details|view hospitals in this group|view more insurers|discover leading hospitals|"
    r"view details|check premium|claim process|step \d+|notify the insurance company)\b",
    re.IGNORECASE,
)
STOP_SECTION_RE = re.compile(
    r"\b(policybazaar claim process|network hospitals by other insurers|explore hdfc ergo|"
    r"hdfc ergo policyholders|network hospital faqs|discover leading hospitals|"
    r"health insurance for)\b",
    re.IGNORECASE,
)
START_SECTION_RE = re.compile(
    r"\b(more hospitals|cashless network|cashless network hospitals|network hospitals list)\b",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class PolicybazaarCityPage:
    url: str
    city: str
    state: str


SEED_CITY_PAGES = [
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-delhi-delhi/",
        "Delhi",
        "Delhi",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-maharashtra-mumbai/",
        "Mumbai",
        "Maharashtra",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-karnataka-bengaluru/",
        "Bengaluru",
        "Karnataka",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-tamil_nadu-chennai/",
        "Chennai",
        "Tamil Nadu",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-maharashtra-hyderabad/",
        "Hyderabad",
        "Telangana",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-west_bengal-kolkata/",
        "Kolkata",
        "West Bengal",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-gujarat-pune/",
        "Pune",
        "Maharashtra",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-maharashtra-navi_mumbai/",
        "Navi Mumbai",
        "Maharashtra",
    ),
    PolicybazaarCityPage(
        "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-maharashtra-thane/",
        "Thane",
        "Maharashtra",
    ),
]


def _clean(value: str) -> str:
    return SPACE_RE.sub(" ", value or "").strip(" -|,")


def _extract_pincode(value: str) -> str:
    match = PINCODE_RE.search(value or "")
    return match.group(1) if match else ""


def _looks_like_address(line: str) -> bool:
    return bool(PINCODE_RE.search(line) or ADDRESS_RE.search(line))


def _looks_like_hospital_name(line: str) -> bool:
    if not line or NOISE_RE.search(line):
        return False
    words = line.split()
    return 2 <= len(words) <= 14 and bool(HOSPITAL_NAME_RE.search(line))


def _looks_like_candidate_name(line: str) -> bool:
    if not line or NOISE_RE.search(line) or _looks_like_address(line):
        return False
    words = line.split()
    if not 2 <= len(words) <= 18:
        return False
    return any(char.isalpha() for char in line)


def _address_parts_after(lines: list[str], index: int) -> list[str]:
    parts: list[str] = []

    for next_line in lines[index + 1 : index + 6]:
        if not next_line or NOISE_RE.search(next_line):
            continue
        if parts and (_looks_like_hospital_name(next_line) or _looks_like_candidate_name(next_line)):
            break
        if _looks_like_address(next_line):
            parts.append(next_line)
            continue
        if parts:
            break

    return parts


def _city_state_from_policybazaar_url(url: str, fallback_city: str = "", fallback_state: str = "") -> tuple[str, str]:
    slug = url.rstrip("/").split("/")[-1]
    prefix = "hdfc-ergo-hospitals-"
    if not slug.startswith(prefix):
        return fallback_city, fallback_state

    location_slug = slug.removeprefix(prefix)
    state_slug, _, city_slug = location_slug.rpartition("-")
    city = (city_slug or fallback_city).replace("_", " ").title()
    state = (state_slug or fallback_state).replace("_", " ").title()
    return city or fallback_city, state or fallback_state


def parse_hdfc_life_network_text(
    text: str,
    source_url: str,
    default_city: str = "",
    default_state: str = "",
) -> list[ScrapedHospital]:
    lines = [_clean(line) for line in (text or "").splitlines()]
    lines = [line for line in lines if line]

    hospitals: list[ScrapedHospital] = []
    seen: set[tuple[str, str]] = set()
    in_network_section = False

    for index, line in enumerate(lines):
        if START_SECTION_RE.search(line):
            in_network_section = True
            continue
        if in_network_section and STOP_SECTION_RE.search(line):
            break

        address_parts = _address_parts_after(lines, index)
        is_hospital_name = _looks_like_hospital_name(line)
        is_name_with_address = _looks_like_candidate_name(line) and bool(address_parts)
        if not (is_hospital_name or is_name_with_address):
            continue

        address = _clean(" ".join(address_parts))
        if not address:
            continue

        pincode = _extract_pincode(address)
        key = (line.lower(), pincode)
        if key in seen:
            continue
        seen.add(key)

        hospitals.append(
            ScrapedHospital(
                name=line.title() if line.isupper() else line,
                address=address,
                city=default_city,
                state=default_state,
                pincode=pincode,
                phone="",
                plan_types=["Network Hospital"],
                source_url=source_url,
            )
        )

    return hospitals


class HdfcLifeScraper(BaseInsuranceScraper):
    insurance_slug = "hdfc-life"

    def scrape(self) -> List[ScrapedHospital]:
        hospitals: list[ScrapedHospital] = []

        try:
            with sync_playwright() as playwright:
                browser = self._launch_browser(playwright)
                try:
                    context = browser.new_context(
                        user_agent=USER_AGENT,
                        locale="en-IN",
                        viewport={"width": 1366, "height": 900},
                        extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
                    )
                    page = context.new_page()
                    page.set_default_timeout(REQUEST_TIMEOUT_MS)
                    city_pages = self._discover_city_pages(page)

                    for city_page in city_pages[:MAX_CITY_PAGES]:
                        page_hospitals = self._scrape_city_page(page, city_page)
                        logger.info(
                            "Policybazaar HDFC ERGO network: parsed %d hospitals for %s",
                            len(page_hospitals),
                            city_page.city,
                        )
                        hospitals.extend(page_hospitals)
                finally:
                    browser.close()
        except PlaywrightError as exc:
            logger.exception("HDFC Life/HDFC ERGO Policybazaar scraper failed: %s", exc)
            return []

        return self._dedupe(hospitals)

    def _launch_browser(self, playwright):
        try:
            return playwright.chromium.launch(channel="chrome", headless=True, args=BROWSER_ARGS)
        except PlaywrightError as exc:
            logger.warning("System Chrome launch failed, falling back to Playwright Chromium: %s", exc)
            return playwright.chromium.launch(headless=True, args=BROWSER_ARGS)

    def _discover_city_pages(self, page) -> list[PolicybazaarCityPage]:
        try:
            self._open_page(page, POLICYBAZAAR_HDFC_ERGO_NETWORK_URL)
            discovered: dict[str, PolicybazaarCityPage] = {}
            links = page.locator("a[href*='/network-hospitals/hdfc-ergo-hospitals-']")
            for index in range(min(links.count(), MAX_CITY_PAGES)):
                href = links.nth(index).get_attribute("href")
                if not href:
                    continue
                absolute_url = urljoin(POLICYBAZAAR_HDFC_ERGO_NETWORK_URL, href)
                if not POLICYBAZAAR_CITY_URL_RE.search(absolute_url):
                    continue
                city, state = _city_state_from_policybazaar_url(absolute_url)
                discovered[absolute_url] = PolicybazaarCityPage(absolute_url, city, state)

            if discovered:
                return list(discovered.values())
        except PlaywrightError as exc:
            logger.warning("Could not discover Policybazaar HDFC ERGO city pages: %s", exc)

        return SEED_CITY_PAGES

    def _scrape_city_page(self, page, city_page: PolicybazaarCityPage) -> list[ScrapedHospital]:
        try:
            self._open_page(page, city_page.url)
            self._expand_hospital_list(page)
            visible_text = page.locator("body").inner_text(timeout=REQUEST_TIMEOUT_MS)
            return parse_hdfc_life_network_text(
                visible_text,
                city_page.url,
                default_city=city_page.city,
                default_state=city_page.state,
            )
        except PlaywrightError as exc:
            logger.warning("Policybazaar HDFC ERGO scraper could not read %s: %s", city_page.url, exc)
            return []

    def _open_page(self, page, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except PlaywrightError:
            logger.debug("Policybazaar page still had network activity after initial load: %s", url)

    def _expand_hospital_list(self, page) -> None:
        for _ in range(MAX_VIEW_MORE_CLICKS):
            try:
                page.mouse.wheel(0, 3500)
                page.wait_for_timeout(600)
                button = page.get_by_text(re.compile(r"^View more hospitals$", re.I)).last
                if not button.is_visible(timeout=1000):
                    break
                button.click()
                page.wait_for_timeout(1200)
            except PlaywrightError:
                break

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
                "HDFC Life/HDFC ERGO scraper found no hospitals. Checked Policybazaar network pages from %s. "
                "HDFC Life claims reference: %s",
                POLICYBAZAAR_HDFC_ERGO_NETWORK_URL,
                HDFC_LIFE_CLAIMS_URL,
            )

        return deduped
