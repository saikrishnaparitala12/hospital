import logging
from typing import List

from .base import BaseInsuranceScraper, ScrapedHospital

logger = logging.getLogger(__name__)

STAR_HEALTH_URL = "https://www.starhealth.in/network-hospitals"


class StarHealthScraper(BaseInsuranceScraper):
    insurance_slug = "star-health"

    def scrape(self) -> List[ScrapedHospital]:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        hospitals: List[ScrapedHospital] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                page.goto(STAR_HEALTH_URL, timeout=60_000)
                page.wait_for_selector(".hospital-list, .network-hospital-item", timeout=30_000)
            except PlaywrightTimeout:
                logger.warning("StarHealth: page load timed out, returning partial results")
                browser.close()
                return hospitals

            while True:
                cards = page.query_selector_all(".network-hospital-item, .hospital-card")
                for card in cards:
                    try:
                        name = (card.query_selector(".hospital-name, h3, h4") or card).inner_text().strip()
                        address_el = card.query_selector(".hospital-address, .address, p")
                        address = address_el.inner_text().strip() if address_el else ""
                        city_el = card.query_selector(".city")
                        city = city_el.inner_text().strip() if city_el else ""
                        state_el = card.query_selector(".state")
                        state = state_el.inner_text().strip() if state_el else ""
                        pincode_el = card.query_selector(".pincode, .pin")
                        pincode = pincode_el.inner_text().strip() if pincode_el else ""
                        phone_el = card.query_selector(".phone, .contact")
                        phone = phone_el.inner_text().strip() if phone_el else ""

                        if name:
                            hospitals.append(
                                ScrapedHospital(
                                    name=name,
                                    address=address,
                                    city=city,
                                    state=state,
                                    pincode=pincode,
                                    phone=phone,
                                    plan_types=["cashless"],
                                    source_url=STAR_HEALTH_URL,
                                )
                            )
                    except Exception as exc:
                        logger.debug("StarHealth: skipping card — %s", exc)

                # Pagination — click "Next" if available
                next_btn = page.query_selector("a.next, button.next, [aria-label='Next']")
                if next_btn and next_btn.is_enabled():
                    try:
                        next_btn.click()
                        page.wait_for_load_state("networkidle", timeout=15_000)
                    except PlaywrightTimeout:
                        break
                else:
                    break

            browser.close()

        return hospitals
