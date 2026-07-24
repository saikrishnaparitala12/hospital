# Insurance Network Hospital Feature

## Goal

This module powers insurance-based hospital discovery similar to Practo or MediBuddy:

- Patients search supported insurance companies.
- Patients select an insurance company and get hospitals that accept it.
- Patients can find nearby hospitals using latitude and longitude.
- Scraping never runs inside API requests.
- Scraped data is stored in PostgreSQL and served from the database.
- Missing or stale data queues a background sync through Celery.

Implemented providers:

- `star-health` — Star Health and Allied Insurance
- `hdfc-life` — HDFC Life/HDFC ERGO health-claim network links sourced from Policybazaar

## Folder Structure

```text
insurance_network/
  admin.py
  apps.py
  models.py
  serializers.py
  services.py
  tasks.py
  urls.py
  views.py
  utils.py
  tests.py
  fixtures/
    initial_insurance.json
  management/
    commands/
      sync_insurance_networks.py
  scrapers/
    base.py
    hdfc_life.py
    registry.py
    star_health.py
```

## Architecture

```text
API request
  |
  |-- search insurance -> registry + DB metadata
  |
  |-- hospitals by insurance
        |
        |-- DB has active mappings -> return immediately
        |
        |-- DB missing/stale -> queue Celery sync
        |
        |-- API still returns immediately; no scraping in request

Celery worker / management command
  |
  |-- load provider scraper from registry
  |-- scrape with Playwright
  |-- normalize hospital name/address
  |-- geocode once if needed
  |-- upsert Hospital and InsuranceHospitalNetwork rows
  |-- write ScrapeLog
```

## Design Rules

- API views do not scrape.
- API views only query PostgreSQL and queue background work.
- Each provider gets its own scraper class implementing `BaseInsuranceScraper`.
- `ScrapedHospital` is the scraper output contract.
- Sync failures never delete old hospital data.
- Hospital deduplication uses `normalized_name + normalized_address + pincode`.
- Geocoding is done once per hospital and persisted.
- Stale data is refreshed in the background while old DB data is returned immediately.

## Database Schema

### InsuranceCompany

Stores provider metadata.

| Field | Purpose |
|---|---|
| `name` | Display name |
| `slug` | API/provider key |
| `website` | Provider website |
| `logo_url` | Optional logo |
| `is_active` | Feature availability |
| `last_scraped_at` | Last successful sync time |

### Hospital

Stores normalized hospital records shared across providers.

| Field | Purpose |
|---|---|
| `name` | Original hospital name |
| `normalized_name` | Normalized name for matching |
| `address` | Original address |
| `normalized_address` | Normalized address |
| `city`, `state`, `pincode` | Location fields |
| `phone` | Contact number |
| `latitude`, `longitude` | Stored geocode |
| `geocoded_at` | Geocode timestamp |

### InsuranceHospitalNetwork

Many-to-many mapping between insurance and hospitals.

| Field | Purpose |
|---|---|
| `insurance` | Insurance FK |
| `hospital` | Hospital FK |
| `plan_types` | JSON list, e.g. `["Network Hospital"]` |
| `is_active` | Mapping status |
| `source_url` | Scrape source |

### ScrapeLog

Operational monitoring table for every sync attempt.

| Field | Purpose |
|---|---|
| `status` | `running`, `success`, or `failed` |
| `hospitals_found` | Saved row count |
| `error_message` | Failure details |
| `started_at`, `finished_at` | Timing |

## API Design

Base path:

```text
/api/v1/
```

All insurance network endpoints are public (`AllowAny`).

### Search Insurance

```http
GET /api/v1/insurance/?q=star
```

Response:

```json
{
  "success": true,
  "status": "ok",
  "query": "star",
  "count": 1,
  "results": [
    {
      "id": null,
      "name": "Star Health and Allied Insurance",
      "slug": "star-health",
      "logo_url": "https://www.starhealth.in/images/logo.png",
      "website": "https://www.starhealth.in",
      "last_scraped_at": null,
      "is_syncing": false,
      "hospital_count": 0
    }
  ]
}
```

### Hospitals By Insurance

```http
GET /api/v1/insurance/star-health/hospitals/
```

If data exists:

```json
{
  "success": true,
  "syncing": false,
  "status": "served_from_db",
  "message": "Hospital network data served from the database.",
  "refresh_queued": false,
  "count": 1,
  "hospitals": []
}
```

If data is missing and the sync task was queued:

```json
{
  "success": true,
  "syncing": true,
  "status": "sync_queued",
  "message": "Hospital network data is being synchronized. Please try again in a few minutes.",
  "count": 0,
  "hospitals": []
}
```

If provider is not registered:

```json
{
  "success": false,
  "status": "provider_not_supported",
  "message": "This insurance provider is not available for network hospital lookup yet.",
  "query": "hdfc-lif",
    "suggestions": ["Star Health and Allied Insurance", "HDFC Life Insurance"],
  "hospitals": []
}
```

### Nearby Hospitals

```http
GET /api/v1/hospitals/nearby/?lat=13.0827&lon=80.2707&radius=10
```

Response:

```json
{
  "success": true,
  "status": "ok",
  "count": 1,
  "hospitals": [
    {
      "id": 1,
      "name": "Apollo Hospitals",
      "address": "Greams Road",
      "city": "Chennai",
      "state": "Tamil Nadu",
      "phone": "044-28290200",
      "latitude": "13.060416",
      "longitude": "80.257616",
      "distance_km": 2.41
    }
  ]
}
```

### Nearby Hospitals By Insurance

```http
GET /api/v1/insurance/star-health/hospitals/nearby/?lat=13.0827&lon=80.2707&radius=10
```

If data is missing, this endpoint queues sync and returns the same `sync_queued` response shape.

HDFC Life example:

```http
GET /api/v1/insurance/hdfc-life/hospitals/
```

If no HDFC Life hospital data is stored yet, the endpoint returns `sync_queued` and the Celery worker runs the provider scraper in the background.
The `hdfc-ergo` alias also resolves to this provider because Policybazaar publishes the hospital network under HDFC ERGO pages.

## Synchronization Flow

### Automatic API Trigger

When a patient requests hospitals for a supported provider:

- If DB has active hospital mappings, return DB data immediately.
- If DB has no data, queue `sync_insurance_network`.
- If DB data exists but `last_scraped_at` is older than `INSURANCE_NETWORK_STALE_AFTER_HOURS`, return DB data and queue refresh.

### Celery Task

```python
sync_insurance_network.delay("star-health")
```

The task retries failed syncs up to 3 times with a 5 minute delay.

### Celery Beat

`hospital/settings.py` schedules a daily refresh:

```python
CELERY_BEAT_SCHEDULE = {
    "refresh-insurance-networks-daily": {
        "task": "insurance_network.tasks.refresh_all_insurance_networks",
        "schedule": crontab(hour=2, minute=0),
    },
}
```

### Manual Command

```bash
python manage.py sync_insurance_networks --slug star-health --sync
python manage.py sync_insurance_networks --slug hdfc-life --sync --no-geocode
python manage.py sync_insurance_networks --slug star-health
python manage.py sync_insurance_networks
```

## Scraper Contract

Every scraper extends:

```python
class BaseInsuranceScraper(ABC):
    insurance_slug: str

    @abstractmethod
    def scrape(self) -> list[ScrapedHospital]:
        ...
```

Scrapers return `ScrapedHospital` records:

```python
ScrapedHospital(
    name="Apollo Hospitals",
    address="Greams Road, Chennai",
    city="Chennai",
    state="Tamil Nadu",
    pincode="600006",
    phone="044-28290200",
    plan_types=["Network Hospital"],
    source_url="https://www.starhealth.in/lookup/hospital/",
)
```

## Existing Providers

### Star Health

Registry slug:

```text
star-health
```

Source:

```text
https://www.starhealth.in/lookup/hospital/
```

### HDFC Life

Registry slug:

```text
hdfc-life
```

Source references:

```text
https://www.hdfclife.com/claims
https://www.policybazaar.com/network-hospitals/hdfc-ergo-network-hospitals/
https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-delhi-delhi/
https://www.policybazaar.com/network-hospitals/hdfc-ergo-hospitals-maharashtra-mumbai/
```

HDFC Life's claims page is kept as the provider reference. Hospital network data is scraped from Policybazaar's public HDFC ERGO network hospital pages during background sync, then saved to PostgreSQL with normalized hospital names, addresses, and one-time geocoding.

## Adding Another Provider

1. Create `insurance_network/scrapers/<provider>.py`.
2. Implement `BaseInsuranceScraper`.
3. Register it in `insurance_network/scrapers/registry.py`.

Example:

```python
SCRAPER_REGISTRY = {
    "care-health": ScraperEntry(
        slug="care-health",
        name="Care Health Insurance",
        website="https://www.careinsurance.com",
        logo_url="",
        scraper_class=CareHealthScraper,
        aliases=("Care", "Care Health"),
    ),
}
```

No API or service changes are needed.

## Caching Strategy

- PostgreSQL is the source of truth for API responses.
- `last_scraped_at` decides whether data is stale.
- Fresh DB data is returned immediately.
- Stale DB data is returned immediately and refreshed asynchronously.
- Failed syncs do not remove old valid records.

## Geocoding

`insurance_network/utils.py` uses OpenStreetMap Nominatim.

Rules:

- Geocode only during sync, never in API requests.
- Geocode only if `latitude` is missing.
- Save `latitude`, `longitude`, and `geocoded_at`.
- Nearby search uses stored coordinates and Haversine distance.

## Logging And Monitoring

- Scrapers log page-level parse counts and failures.
- `SyncService` writes `ScrapeLog` rows for every run.
- Django Admin exposes `ScrapeLog`.
- Celery retries transient sync failures.
- Production should monitor failed `ScrapeLog` rows and Celery queue health.

## Testing Strategy

Covered by `insurance_network/tests.py`:

- Search returns registered providers.
- Unknown providers return 404 without scraping.
- Missing DB data queues background sync and does not scrape inline.
- Fresh DB data returns immediately.
- Stale DB data returns immediately and queues refresh.
- Parser tests validate Star Health table parsing.
- Sync tests validate normalization/upsert behavior.

## Deployment Notes

- Run PostgreSQL migrations.
- Run Redis or another Celery broker.
- Start Django app, Celery worker, and Celery Beat.
- Install Playwright browsers:

```bash
python -m playwright install chromium
```

- Use a worker queue with enough memory for browser automation.
- Set `INSURANCE_NETWORK_STALE_AFTER_HOURS` for refresh policy.
- Keep scraper timeouts conservative.

## Security Best Practices

- Do not accept arbitrary scraper URLs from API users.
- Only registered providers can be scraped.
- Run Playwright in headless mode inside worker containers.
- Apply request throttling/rate limits at the API layer if exposed publicly.
- Keep browser and Playwright versions patched.
- Store only public hospital network data.
- Avoid logging sensitive patient coordinates beyond what is needed for debugging.
