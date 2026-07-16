import re
import logging
import time
import requests

logger = logging.getLogger(__name__)

_NOISE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s,\-]")


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = _PUNCT.sub("", text)
    text = _NOISE.sub(" ", text)
    return text


def geocode_address(address: str, city: str, state: str, pincode: str = "") -> tuple[float, float] | tuple[None, None]:
    """
    Geocode using Nominatim (OSM). Free, no API key required.
    Returns (latitude, longitude) or (None, None) on failure.
    Rate-limited to 1 req/sec per OSM policy.
    """
    query = ", ".join(filter(None, [address, city, state, pincode, "India"]))
    try:
        time.sleep(1)  # OSM rate limit
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "HospitalManagementSystem/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.warning("Geocoding failed for '%s': %s", query, exc)
    return None, None
