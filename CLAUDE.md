# Impiricus Clinical Intelligence Graph

Full-stack web app visualizing the pharma-physician influence network for any US state and year, using only public government APIs.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, httpx (async), NetworkX |
| Frontend | Single `index.html`, `3d-force-graph` CDN, Tailwind CSS CDN |
| Data sources | NPI Registry, OpenFDA, CMS Open Payments |
| Auth | None — all APIs are public |
| Run | `uvicorn main:app --reload --port 8000` then open `frontend/index.html` |

---

## Project Structure

```
impiricus-pharma-graph/
├── main.py                   # FastAPI entrypoint, cache, fetcher orchestration
├── requirements.txt
├── .env                      # Empty — no keys needed yet
├── .gitignore
├── fetchers/
│   ├── __init__.py
│   ├── npi.py                # NPI Registry — physicians by state + specialty
│   ├── openfda.py            # OpenFDA — drugs + condition parsing
│   └── open_payments.py      # CMS Open Payments — pharma→physician payments
├── graph/
│   ├── __init__.py
│   ├── builder.py            # NetworkX DiGraph assembly + serialization
│   └── models.py             # Pydantic models (Node, Edge, GraphMeta, GraphResponse)
└── frontend/
    └── index.html            # Full UI, no build step
```

---

## API Endpoint

### `GET /api/graph/{state}/{year}`
- `state`: 2-letter US state code (e.g. `GA`, `TX`)
- `year`: integer, valid range 2020–2023
- Returns: `GraphResponse` (nodes, edges, meta)
- Never returns 500 — always returns a valid (possibly partial) `GraphResponse`

---

## Data Sources

### NPI Registry
- Base URL: `https://npiregistry.cms.hhs.gov/api/`
- Params: `version=2.1`, `state`, `taxonomy_description`, `limit=20`
- Rate limit: ~3 req/sec — use `asyncio.sleep(0.4)` between specialty calls
- Specialties: Cardiology, Endocrinology, Internal Medicine, Oncology, Neurology

### OpenFDA
- Base URL: `https://api.fda.gov/drug/label.json`
- Search by manufacturer name, parse `indications_and_usage[0]` for conditions

### CMS Open Payments
- Base URL: `https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset_id}/0`
- POST with JSON body — filter by `recipient_state`, sort by amount desc, cap 500 rows
- Dataset IDs must be verified at `/api/1/datastore/list` before use — PRD IDs for 2021/2022 are placeholders

---

## Node Types

| Type | ID Format | Key Props |
|---|---|---|
| `pharma` | slugified name e.g. `pfizer` | total_paid, num_physicians |
| `drug` | `drug_{slugified_brand}` | generic_name, conditions |
| `condition` | `cond_{icd10}` e.g. `cond_I48` | icd10_code |
| `physician` | `npi_{npi_number}` | npi, specialty, city, state, total_received |

## Edge Types

| Type | From → To | Weight |
|---|---|---|
| `MANUFACTURES` | pharma → drug | 1.0 |
| `INDICATED_FOR` | drug → condition | 1.0 |
| `SPECIALIZES_IN` | physician → condition | 1.0 |
| `PAID` | pharma → physician | payment amount USD |
| `RECEIVED_FOR` | physician → drug | payment amount USD |
| `PEER_OF` | physician → physician | 1.0 — same specialty + same pharma payer |

Cap: 200 nodes, 400 edges, 100 PEER_OF edges — truncate by weight descending.

---

## Key Constants

```python
SPECIALTIES = ["Cardiology", "Endocrinology", "Internal Medicine", "Oncology", "Neurology"]

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

TAXONOMY_CONDITION_MAP = {
    "Cardiology":        ["I48", "I50"],
    "Endocrinology":     ["E11"],
    "Internal Medicine": ["I10", "E11"],
    "Oncology":          ["C80"],
    "Neurology":         ["G35", "I63"],
}
```

---

## Fetcher Orchestration (main.py)

```python
payments, physicians = await asyncio.gather(fetch_open_payments(state, year), fetch_npi_physicians(state))
company_names = list({p["company"] for p in payments})
drugs = await fetch_drugs(company_names)
graph = build_graph(payments, physicians, drugs)
```

In-memory cache: dict keyed on `(state, year)` with 1-hour TTL.

---

## Error Handling Rules

- Every fetcher returns `[]` on any exception — never propagates
- Log all upstream errors with API name and HTTP status
- Endpoint always returns valid `GraphResponse`, even if all fetchers fail

---

## Performance Targets

- Cold response: < 10s
- Cached response: < 200ms
- Frontend render: < 2s after data received

---

## Build Order (PRD spec)

1. ✅ `graph/models.py` — Pydantic models
2. `fetchers/open_payments.py`
3. `fetchers/npi.py`
4. `fetchers/openfda.py`
5. `graph/builder.py`
6. `main.py`
7. `frontend/index.html`

---

## What's Been Built

### ✅ Completed
- Git repo initialized, branch set to `main`
- Full folder structure created
- `.gitignore`, `.env`, `requirements.txt` in place
- `graph/models.py` — complete Pydantic models: `Node`, `Edge`, `GraphMeta`, `GraphResponse`, `NodeType`, `EdgeType`

### 🔲 Stub files (empty, not yet implemented)
- `fetchers/npi.py`
- `fetchers/openfda.py`
- `fetchers/open_payments.py`
- `graph/builder.py`
- `main.py`
- `frontend/index.html`
