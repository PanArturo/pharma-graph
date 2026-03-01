# Impiricus Clinical Intelligence Graph — PRD for Claude Code

## Project Overview

Build a full-stack web application that visualizes the pharma-physician influence network in any US state for a given year. The backend fetches live data from three public US government health APIs, assembles a graph using NetworkX, and exposes it via a single FastAPI endpoint. The frontend renders the graph as a visually stunning interactive 3D force graph using `3d-force-graph` (Three.js-based).

This is a demo project targeting the Impiricus engineering team. Impiricus builds an AI-powered SMS platform connecting pharma companies to physicians based on clinical events. This project reconstructs the real-world influence network their platform operates on top of — using only public data.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, httpx (async), NetworkX |
| Frontend | Single `index.html`, `3d-force-graph` CDN, Tailwind CSS CDN |
| Data sources | NPI Registry, OpenFDA, CMS Open Payments |
| Auth | None — all APIs are public and free |
| Run | `uvicorn main:app --reload` then open `frontend/index.html` |

---

## Project Structure

```
impiricus-graph/
├── main.py
├── fetchers/
│   ├── __init__.py
│   ├── npi.py
│   ├── openfda.py
│   └── open_payments.py
├── graph/
│   ├── __init__.py
│   ├── builder.py
│   └── models.py
├── frontend/
│   └── index.html
├── requirements.txt
└── .env
```

---

## API Endpoint

### `GET /api/graph/{state}/{year}`

**Path params:**
- `state` — 2-letter US state code, e.g. `GA`, `TX`, `CA`
- `year` — integer, e.g. `2023`. Valid range: 2020–2023.

**Examples:**
```
/api/graph/GA/2023
/api/graph/TX/2022
/api/graph/CA/2021
```

**Response: `GraphResponse`**
```json
{
  "nodes": [
    {
      "id": "pfizer",
      "type": "pharma",
      "label": "Pfizer",
      "props": {
        "total_paid": 142000,
        "num_physicians": 34
      }
    },
    {
      "id": "npi_1234567890",
      "type": "physician",
      "label": "Dr. Lisa Chen",
      "props": {
        "npi": "1234567890",
        "specialty": "Cardiology",
        "city": "Atlanta",
        "state": "GA",
        "total_received": 18500
      }
    }
  ],
  "edges": [
    {
      "source": "pfizer",
      "target": "npi_1234567890",
      "type": "PAID",
      "weight": 12500,
      "props": {
        "drug": "Eliquis",
        "nature": "Speaking Fee",
        "date": "2023-06-14"
      }
    }
  ],
  "meta": {
    "node_count": 87,
    "edge_count": 134,
    "state": "GA",
    "year": 2023,
    "sources": ["NPI Registry", "OpenFDA", "CMS Open Payments"]
  }
}
```

**Error responses:**
- `400` — invalid state code or year out of range
- `422` — malformed params
- `503` — upstream API unavailable (return partial graph if possible, never crash)

---

## Data Sources

### 1. NPI Registry
- **Base URL:** `https://npiregistry.cms.hhs.gov/api/`
- **Auth:** None
- **Use:** Fetch licensed physicians in the given state by specialty
- **Key params:** `version=2.1`, `state=GA`, `taxonomy_description=Cardiology`, `limit=20`
- **Rate limit:** ~3 req/sec — add `asyncio.sleep(0.4)` between specialty batch calls
- **Returns:** NPI, first name, last name, taxonomy (specialty), practice city, practice state

**Specialties to query:**
```python
SPECIALTIES = [
    "Cardiology",
    "Endocrinology",
    "Internal Medicine",
    "Oncology",
    "Neurology",
]
```

### 2. OpenFDA Drug Label
- **Base URL:** `https://api.fda.gov/drug/label.json`
- **Auth:** None
- **Use:** Given pharma company names from Open Payments, fetch their drugs and parse conditions from indications text
- **Key params:** `search=openfda.manufacturer_name:"Pfizer"&limit=10`
- **Returns:** brand_name, generic_name, manufacturer_name, indications_and_usage

**Condition parsing — keyword map:**
```python
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
```
Parse `indications_and_usage[0].lower()` against this map. A drug can match multiple conditions.

### 3. CMS Open Payments
- **Base URL:** `https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset_id}/0`
- **Auth:** None
- **Use:** Fetch payments from pharma companies to physicians filtered by state and year
- **Filter:** `recipient_state = {state}`
- **Pagination:** max 500 rows per call, use `offset` to paginate. Cap at 500 records total for demo performance.
- **Returns:** physician NPI, physician first/last name, company name, drug/device name, payment amount, nature of payment, date

**Dataset IDs by year:**
```python
OPEN_PAYMENTS_DATASETS = {
    2020: "0380bbeb-aea1-5898-90ef-7f4e02b26f24",
    2021: "d7c1c06a-4b7e-5d7d-9b5d-7b5b3b5b5b5b",
    2022: "9b5d7b5b-3b5b-5b5b-7b5b-3b5b5b5b5b5b",
    2023: "06dba66e-9378-5e56-9b93-0bdc8b193ebb",
}
```
Important: Verify all dataset IDs at `https://openpaymentsdata.cms.gov/api/1/datastore/list` before building — IDs may differ. If an ID returns 404, fetch the list endpoint and find the correct dataset for that program year.

**CMS API query format:**
```python
# POST request with JSON body
payload = {
    "conditions": [
        {
            "property": "recipient_state",
            "value": state,
            "operator": "="
        }
    ],
    "limit": 500,
    "offset": 0,
    "sort": [{"property": "total_amount_of_payment_usdollars", "order": "desc"}]
}
```

---

## Node Types

| Type | ID Format | Label | Key Props |
|---|---|---|---|
| `pharma` | slugified company name e.g. `pfizer` | Company name | total_paid, num_physicians |
| `drug` | `drug_{slugified_brand}` | Brand name | generic_name, drug_class, conditions |
| `condition` | `cond_{icd10}` e.g. `cond_I48` | Condition name | icd10_code |
| `physician` | `npi_{npi_number}` | Full name with Dr. prefix | npi, specialty, city, state, total_received |

---

## Edge Types

| Type | From → To | Source | Weight |
|---|---|---|---|
| `MANUFACTURES` | pharma → drug | OpenFDA manufacturer match | 1.0 |
| `INDICATED_FOR` | drug → condition | OpenFDA indications parsed | 1.0 |
| `SPECIALIZES_IN` | physician → condition | NPI taxonomy mapped | 1.0 |
| `PAID` | pharma → physician | CMS Open Payments | payment amount USD |
| `RECEIVED_FOR` | physician → drug | CMS Open Payments drug name | payment amount USD |
| `PEER_OF` | physician → physician | Derived | 1.0 |

**Deriving `PEER_OF` edges:**
Two physicians get a `PEER_OF` edge if they share the same specialty AND received payments from the same pharma company in the same year. This reconstructs the professional influence network. Cap at 100 peer edges total to avoid visual clutter.

**NPI taxonomy → condition mapping:**
```python
TAXONOMY_CONDITION_MAP = {
    "Cardiology":        ["I48", "I50"],
    "Endocrinology":     ["E11"],
    "Internal Medicine": ["I10", "E11"],
    "Oncology":          ["C80"],
    "Neurology":         ["G35", "I63"],
}
```

---

## Pydantic Models (`graph/models.py`)

```python
from pydantic import BaseModel
from typing import Any, Literal

NodeType = Literal["pharma", "drug", "condition", "physician"]
EdgeType = Literal["MANUFACTURES", "INDICATED_FOR", "SPECIALIZES_IN",
                   "PAID", "RECEIVED_FOR", "PEER_OF"]

class Node(BaseModel):
    id: str
    type: NodeType
    label: str
    props: dict[str, Any] = {}

class Edge(BaseModel):
    source: str
    target: str
    type: EdgeType
    weight: float = 1.0
    props: dict[str, Any] = {}

class GraphMeta(BaseModel):
    node_count: int
    edge_count: int
    state: str
    year: int
    sources: list[str]

class GraphResponse(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    meta: GraphMeta
```

---

## Graph Builder (`graph/builder.py`)

Use `nx.DiGraph`. Build order:
1. Add all nodes with type and props as node attributes
2. Add explicit edges (MANUFACTURES, INDICATED_FOR, SPECIALIZES_IN, PAID, RECEIVED_FOR)
3. Derive PEER_OF edges
4. Serialize manually into `GraphResponse` — do NOT use `nx.node_link_data()` directly

---

## Fetcher Execution Order (`main.py`)

```python
# Step 1 — parallel fetch of payments + physicians
payments, physicians = await asyncio.gather(
    fetch_open_payments(state, year),
    fetch_npi_physicians(state),
)

# Step 2 — drugs depend on company names from payments
company_names = list({p["company"] for p in payments})
drugs = await fetch_drugs(company_names)

# Step 3 — build graph
graph = build_graph(payments, physicians, drugs)
return graph
```

Add in-memory cache with 1-hour TTL keyed on `(state, year)`. Use a dict with stored timestamps.

---

## CORS

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Frontend (`frontend/index.html`)

Single self-contained HTML file. No build step. No npm. No React.

**CDN imports required:**
```html
<script src="https://unpkg.com/3d-force-graph@1"></script>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
```

---

### Visual Design

**Background:** `#050A0F` near-black with subtle radial gradient at center

**Fonts:** Space Mono for data labels and UI, Syne 800 for headings

**Node colors:**
```javascript
const NODE_COLORS = {
  pharma:    '#00E5FF',  // cyan
  physician: '#00FF9D',  // green
  drug:      '#FFD600',  // yellow
  condition: '#FF4D8B',  // pink
}
```

**Edge colors:**
```javascript
const EDGE_COLORS = {
  PAID:         '#FF6B35',  // orange — money flow, most prominent
  PEER_OF:      '#7B61FF',  // purple
  MANUFACTURES: '#1A2D45',  // dim
  INDICATED_FOR:'#1A2D45',  // dim
  SPECIALIZES_IN:'#1A2D45', // dim
  RECEIVED_FOR: '#1A2D45',  // dim
}
```

---

### 3d-force-graph Configuration

```javascript
const Graph = ForceGraph3D()(document.getElementById('graph'))
  .backgroundColor('#050A0F')
  .nodeLabel(node => node.label)
  .nodeColor(node => NODE_COLORS[node.type])
  .nodeVal(node => {
    if (node.type === 'pharma')    return Math.sqrt(node.props.total_paid / 1000) + 5
    if (node.type === 'physician') return Math.sqrt((node.props.total_received || 1000) / 500) + 3
    return 4
  })
  .nodeOpacity(0.9)
  .linkColor(link => EDGE_COLORS[link.type] || '#1A2D45')
  .linkWidth(link => link.type === 'PAID' ? Math.log((link.weight / 1000) + 1) + 0.5 : 0.5)
  .linkDirectionalParticles(link => link.type === 'PAID' ? 4 : 0)
  .linkDirectionalParticleSpeed(0.005)
  .linkDirectionalParticleWidth(link => Math.log((link.weight / 5000) + 1) + 1)
  .linkDirectionalParticleColor(() => '#FF6B35')
  .onNodeClick(node => showNodePanel(node))
  .onNodeHover(node => highlightConnections(node))
  .onBackgroundClick(() => resetHighlight())
```

---

### UI Features to Build

**1. State + Year Selector (top left)**
- Dropdown with all 50 US state codes
- Year dropdown: 2020, 2021, 2022, 2023
- Default: GA / 2023
- On change: show loading state, fetch `/api/graph/{state}/{year}`, reload graph with new data

**2. Loading State**
- While fetching: render 3 pulsing dots in center of graph canvas
- Text below dots: `"Fetching clinical network for {STATE} {YEAR}..."`
- Animate opacity 0→1→0 on each dot with staggered delay

**3. Click to Highlight Reach**
- Clicking any node: dim all non-connected nodes to 10% opacity, dim non-connected edges to 5% opacity
- Connected nodes and their edges: full brightness
- Clicking background: reset all to full opacity
- Implement via `nodeOpacity` and `linkOpacity` dynamic functions checking a `highlightedNodeIds` Set

**4. Node Info Panel (right side)**
- Slides in from right on node click (CSS transform transition)
- Shows: colored type badge, node label as large heading, all props as key-value rows
- Border left color matches node type color
- X button closes panel and resets highlight
- Styled dark: `bg-[#0D1520]` border `border-[#1A2D45]`

**5. Ranked Sidebar (left side)**
- Lists top 15 pharma companies sorted by total_paid descending
- Each row: rank number, company name, total paid formatted as `$X.XK` or `$X.XM`, physician count
- Clicking a row: flies camera to that pharma node using `Graph.centerAt(x, y, z, 1000)` and `Graph.cameraPosition({...}, null, 1000)`
- Search input at top filters the list in real time

**6. Stats Bar (top right, always visible)**
- Total Nodes count
- Total Edges count  
- Total Payments: sum of all PAID edge weights, formatted as `$X.XM`
- State + Year label

**7. "Follow the Money" Mode (top bar button)**
- Toggle button: when active, border glows orange
- Step 1: user clicks a pharma node — it highlights, sidebar shows "Now click a drug"
- Step 2: user clicks a drug node — graph highlights every physician who has BOTH a PAID edge from that pharma AND a RECEIVED_FOR edge to that drug
- Highlighted edges scale thickness by payment amount
- All other nodes dim to 5% opacity
- Reset button clears mode
- This is the primary demo feature — design it to be visually dramatic

**8. Legend (bottom left)**
- Small fixed panel showing node type → color dot → label
- Edge type → color line → label for PAID and PEER_OF only
- Collapsible

---

## Error Handling Rules

- Each fetcher returns `[]` on any exception — never propagates errors up
- If Open Payments returns 0 results, still build graph from NPI + OpenFDA data
- If NPI returns 0 results for a specialty, skip and continue
- Log all upstream errors with API name and HTTP status
- `/api/graph/{state}/{year}` never returns 500 — always returns valid `GraphResponse`

---

## Performance Targets

- Cold API response: under 10 seconds
- Cached API response: under 200ms
- Frontend render: under 2 seconds after data received
- Cap: 200 nodes max, 400 edges max — truncate by weight descending if over limit

---

## Requirements.txt

```
fastapi>=0.110.0
uvicorn>=0.27.0
httpx>=0.27.0
networkx>=3.2
pydantic>=2.6
python-dotenv>=1.0
```

---

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Open frontend/index.html in browser
# API explorer at http://localhost:8000/docs
```

---

## Build Order

Build and verify each layer before moving to the next:

1. `graph/models.py` — Pydantic models, no dependencies
2. `fetchers/open_payments.py` — test with GA/2023, print raw results
3. `fetchers/npi.py` — test with GA, print physician count per specialty
4. `fetchers/openfda.py` — test with company names from step 2, verify condition parsing
5. `graph/builder.py` — assemble graph, print node/edge counts and types
6. `main.py` — wire all fetchers, test `GET /api/graph/GA/2023` returns valid JSON
7. `frontend/index.html` — build full UI, test all 7 interactive features against live API
