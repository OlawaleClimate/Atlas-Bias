#!/usr/bin/env python3
"""
search_papers.py — Agent 1 of 3

Searches OpenAlex for peer-reviewed papers relevant to a given bias entry.
Produces a ranked list of up to 7 candidates saved to:
  pipeline/outputs/papers/<bias-id>.json

Usage:
    python agents/search_papers.py --bias cold-tongue-bias
    python agents/search_papers.py --bias cold-tongue-bias --show-all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parents[1]
OUT_DIR     = REPO_ROOT / "pipeline" / "outputs" / "papers"
OPENALEX    = "https://api.openalex.org/works"
UA          = "AtlasBiasBot/2.0 (mailto:atlas-bias@noreply.github.io)"

# ─────────────────────────────────────────────────────────────────────────────
# Bias catalogue  (name, primary query terms, secondary/mechanism query)
# ─────────────────────────────────────────────────────────────────────────────
BIAS_CATALOGUE: dict[str, dict[str, Any]] = {
    "cold-tongue-bias": {
        "name": "Cold Tongue Bias",
        "category": "temperature",
        "region": "equatorial_pacific",
        "primary_query": '"cold tongue bias" equatorial Pacific CMIP climate model SST',
        "secondary_query": "equatorial Pacific SST cold bias trade wind upwelling CMIP coupled model",
        "keywords": ["cold tongue", "equatorial pacific", "sst bias", "trade wind",
                     "upwelling", "cmip", "coupled model", "tropical pacific"],
    },
    "double-itcz": {
        "name": "Double ITCZ",
        "category": "precipitation",
        "region": "tropical_pacific",
        "primary_query": '"double ITCZ" bias CMIP climate model precipitation tropical Pacific',
        "secondary_query": "double intertropical convergence zone bias Southern Hemisphere precipitation CMIP model",
        "keywords": ["double itcz", "intertropical convergence zone", "southern hemisphere",
                     "precipitation bias", "cmip", "tropical pacific", "itcz"],
    },
    "southern-ocean-warm-sst": {
        "name": "Southern Ocean Warm SST Bias",
        "category": "temperature",
        "region": "southern_ocean",
        "primary_query": '"Southern Ocean" SST warm bias CMIP climate model sea surface temperature',
        "secondary_query": "Southern Ocean warm bias shortwave cloud radiation coupled model CMIP",
        "keywords": ["southern ocean", "sst bias", "warm bias", "sea surface temperature",
                     "cmip", "shortwave", "cloud", "radiation"],
    },
    "southern-ocean-shortwave": {
        "name": "Southern Ocean Shortwave Bias",
        "category": "clouds",
        "region": "southern_ocean",
        "primary_query": '"Southern Ocean" shortwave bias cloud radiation CMIP climate model',
        "secondary_query": "Southern Ocean absorbed shortwave radiation cloud bias CMIP model Southern Hemisphere",
        "keywords": ["southern ocean", "shortwave", "cloud bias", "radiation",
                     "cmip", "reflected", "absorbed", "southern hemisphere"],
    },
    "low-cloud-underestimate": {
        "name": "Low Cloud Underestimate",
        "category": "clouds",
        "region": "eastern_subtropical_oceans",
        "primary_query": "stratocumulus cloud bias CMIP climate model shortwave radiation boundary layer",
        "secondary_query": "low-level cloud underestimate climate model subtropical eastern Pacific Atlantic",
        "keywords": ["stratocumulus", "low cloud", "cloud fraction", "cloud bias",
                     "cmip", "radiation", "boundary layer", "subtropical",
                     "shortwave", "cloud cover"],
    },
}

# Whitelisted journals (lower-cased substrings — a match if any substring is found)
JOURNAL_WHITELIST = [
    "journal of climate",
    "geophysical research letters",
    "journal of geophysical research",
    "climate dynamics",
    "nature climate change",
    "nature geoscience",
    "bulletin of the american meteorological society",
    "bams",
    "geoscientific model development",
    "journal of advances in modeling earth systems",
    "james",
    "ocean modelling",
    "monthly weather review",
    "journal of the atmospheric sciences",
    "atmospheric chemistry and physics",
    "earth system dynamics",
]

REQUEST_DELAY   = 1.5   # seconds between OpenAlex calls
REQUEST_TIMEOUT = 20
MIN_CITATIONS   = 10
YEAR_MIN        = 1990
CANDIDATES_KEEP = 10    # keep top 10 (5 primary + 5 reserve for upgrade/fallback)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────────────────────
def _get(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


# ─────────────────────────────────────────────────────────────────────────────
# OpenAlex search
# ─────────────────────────────────────────────────────────────────────────────
def search_openalex(query: str, n: int = 20) -> list[dict[str, Any]]:
    params = {
        "search":   query,
        "per_page": str(n),
        "filter":   f"publication_year:>{YEAR_MIN},cited_by_count:>{MIN_CITATIONS - 1}",
        "select":   "id,title,doi,authorships,publication_year,primary_location,"
                    "abstract_inverted_index,cited_by_count",
        "sort":     "relevance_score:desc",
    }
    url = OPENALEX + "?" + urllib.parse.urlencode(params)
    status, body = _get(url)
    if status != 200 or not body:
        return []
    try:
        return json.loads(body).get("results", [])
    except json.JSONDecodeError:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Abstract reconstruction from OpenAlex inverted index
# ─────────────────────────────────────────────────────────────────────────────
def reconstruct_abstract(inv: dict[str, list[int]] | None) -> str:
    if not inv:
        return ""
    size = max(pos for positions in inv.values() for pos in positions) + 1
    words = [""] * size
    for word, positions in inv.items():
        for pos in positions:
            words[pos] = word
    return " ".join(w for w in words if w)


# ─────────────────────────────────────────────────────────────────────────────
# Journal whitelist check
# ─────────────────────────────────────────────────────────────────────────────
def journal_ok(paper: dict[str, Any]) -> tuple[bool, str]:
    loc = paper.get("primary_location") or {}
    src = loc.get("source") or {}
    name = (src.get("display_name") or "").lower()
    if not name:
        return False, "unknown journal"
    for approved in JOURNAL_WHITELIST:
        if approved in name:
            return True, src.get("display_name", name)
    return False, src.get("display_name", name)


# ─────────────────────────────────────────────────────────────────────────────
# Keyword scoring
# ─────────────────────────────────────────────────────────────────────────────
def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    t = text.lower()
    return [kw for kw in keywords if kw in t]


# ─────────────────────────────────────────────────────────────────────────────
# Format authors
# ─────────────────────────────────────────────────────────────────────────────
def fmt_authors(authorships: list[dict]) -> str:
    names = []
    for a in authorships[:4]:
        display = (a.get("author") or {}).get("display_name", "")
        if display:
            parts = display.split()
            names.append(parts[-1] if parts else display)
    if not names:
        return "Unknown"
    suffix = " et al." if len(authorships) > 4 else ""
    if len(names) == 1:
        return names[0] + suffix
    return ", ".join(names[:-1]) + " and " + names[-1] + suffix


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Search OpenAlex for papers on a bias entry.")
    parser.add_argument("--bias", required=True, help="Bias ID (e.g. cold-tongue-bias)")
    parser.add_argument("--show-all", action="store_true",
                        help="Also print candidates that were filtered out")
    args = parser.parse_args()

    bias_id = args.bias.lower().strip()
    if bias_id not in BIAS_CATALOGUE:
        print(f"[error] '{bias_id}' not in catalogue. Available:\n  " +
              "\n  ".join(BIAS_CATALOGUE.keys()), file=sys.stderr)
        return 1

    cfg = BIAS_CATALOGUE[bias_id]
    keywords = cfg["keywords"]

    print(f"\n{'═' * 65}")
    print(f"  SEARCH: {cfg['name']}")
    print(f"{'═' * 65}\n")

    # ── Run both queries ──────────────────────────────────────────────────────
    print(f"  Primary query   : {cfg['primary_query']}")
    primary = search_openalex(cfg["primary_query"])
    time.sleep(REQUEST_DELAY)

    print(f"  Secondary query : {cfg['secondary_query']}")
    secondary = search_openalex(cfg["secondary_query"])
    time.sleep(REQUEST_DELAY)

    # ── Merge + deduplicate by DOI ────────────────────────────────────────────
    seen_dois: set[str] = set()
    all_candidates: list[dict[str, Any]] = []
    for paper in primary + secondary:
        raw_doi = (paper.get("doi") or "").replace("https://doi.org/", "").strip()
        if not raw_doi or raw_doi in seen_dois:
            continue
        seen_dois.add(raw_doi)
        abstract = reconstruct_abstract(paper.get("abstract_inverted_index"))
        title    = paper.get("title") or ""
        full_text = (title + " " + abstract).lower()
        hits     = keyword_hits(full_text, keywords)
        score    = (paper.get("cited_by_count") or 0) * len(hits)

        ok_journal, journal_name = journal_ok(paper)
        all_candidates.append({
            "doi":          raw_doi,
            "title":        title,
            "authors":      fmt_authors(paper.get("authorships", [])),
            "year":         paper.get("publication_year") or 0,
            "journal":      journal_name,
            "journal_ok":   ok_journal,
            "cited_by":     paper.get("cited_by_count") or 0,
            "abstract":     abstract,
            "keyword_hits": hits,
            "score":        score,
            "verified":     None,       # filled by verify_papers.py
        })

    # ── Sort by score descending ──────────────────────────────────────────────
    all_candidates.sort(key=lambda x: x["score"], reverse=True)

    # ── Apply filters ─────────────────────────────────────────────────────────
    passed:  list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for c in all_candidates:
        reasons = []
        if not c["journal_ok"]:
            reasons.append(f"journal not whitelisted ({c['journal']})")
        if c["cited_by"] < MIN_CITATIONS:
            reasons.append(f"only {c['cited_by']} citations")
        if len(c["keyword_hits"]) < 2:
            reasons.append(f"only {len(c['keyword_hits'])} keyword hit(s): {c['keyword_hits']}")
        if c["year"] < YEAR_MIN:
            reasons.append(f"year {c['year']} < {YEAR_MIN}")

        if reasons:
            c["drop_reasons"] = reasons
            dropped.append(c)
        else:
            c["drop_reasons"] = []
            passed.append(c)

    # Keep top 7 passed
    final = passed[:CANDIDATES_KEEP]

    # ── Print review table ────────────────────────────────────────────────────
    print(f"\n  {'─' * 63}")
    print(f"  {'#':<3} {'Authors (Year)':<28} {'Journal':<22} {'Cites':>5}  Status")
    print(f"  {'─' * 63}")
    for i, c in enumerate(final, 1):
        journal_short = c["journal"][:20]
        authors_short = f"{c['authors']} ({c['year']})"[:26]
        print(f"  {i:<3} {authors_short:<28} {journal_short:<22} {c['cited_by']:>5}  ✓ PASS")
        print(f"      DOI: {c['doi']}")
        print(f"      Hits: {c['keyword_hits']}")

    if args.show_all and dropped:
        print(f"\n  {'─' * 63}")
        print(f"  DROPPED ({len(dropped)}):")
        for c in dropped[:5]:
            print(f"  ✗  {c['authors']} ({c['year']}) — {c['journal']}")
            print(f"     Reasons: {'; '.join(c['drop_reasons'])}")

    print(f"\n  {'─' * 63}")
    print(f"  {len(final)} candidates kept  |  {len(dropped)} dropped")
    if len(final) < 5:
        print(f"  ⚠  WARNING: only {len(final)} candidates — "
              "verify_papers.py may need to trigger fallback search")
    print(f"  {'─' * 63}\n")

    # ── Write output ──────────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{bias_id}.json"
    out_path.write_text(json.dumps({
        "bias_id":    bias_id,
        "bias_name":  cfg["name"],
        "keywords":   keywords,
        "candidates": final,
        "dropped":    dropped if args.show_all else [],
    }, indent=2), encoding="utf-8")

    print(f"  Written → {out_path.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
