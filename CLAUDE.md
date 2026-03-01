# Impiricus Clinical Intelligence Graph

Full-stack web app visualizing the pharma-physician influence network for any US state and year, using only public government APIs.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14, FastAPI, httpx (async), NetworkX |
| Frontend | `index.html` + `style.css` + `app.js` — no build step, no npm |
| 3D Visualization | `3d-force-graph` via CDN (Three.js-based) |
| Data sources | NPI Registry, OpenFDA, CMS Open Payments |
| Auth | None — all APIs are public |
| Run | `source .venv/bin/activate && uvicorn main:app --reload --port 8000` then open `frontend/index.html` |

---

## Project Structure

```
impiricus-pharma-graph/
├── main.py                   # FastAPI entrypoint, cache, fetcher orchestration
├── requirements.txt
├── .env                      # Empty — no keys needed yet
├── .gitignore
├── CLAUDE.md
├── docs/
│   └── workflow.md           # Full data flow explanation (fetchers → graph build)
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
    ├── index.html            # HTML structure only
    ├── style.css             # All styles, animations, layout
    └── app.js                # All JS — graph init, loading, highlight, FTM, sidebar
```

---

## API Endpoint

### `GET /api/graph/{state}/{year}`
- `state`: 2-letter US state code (e.g. `GA`, `TX`)
- `year`: integer, valid range 2020–2023
- Returns: `GraphResponse` (nodes, edges, meta)
- Validates state against full 50-state + DC set before hitting any external APIs
- Never returns 500 — always returns a valid (possibly partial) `GraphResponse`

### `GET /health`
- Returns `{ "status": "ok", "cached_queries": N }`

---

## Data Sources

### NPI Registry
- Base URL: `https://npiregistry.cms.hhs.gov/api/`
- Params: `version=2.1`, `state`, `taxonomy_description`, `limit=20`
- Rate limit: ~3 req/sec — `asyncio.sleep(0.4)` between specialty calls
- Specialties queried: Cardiology, Endocrinology, Internal Medicine, Oncology, Neurology
- Deduplicates by NPI number (same doctor can appear in multiple specialty results)

### OpenFDA
- Base URL: `https://api.fda.gov/drug/label.json`
- Search: `openfda.manufacturer_name:"<company>"`, limit 10
- Parses `indications_and_usage[0]` free-text against `CONDITION_MAP` for ICD-10 codes
- 404 = no results (not an error) — medical device companies always return 404
- Rate limit: 40 req/min unauthenticated — `asyncio.sleep(0.3)` between company calls

### CMS Open Payments
- Base URL: `https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset_id}/0`
- POST with JSON body — filter `recipient_state`, sort by amount desc, cap 500 rows
- **Verified dataset IDs** (fetched from CMS metastore):
  ```python
  2020: "a08c4b30-5cf3-4948-ad40-36f404619019"
  2021: "0380bbeb-aea1-58b6-b708-829f92a48202"
  2022: "df01c2f8-dc1f-4e79-96cb-8208beaf143c"
  2023: "fb3a65aa-c901-4a38-a813-b04b00dfa2a9"
  ```
- If a dataset ID returns 404, fetcher hits `metastore/schemas/dataset/items` to resolve dynamically
- Field names: `covered_recipient_npi`, `applicable_manufacturer_or_applicable_gpo_making_payment_name`, `total_amount_of_payment_usdollars`, etc.

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

---

## Truncation Logic (graph/builder.py)

- Max 200 nodes, 400 edges, 100 PEER_OF edges
- **Node truncation**: anchor nodes (pharma, drug, condition) always kept in full. Only physicians truncated, sorted by `total_received` descending.
- **Edge truncation**: structural edges (MANUFACTURES, INDICATED_FOR, SPECIALIZES_IN, RECEIVED_FOR, PEER_OF) kept in full. PAID edges sorted by weight and capped last.

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
# Parallel fetch
payments, physicians = await asyncio.gather(fetch_open_payments(state, year), fetch_npi_physicians(state))
# Serial — depends on company names from payments
company_names = list({p["company"] for p in payments})
drugs = await fetch_drugs(company_names)
# Build
graph = build_graph(payments, physicians, drugs, state, year)
```

In-memory cache: dict keyed on `(state, year)` with 1-hour TTL.

---

## Frontend Features (app.js)

1. **State + Year Selector** — top left, defaults to GA/2023, triggers full reload on change
2. **Loading State** — pulsing cyan dots with `"Fetching clinical network for {STATE} {YEAR}..."`
3. **Click to Highlight Reach** — click any node to dim all unconnected nodes/edges; background click resets
4. **Node Info Panel** — slides in from right on click; shows type badge, label, all props; border color matches node type
5. **Ranked Sidebar** — top 15 pharma companies by total_paid; search filters in real time; click flies camera to node
6. **Stats Bar** — top right: node count, edge count, total payments (sum of PAID edges), state/year label
7. **Follow the Money** — two-step mode: select pharma → select drug → highlights physicians paid by that pharma for that drug; falls back to all paid physicians if no RECEIVED_FOR match

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

## Known Limitations (Demo Scope)

| Limitation | Reason |
|---|---|
| Only 5 specialties from NPI | Full NPI taxonomy has 800+ codes |
| Only 8 conditions in keyword map | Full NLP would use ICD-10 database + medical NLP |
| 500 payment record cap | GA/TX/CA have tens of thousands of records |
| OpenFDA misses device companies | FDA drug label DB doesn't include medical devices |
| PEER_OF rarely fires | Requires NPI specialty overlap with CMS payment recipients |

---

## Current Status

### ✅ Complete
- Git repo on `main`, feature branch `feature/backend-fetchers`
- Python 3.14 venv at `.venv/` with all dependencies installed
- `graph/models.py` — Pydantic models
- `fetchers/open_payments.py` — CMS fetcher with verified dataset IDs + dynamic fallback resolution
- `fetchers/npi.py` — NPI fetcher with rate limiting + deduplication
- `fetchers/openfda.py` — OpenFDA fetcher with condition parsing
- `graph/builder.py` — full graph assembly, all 6 edge types, smart truncation
- `main.py` — FastAPI app, 1-hour cache, validation, CORS, `/health` endpoint
- `frontend/index.html` + `style.css` + `app.js` — full 7-feature UI
- `docs/workflow.md` — full data flow documentation
- Tested end-to-end: GA/2023 returns 200 nodes, ~186 edges, all 4 node types present

### 🔲 Not Started
- Deploy / hosting
- Additional states tested beyond GA
- PEER_OF edge improvement (currently rarely fires due to NPI/CMS data overlap gap)
