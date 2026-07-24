from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase

from .models import Hospital, InsuranceCompany, InsuranceHospitalNetwork
from .scrapers.base import ScrapedHospital
from .scrapers.hdfc_life import parse_hdfc_life_network_text
from .scrapers.registry import get_scraper_entry
from .scrapers.star_health import parse_star_health_page
from .services import InsuranceProviderNotSupported, InsuranceService, SyncService


class InsuranceServiceTests(TestCase):
    def test_search_returns_registered_provider_without_db_row(self):
        results = InsuranceService.search("star")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].slug, "star-health")
        self.assertIsNone(results[0].pk)

    def test_get_or_create_supported_creates_registry_provider(self):
        insurance, created = InsuranceService.get_or_create_supported("Star Health")

        self.assertTrue(created)
        self.assertEqual(insurance.slug, "star-health")
        self.assertEqual(insurance.name, "Star Health and Allied Insurance")

    def test_get_or_create_supported_creates_hdfc_life_provider(self):
        insurance, created = InsuranceService.get_or_create_supported("HDFC-Lif")

        self.assertTrue(created)
        self.assertEqual(insurance.slug, "hdfc-life")
        self.assertEqual(insurance.name, "HDFC Life Insurance")

    def test_get_or_create_supported_rejects_unknown_provider(self):
        with self.assertRaises(InsuranceProviderNotSupported):
            InsuranceService.get_or_create_supported("Unknown Cover")


class ScraperRegistryTests(TestCase):
    def test_registry_resolves_alias(self):
        entry = get_scraper_entry("Star Health")

        self.assertEqual(entry.slug, "star-health")

    def test_registry_resolves_hdfc_life_alias(self):
        entry = get_scraper_entry("HDFC-Lif")

        self.assertEqual(entry.slug, "hdfc-life")

    def test_registry_resolves_hdfc_ergo_alias(self):
        entry = get_scraper_entry("hdfc-ergo")

        self.assertEqual(entry.slug, "hdfc-life")

    def test_star_health_parser_extracts_table_rows(self):
        html = """
        <table>
          <tr><th>Hospital Name</th><th>Address</th><th>Phone</th><th>Type</th></tr>
          <tr>
            <td>Apollo Hospitals</td>
            <td>21 Greams Road, Chennai 600006</td>
            <td>044-28290200</td>
            <td>Cashless</td>
          </tr>
        </table>
        """

        hospitals = parse_star_health_page(html, "https://example.com", "Chennai", "Tamil Nadu")

        self.assertEqual(len(hospitals), 1)
        self.assertEqual(hospitals[0].name, "Apollo Hospitals")
        self.assertEqual(hospitals[0].pincode, "600006")
        self.assertEqual(hospitals[0].plan_types, ["Cashless"])

    def test_hdfc_life_parser_extracts_visible_network_text(self):
        text = """
        Apollo Hospitals
        21 Greams Road, Chennai 600006
        Fortis Medical Centre
        Sector 62, Noida 201301
        """

        hospitals = parse_hdfc_life_network_text(
            text,
            "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-tamil_nadu-chennai/",
            default_city="Chennai",
            default_state="Tamil Nadu",
        )

        self.assertEqual(len(hospitals), 2)
        self.assertEqual(hospitals[0].pincode, "600006")
        self.assertEqual(hospitals[1].name, "Fortis Medical Centre")

    def test_hdfc_life_parser_extracts_policybazaar_name_address_pairs(self):
        text = """
        HDFC ERGO Network Hospitals List in Hyderabad
        645 HDFC ERGO Cashless Network in Hyderabad
        More hospitals
        Aashritha Hospital
        3 4 100/2 M V Ramarao Complex Mallapur Main Road Opp Sai Towers (City - Ranga Reddy)
        Centre For Sight
        Plot No 14 Sector 25 Seawood Nerul (City - Navi Mumbai)
        Aira Diagnostics - Hyderabad (Dr. Usha Sree)
        Location - Hyderabad - Andhra Pradesh - 500044
        Policybazaar Claim process
        Step 1
        """

        hospitals = parse_hdfc_life_network_text(
            text,
            "https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-maharashtra-hyderabad/",
            default_city="Hyderabad",
            default_state="Telangana",
        )

        self.assertEqual(len(hospitals), 3)
        self.assertEqual(hospitals[0].name, "Aashritha Hospital")
        self.assertEqual(hospitals[1].name, "Centre For Sight")
        self.assertEqual(hospitals[2].pincode, "500044")


class HospitalsByInsuranceViewTests(APITestCase):
    def test_missing_data_queues_background_sync_without_scraping_inline(self):
        with (
            patch("insurance_network.views.SyncService.trigger_background_sync", return_value=True) as mock_queue,
            patch("insurance_network.views.SyncService.sync") as mock_sync,
        ):
            response = self.client.get("/api/v1/insurance/star-health/hospitals/")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.data["syncing"])
        self.assertEqual(response.data["status"], "sync_queued")
        mock_queue.assert_called_once()
        mock_sync.assert_not_called()

    def test_existing_data_returns_from_db_without_queuing_when_fresh(self):
        insurance = InsuranceCompany.objects.create(
            name="Star Health and Allied Insurance",
            slug="star-health",
            is_active=True,
            last_scraped_at=timezone.now(),
        )
        hospital = Hospital.objects.create(
            name="Apollo Hospitals",
            normalized_name="apollo hospitals",
            address="Greams Road",
            normalized_address="greams road",
            city="Chennai",
            state="Tamil Nadu",
            pincode="600006",
            phone="044-28290200",
        )
        InsuranceHospitalNetwork.objects.create(
            insurance=insurance,
            hospital=hospital,
            plan_types=["Network Hospital"],
            source_url="https://www.starhealth.in/lookup/hospital/",
        )

        with patch("insurance_network.views.SyncService.trigger_background_sync") as mock_queue:
            response = self.client.get("/api/v1/insurance/star-health/hospitals/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "served_from_db")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["hospitals"][0]["name"], "Apollo Hospitals")
        mock_queue.assert_not_called()

    def test_stale_data_returns_db_and_queues_refresh(self):
        insurance = InsuranceCompany.objects.create(
            name="Star Health and Allied Insurance",
            slug="star-health",
            is_active=True,
            last_scraped_at=timezone.now() - timedelta(hours=48),
        )
        hospital = Hospital.objects.create(
            name="Apollo Hospitals",
            normalized_name="apollo hospitals",
            address="Greams Road",
            normalized_address="greams road",
            city="Chennai",
            state="Tamil Nadu",
            pincode="600006",
            phone="044-28290200",
        )
        InsuranceHospitalNetwork.objects.create(
            insurance=insurance,
            hospital=hospital,
            plan_types=["Network Hospital"],
            source_url="https://www.starhealth.in/lookup/hospital/",
        )

        with patch("insurance_network.views.SyncService.trigger_background_sync", return_value=True) as mock_queue:
            response = self.client.get("/api/v1/insurance/star-health/hospitals/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "served_from_db")
        self.assertTrue(response.data["refresh_queued"])
        mock_queue.assert_called_once()

    def test_hdfc_life_missing_data_queues_background_sync(self):
        with (
            patch("insurance_network.views.SyncService.trigger_background_sync", return_value=True) as mock_queue,
            patch("insurance_network.views.SyncService.sync") as mock_sync,
        ):
            response = self.client.get("/api/v1/insurance/hdfc-life/hospitals/")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "sync_queued")
        self.assertEqual(response.data["insurance"]["slug"], "hdfc-life")
        mock_queue.assert_called_once()
        mock_sync.assert_not_called()

    def test_unknown_provider_returns_404_without_scraping(self):
        with patch("insurance_network.views.SyncService.trigger_background_sync") as mock_queue:
            response = self.client.get("/api/v1/insurance/unknown-cover/hospitals/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["status"], "provider_not_supported")
        mock_queue.assert_not_called()


class SyncServiceTests(TestCase):
    def test_sync_saves_scraped_hospitals(self):
        insurance, _ = InsuranceService.get_or_create_supported("star-health")

        class DummyScraper:
            def run(self):
                return [
                    ScrapedHospital(
                        name="Apollo Hospitals",
                        address="Greams Road, Chennai 600006",
                        city="Chennai",
                        state="Tamil Nadu",
                        pincode="600006",
                        phone="044-28290200",
                        plan_types=["Network Hospital"],
                        source_url="https://www.starhealth.in/lookup/hospital/",
                    )
                ]

        with patch("insurance_network.scrapers.registry.get_scraper", return_value=DummyScraper()):
            log = SyncService.sync(insurance.slug, geocode=False)

        self.assertEqual(log.status, "success")
        self.assertEqual(log.hospitals_found, 1)
        self.assertEqual(Hospital.objects.count(), 1)
        self.assertTrue(InsuranceHospitalNetwork.objects.filter(insurance=insurance).exists())

    def test_sync_keeps_same_name_different_addresses_when_pincode_missing(self):
        insurance, _ = InsuranceService.get_or_create_supported("hdfc-life")
        scraped = [
            ScrapedHospital(
                name="Apollo Hospitals",
                address="First Main Road, Chennai",
                city="Chennai",
                state="Tamil Nadu",
                pincode="",
                phone="",
                plan_types=["Network Hospital"],
                source_url="https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-tamil_nadu-chennai/",
            ),
            ScrapedHospital(
                name="Apollo Hospitals",
                address="Second Main Road, Chennai",
                city="Chennai",
                state="Tamil Nadu",
                pincode="",
                phone="",
                plan_types=["Network Hospital"],
                source_url="https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-tamil_nadu-chennai/",
            ),
        ]

        saved = SyncService._save_scraped_hospitals(insurance, scraped, geocode=False)

        self.assertEqual(saved, 2)
        self.assertEqual(Hospital.objects.count(), 2)
