import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://npiregistry.cms.hhs.gov/api/"

SPECIALTIES = [
    "Cardiology",
    "Endocrinology",
    "Internal Medicine",
    "Oncology",
    "Neurology",
]


def _parse_physician(result: dict) -> dict | None:
    basic = result.get("basic", {})
    addresses = result.get("addresses", [])
    taxonomies = result.get("taxonomies", [])

    npi = result.get("number", "").strip()
    first = basic.get("first_name", "").strip()
    last = basic.get("last_name", "").strip()

    if not npi or not last:
        return None

    # Practice address — prefer location type over mailing
    address = next(
        (a for a in addresses if a.get("address_purpose") == "LOCATION"),
        addresses[0] if addresses else {},
    )

    # Primary taxonomy (the one marked as primary, else first)
    taxonomy = next(
        (t for t in taxonomies if t.get("primary")),
        taxonomies[0] if taxonomies else {},
    )

    return {
        "npi": npi,
        "first": first,
        "last": last,
        "full_name": f"Dr. {first} {last}".strip(),
        "specialty": taxonomy.get("desc", "").strip(),
        "city": address.get("city", "").strip(),
        "state": address.get("state", "").strip(),
    }


async def _fetch_specialty(client: httpx.AsyncClient, state: str, specialty: str) -> list[dict]:
    params = {
        "version": "2.1",
        "state": state,
        "taxonomy_description": specialty,
        "limit": 100,
    }
    try:
        resp = await client.get(BASE_URL, params=params, timeout=15)
        if resp.status_code != 200:
            logger.error("NPI Registry: HTTP %s for state=%s specialty=%s", resp.status_code, state, specialty)
            return []

        data = resp.json()
        results = data.get("results", [])

        physicians = []
        for result in results:
            parsed = _parse_physician(result)
            if parsed:
                physicians.append(parsed)

        logger.info("NPI Registry: %d physicians for state=%s specialty=%s", len(physicians), state, specialty)
        return physicians

    except Exception as exc:
        logger.error("NPI Registry: error for state=%s specialty=%s: %s", state, specialty, exc)
        return []


async def fetch_npi_physicians(state: str) -> list[dict]:
    """
    Fetch licensed physicians in the given state across all specialties.
    Respects the ~3 req/sec rate limit with 0.4s delay between calls.
    Returns a deduplicated list of physician dicts. Returns [] on total failure.
    """
    physicians: dict[str, dict] = {}  # keyed by NPI to deduplicate

    async with httpx.AsyncClient() as client:
        for i, specialty in enumerate(SPECIALTIES):
            if i > 0:
                await asyncio.sleep(0.4)

            results = await _fetch_specialty(client, state, specialty)
            for p in results:
                # First occurrence wins — preserves specialty from the query that found them
                if p["npi"] not in physicians:
                    physicians[p["npi"]] = p

    all_physicians = list(physicians.values())
    logger.info("NPI Registry: %d unique physicians total for state=%s", len(all_physicians), state)
    return all_physicians
