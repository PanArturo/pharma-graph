import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov/drug/label.json"

CONDITION_MAP = {
    "atrial fibrillation": ("Atrial Fibrillation", "I48"),
    "type 2 diabetes":     ("Type 2 Diabetes",     "E11"),
    "heart failure":       ("Heart Failure",        "I50"),
    "hypertension":        ("Hypertension",         "I10"),
    "deep vein thrombosis":("DVT",                  "I82"),
    "stroke":              ("Stroke",               "I63"),
    "cancer":              ("Oncology",             "C80"),
    "multiple sclerosis":  ("Multiple Sclerosis",   "G35"),
}


def _parse_conditions(indications_text: str) -> list[dict]:
    """
    Scan the indications_and_usage text for known condition keywords.
    A single drug can match multiple conditions.
    Returns a list of { name, icd10 } dicts.
    """
    text = indications_text.lower()
    matched = []
    for keyword, (name, icd10) in CONDITION_MAP.items():
        if keyword in text:
            matched.append({"name": name, "icd10": icd10})
    return matched


def _slugify(name: str) -> str:
    return name.lower().strip().replace(" ", "_").replace("/", "_")


def _parse_drug(result: dict) -> dict | None:
    openfda = result.get("openfda", {})

    brand_names = openfda.get("brand_name", [])
    generic_names = openfda.get("generic_name", [])
    manufacturers = openfda.get("manufacturer_name", [])
    indications_list = result.get("indications_and_usage", [])

    brand = brand_names[0].strip() if brand_names else ""
    generic = generic_names[0].strip() if generic_names else ""
    manufacturer = manufacturers[0].strip() if manufacturers else ""
    indications = indications_list[0] if indications_list else ""

    if not brand and not generic:
        return None

    label = brand or generic
    conditions = _parse_conditions(indications)

    return {
        "id": f"drug_{_slugify(label)}",
        "brand": brand,
        "generic": generic,
        "manufacturer": manufacturer,
        "conditions": conditions,
    }


async def _fetch_drugs_for_company(client: httpx.AsyncClient, company: str) -> list[dict]:
    params = {
        "search": f'openfda.manufacturer_name:"{company}"',
        "limit": 10,
    }
    try:
        resp = await client.get(BASE_URL, params=params, timeout=15)

        if resp.status_code == 404:
            # 404 from OpenFDA means no results — not an error
            logger.info("OpenFDA: no drugs found for company=%s", company)
            return []

        if resp.status_code != 200:
            logger.error("OpenFDA: HTTP %s for company=%s", resp.status_code, company)
            return []

        data = resp.json()
        results = data.get("results", [])

        drugs = []
        for result in results:
            parsed = _parse_drug(result)
            if parsed:
                drugs.append(parsed)

        logger.info("OpenFDA: %d drugs for company=%s", len(drugs), company)
        return drugs

    except Exception as exc:
        logger.error("OpenFDA: error for company=%s: %s", company, exc)
        return []


async def fetch_drugs(company_names: list[str]) -> list[dict]:
    """
    Fetch drugs and parsed conditions for a list of pharma company names.
    Deduplicates by drug ID. Returns [] on total failure.
    """
    drugs: dict[str, dict] = {}  # keyed by drug ID to deduplicate

    async with httpx.AsyncClient() as client:
        for i, company in enumerate(company_names):
            if i > 0:
                await asyncio.sleep(0.3)  # stay under 40 req/min unauthenticated limit

            results = await _fetch_drugs_for_company(client, company)
            for drug in results:
                if drug["id"] not in drugs:
                    drugs[drug["id"]] = drug

    all_drugs = list(drugs.values())
    logger.info("OpenFDA: %d unique drugs total across %d companies", len(all_drugs), len(company_names))
    return all_drugs
