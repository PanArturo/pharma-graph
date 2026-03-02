"""
Pre-fetch graph data for a set of states/years and save as static JSON files.

Usage:
    python -m scripts.prefetch              # fetch all TARGETS below
    python -m scripts.prefetch GA 2024      # fetch a single state/year

Output:
    frontend/data/{STATE}_{YEAR}.json       # graph data file
    frontend/data/manifest.json             # index of available combos
"""

import asyncio
import json
import sys
from pathlib import Path

# Make sure project root is on the path when run as a module
sys.path.insert(0, str(Path(__file__).parent.parent))

from fetchers.npi import fetch_npi_physicians
from fetchers.open_payments import fetch_open_payments
from fetchers.openfda import fetch_drugs
from graph.builder import build_graph

OUTPUT_DIR = Path(__file__).parent.parent / "frontend" / "data"

# Default targets to pre-fetch — edit this list as needed
TARGETS: list[tuple[str, int]] = [
    ("GA", 2024),
    ("GA", 2023),
    ("GA", 2022),
    ("CA", 2024),
    ("CA", 2023),
    ("CA", 2022),
]


async def prefetch_one(state: str, year: int) -> bool:
    out_path = OUTPUT_DIR / f"{state}_{year}.json"
    print(f"  Fetching {state} {year}...", flush=True)
    try:
        payments, physicians = await asyncio.gather(
            fetch_open_payments(state, year),
            fetch_npi_physicians(state),
        )
        company_names = list({p["company"] for p in payments})
        drugs = await fetch_drugs(company_names)
        graph = build_graph(payments, physicians, drugs, state, year)
        out_path.write_text(graph.model_dump_json())
        size_kb = out_path.stat().st_size // 1024
        print(f"  ✓ {state} {year} → {out_path.name} ({size_kb} KB, "
              f"{graph.meta.node_count} nodes, {graph.meta.edge_count} edges)")
        return True
    except Exception as exc:
        print(f"  ✗ {state} {year} failed: {exc}")
        return False


def write_manifest() -> None:
    """Scan output dir and write manifest.json mapping state → [years]."""
    available: dict[str, list[int]] = {}
    for f in sorted(OUTPUT_DIR.glob("??_????.json")):
        # skip manifest.json itself
        if f.stem == "manifest":
            continue
        parts = f.stem.split("_")
        if len(parts) == 2 and parts[1].isdigit():
            state, year = parts[0], int(parts[1])
            available.setdefault(state, []).append(year)
    # sort years descending within each state
    for state in available:
        available[state].sort(reverse=True)
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(available, indent=2))
    total = sum(len(v) for v in available.values())
    print(f"\nManifest written: {len(available)} states, {total} datasets")
    for state, years in sorted(available.items()):
        print(f"  {state}: {years}")


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Allow ad-hoc single fetch: python -m scripts.prefetch TX 2023
    if len(sys.argv) == 3:
        targets = [(sys.argv[1].upper(), int(sys.argv[2]))]
    else:
        targets = TARGETS

    print(f"Pre-fetching {len(targets)} dataset(s)...\n")
    for state, year in targets:
        await prefetch_one(state, year)

    write_manifest()


if __name__ == "__main__":
    asyncio.run(main())
