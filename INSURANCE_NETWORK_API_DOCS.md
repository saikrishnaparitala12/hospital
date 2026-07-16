# Insurance Network Hospital API — Documentation

## Overview

The Insurance Network Hospital feature allows patients to:
- Search for insurance companies
- Browse all hospitals that accept a specific insurance
- Find nearby hospitals based on their GPS coordinates
- Find nearby hospitals filtered by insurance provider

Hospital data is scraped from insurance provider websites using **Playwright** and stored in PostgreSQL. API responses are always served from the database — scraping never happens during a request.

---

## Architecture Summary

```
Patient Request
      │
      ▼
  API View  ──── reads from ────▶  PostgreSQL (Hospital / InsuranceHospitalNetwork)
      │
      └── data stale? ──── fires ────▶  Celery Task  ──▶  Playwright Scraper
                                              │
                                              ▼
                                     Normalize + Geocode
                                              │
                                              ▼
                                         Save to DB
```

### Key Design Rules
- **No scraping during API requests** — views only read from DB
- **Stale check** — if `last_scraped_at` is older than 24 hours, a background sync is triggered automatically
- **Geocoding once** — latitude/longitude is fetched from OSM Nominatim once and stored permanently
- **Deduplication** — hospitals are matched by `normalized_name + pincode` to avoid duplicates across scrapers

---

## Base URL

All endpoints are prefixed with:
```
/api/v1/
```

---

## Authentication

All insurance network endpoints are **public** (`AllowAny`) — no JWT token required.

---

## Standard Response Format

### Success
```json
{
  "id": 1,
  "name": "Star Health and Allied Insurance",
  ...
}
```
> Insurance network endpoints return DRF's default response format (plain JSON array or object), not the `{ message, data }` wrapper used by other APIs.

---

## Endpoints

---

### GET `/api/v1/insurance/`
Search for insurance companies.

**Auth**: None

**Query Params**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | No | Search by name (case-insensitive contains). Omit to list all. |

**Examples**
```
GET /api/v1/insurance/
GET /api/v1/insurance/?q=star
GET /api/v1/insurance/?q=hdfc
```

**Response** `200`
```json
[
  {
    "id": 1,
    "name": "Star Health and Allied Insurance",
    "slug": "star-health",
    "logo_url": "https://www.starhealth.in/images/logo.png",
    "website": "https://www.starhealth.in",
    "last_scraped_at": "2025-01-15T02:00:00Z"
  }
]
```

**Field Reference**
| Field | Description |
|-------|-------------|
| `slug` | URL-safe identifier used in other endpoints |
| `last_scraped_at` | When hospital data was last synced. `null` means never scraped yet. |

---

### GET `/api/v1/insurance/<slug>/hospitals/`
Get all hospitals that accept a specific insurance.

**Auth**: None

**Path Params**
| Param | Description |
|-------|-------------|
| `slug` | Insurance company slug (e.g. `star-health`) |

**Example**
```
GET /api/v1/insurance/star-health/hospitals/
```

**Response** `200`
```json
[
  {
    "id": 101,
    "name": "Apollo Hospitals",
    "address": "21 Greams Lane, Off Greams Road",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "pincode": "600006",
    "phone": "044-28290200",
    "latitude": "13.060416",
    "longitude": "80.257616"
  },
  {
    "id": 102,
    "name": "Fortis Malar Hospital",
    "address": "52 1st Main Road, Gandhi Nagar",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "pincode": "600020",
    "phone": "044-42892222",
    "latitude": "13.010357",
    "longitude": "80.220978"
  }
]
```

**Notes**
- Returns an empty array `[]` if no hospitals have been synced yet
- Automatically triggers a background sync if data is older than 24 hours (non-blocking)

**Error** `404`
```json
{ "detail": "Insurance not found." }
```

---

### GET `/api/v1/hospitals/nearby/`
Find hospitals near a given GPS location.

**Auth**: None

**Query Params**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Patient's latitude |
| `lon` | float | Yes | — | Patient's longitude |
| `radius` | float | No | `10` | Search radius in kilometres |

**Example**
```
GET /api/v1/hospitals/nearby/?lat=13.0827&lon=80.2707&radius=5
```

**Response** `200`
```json
[
  {
    "id": 101,
    "name": "Apollo Hospitals",
    "address": "21 Greams Lane, Off Greams Road",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "phone": "044-28290200",
    "latitude": "13.060416",
    "longitude": "80.257616",
    "distance_km": 2.41
  },
  {
    "id": 105,
    "name": "MIOT International",
    "address": "4/112 Mount Poonamallee Road",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "phone": "044-22490000",
    "latitude": "13.041200",
    "longitude": "80.175300",
    "distance_km": 4.87
  }
]
```

**Notes**
- Results are sorted by `distance_km` ascending (nearest first)
- Only hospitals with geocoded coordinates (`latitude` / `longitude` not null) are returned
- Returns empty array `[]` if no hospitals are within the radius

**Error** `400`
```json
{ "detail": "lat and lon are required numeric parameters." }
```

---

### GET `/api/v1/insurance/<slug>/hospitals/nearby/`
Find hospitals near a location that also accept a specific insurance.

**Auth**: None

**Path Params**
| Param | Description |
|-------|-------------|
| `slug` | Insurance company slug (e.g. `star-health`) |

**Query Params**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Patient's latitude |
| `lon` | float | Yes | — | Patient's longitude |
| `radius` | float | No | `10` | Search radius in kilometres |

**Example**
```
GET /api/v1/insurance/star-health/hospitals/nearby/?lat=13.0827&lon=80.2707&radius=10
```

**Response** `200`
```json
[
  {
    "id": 101,
    "name": "Apollo Hospitals",
    "address": "21 Greams Lane, Off Greams Road",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "phone": "044-28290200",
    "latitude": "13.060416",
    "longitude": "80.257616",
    "distance_km": 2.41
  }
]
```

**Notes**
- Combines insurance filter + proximity filter
- Results sorted by `distance_km` ascending
- Automatically triggers background sync if data is stale

**Errors**
```json
{ "detail": "Insurance not found." }          // 404 — invalid slug
{ "detail": "lat and lon are required numeric parameters." }  // 400 — missing coords
```

---

## API Summary Table

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/insurance/` | None | Search insurance companies |
| GET | `/api/v1/insurance/<slug>/hospitals/` | None | All hospitals by insurance |
| GET | `/api/v1/hospitals/nearby/` | None | Nearby hospitals (any insurance) |
| GET | `/api/v1/insurance/<slug>/hospitals/nearby/` | None | Nearby hospitals by insurance |

---

## Data Models

### InsuranceCompany
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `name` | string | Full insurance company name |
| `slug` | string | URL-safe unique identifier |
| `website` | string | Insurance provider website |
| `logo_url` | string | Logo image URL |
| `is_active` | bool | Whether this provider is enabled |
| `last_scraped_at` | datetime | Last successful scrape timestamp |

### Hospital
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `name` | string | Hospital name (original) |
| `normalized_name` | string | Lowercased, cleaned name (used for deduplication) |
| `address` | string | Full address |
| `city` | string | City |
| `state` | string | State |
| `pincode` | string | PIN code |
| `phone` | string | Contact number |
| `latitude` | decimal | GPS latitude (null until geocoded) |
| `longitude` | decimal | GPS longitude (null until geocoded) |
| `geocoded_at` | datetime | When geocoding was performed |

### InsuranceHospitalNetwork
| Field | Type | Description |
|-------|------|-------------|
| `insurance` | FK | InsuranceCompany |
| `hospital` | FK | Hospital |
| `plan_types` | JSON array | e.g. `["cashless", "reimbursement"]` |
| `is_active` | bool | Whether this mapping is active |
| `source_url` | string | URL scraped from |

---

## Background Sync

### Automatic (Stale Check)
When a patient hits `/insurance/<slug>/hospitals/` or the nearby-by-insurance endpoint, the system checks if `last_scraped_at` is older than **24 hours**. If stale, a Celery task is queued automatically — the API response is not delayed.

### Celery Beat (Daily Cron)
A scheduled task runs every day at **2:00 AM IST** to refresh all active insurance providers:
```
Task: insurance_network.tasks.refresh_all_insurance_networks
Schedule: crontab(hour=2, minute=0)
```

### Manual Trigger (Management Command)
```bash
# Sync one provider synchronously (no Celery needed — good for testing)
python manage.py sync_insurance_networks --slug star-health --sync

# Queue one provider via Celery
python manage.py sync_insurance_networks --slug star-health

# Queue all active providers via Celery
python manage.py sync_insurance_networks
```

### ScrapeLog
Every sync attempt is recorded in the `ScrapeLog` table:

| Field | Description |
|-------|-------------|
| `status` | `pending` → `running` → `success` / `failed` |
| `hospitals_found` | Number of hospitals saved in this run |
| `error_message` | Full error if status is `failed` |
| `started_at` | When the scrape started |
| `finished_at` | When the scrape finished |

Viewable in Django Admin at `/admin/insurance_network/scrapelog/`

---

## Adding a New Insurance Provider

Only 2 steps required:

**Step 1** — Create `insurance_network/scrapers/<provider>.py`:
```python
from .base import BaseInsuranceScraper, ScrapedHospital

class HdfcErgoScraper(BaseInsuranceScraper):
    insurance_slug = "hdfc-ergo"

    def scrape(self):
        from playwright.sync_api import sync_playwright
        hospitals = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.hdfcergo.com/network-hospitals")
            # ... scraping logic ...
            browser.close()
        return hospitals
```

**Step 2** — Register in `insurance_network/scrapers/registry.py`:
```python
from .hdfc_ergo import HdfcErgoScraper

SCRAPER_REGISTRY = {
    "star-health": StarHealthScraper,
    "hdfc-ergo": HdfcErgoScraper,   # add this line
}
```

**Step 3** — Seed the DB record (via Django Admin or fixture):
```json
{
  "model": "insurance_network.insurancecompany",
  "fields": {
    "name": "HDFC ERGO General Insurance",
    "slug": "hdfc-ergo",
    "website": "https://www.hdfcergo.com",
    "is_active": true
  }
}
```

All sync, geocoding, API, and scheduling logic is inherited automatically — no other changes needed.

---

## Geocoding

Hospital addresses are geocoded using **OpenStreetMap Nominatim** (free, no API key required).

- Geocoding happens once per hospital during the first sync
- Result stored in `latitude` / `longitude` fields permanently
- Rate limited to 1 request/second per OSM policy
- If geocoding fails, the hospital is still saved — it just won't appear in nearby searches until geocoded

To switch to Google Maps Geocoding API, update `insurance_network/utils.py` → `geocode_address()`.

---

## Error Reference

| Status | Body | Cause |
|--------|------|-------|
| `404` | `{ "detail": "Insurance not found." }` | Invalid or inactive insurance slug |
| `400` | `{ "detail": "lat and lon are required numeric parameters." }` | Missing or non-numeric coordinates |
