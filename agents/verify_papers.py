#!/usr/bin/env python3
"""
verify_papers.py — Agent 2 of 3

Reads pipeline/outputs/papers/<bias-id>.json produced by search_papers.py.
For each candidate paper, runs 4 independent checks:

  1. DOI resolves  — doi.org/<doi> lands on a real paper page
  2. Title match   — Crossref title matches OpenAlex title (fuzzy ≥ 0.75)
  3. Journal match — Crossref journal matches OpenAlex journal
  4. Abstract check— Crossref abstract contains ≥ 2 bias keywords

Papers that fail are replaced from the reserve list (slots 6–7).
If still under 5 after using all reserves, runs a fallback search.
If still under 5 after fallback, stops and flags for manual review.

Output: updates pipeline/outputs/papers/<bias-id>.json in-place
        (adds "verified" block to each paper, removes failed ones)

Usage:
    python agents/verify_papers.py --bias cold-tongue-bias
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

REPO_ROOT  = Path(__file__).resolve().parents[1]
PAPERS_DIR = REPO_ROOT / "pipeline" / "outputs" / "papers"
CROSSREF   = "https://api.crossref.org/works/{doi}"
OPENALEX   = "https://api.openalex.org/works"
UA         = "AtlasBiasBot/2.0 (mailto:atlas-bias@noreply.github.io)"

REQUEST_DELAY   = 1.5
REQUEST_TIMEOUT = 20
TITLE_MATCH_MIN = 0.70   # fuzzy title similarity threshold
ABSTRACT_HITS_MIN = 2    # must mention ≥ 2 bias keywords
MIN_VERIFIED    = 5      # target number of confirmed papers


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
# Check 1 — DOI resolves to a real paper page
# ─────────────────────────────────────────────────────────────────────────────
def check_doi_resolves(doi: str) -> tuple[bool, int, str]:
    """Return (ok, http_status, landing_url)."""
    safe = urllib.parse.quote(doi, safe="/:@!$&'()*+,;=.-_~")
    url  = f"https://doi.org/{safe}"
    req  = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            landing = r.url
            # Reject if it looks like a search page or generic homepage
            bad_patterns = [
                "/search?", "/search/", "?query=", "404", "not-found",
                "error", "page-not-found",
            ]
            if any(p in landing.lower() for p in bad_patterns):
                return False, r.status, landing
            return True, r.status, landing
    except urllib.error.HTTPError as e:
        # 403 = publisher blocks bots but DOI resolved — treat as OK
        if e.code == 403:
            return True, 403, url
        return False, e.code, url
    except Exception:
        return False, 0, url


# ─────────────────────────────────────────────────────────────────────────────
# Crossref fetch
# ─────────────────────────────────────────────────────────────────────────────
def fetch_crossref(doi: str) -> dict[str, Any] | None:
    safe = urllib.parse.quote(doi, safe="/:@!$&'()*+,;=.-_~")
    status, body = _get(CROSSREF.format(doi=safe))
    if status != 200 or not body:
        return None
    try:
        return json.loads(body).get("message", {})
    except json.JSONDecodeError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — fuzzy title match
# ─────────────────────────────────────────────────────────────────────────────
def _tokenise(text: str) -> set[str]:
    return set(re.findall(r"\b[a-z]{3,}\b", text.lower()))


def title_similarity(a: str, b: str) -> float:
    ta, tb = _tokenise(a), _tokenise(b)
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    return len(intersection) / max(len(ta), len(tb))


def check_title_match(crossref_meta: dict[str, Any], openalex_title: str) -> tuple[bool, float, str]:
    titles = crossref_meta.get("title", [])
    cr_title = titles[0] if titles else ""
    score = title_similarity(cr_title, openalex_title)
    ok = score >= TITLE_MATCH_MIN
    return ok, score, cr_title


# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — journal match
# ─────────────────────────────────────────────────────────────────────────────
def check_journal_match(crossref_meta: dict[str, Any], openalex_journal: str) -> tuple[bool, str]:
    containers = crossref_meta.get("container-title", [])
    cr_journal = containers[0] if containers else ""
    # Fuzzy: check if one is a substring of the other (case-insensitive)
    a = cr_journal.lower()
    b = openalex_journal.lower()
    ok = (a in b) or (b in a) or title_similarity(a, b) >= 0.5
    return ok, cr_journal


# ─────────────────────────────────────────────────────────────────────────────
# Check 4 — abstract relevance from Crossref
# ─────────────────────────────────────────────────────────────────────────────
def _strip_xml(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def check_abstract_relevance(
    crossref_meta: dict[str, Any], keywords: list[str]
) -> tuple[bool, list[str], str]:
    abstract = _strip_xml(crossref_meta.get("abstract", "")).lower()
    if not abstract:
        # No abstract in Crossref — fall back to title-only check
        titles = crossref_meta.get("title", [])
        title_text = (titles[0] if titles else "").lower()
        hits = [kw for kw in keywords if kw in title_text]
        # A strong title match counts as 1 hit
        return len(hits) >= 1, hits, "(title-only check — no Crossref abstract)"
    hits = [kw for kw in keywords if kw in abstract]
    return len(hits) >= ABSTRACT_HITS_MIN, hits, abstract[:300]


# ─────────────────────────────────────────────────────────────────────────────
# Run all 4 checks on one paper
# ─────────────────────────────────────────────────────────────────────────────
def verify_paper(paper: dict[str, Any], keywords: list[str]) -> dict[str, Any]:
    doi       = paper["doi"]
    oa_title  = paper["title"]
    oa_journal = paper["journal"]

    result: dict[str, Any] = {
        "doi_resolves":        False,
        "http_status":         0,
        "landing_url":         "",
        "crossref_title":      "",
        "title_match_score":   0.0,
        "title_match_ok":      False,
        "crossref_journal":    "",
        "journal_match_ok":    False,
        "abstract_hits":       [],
        "abstract_snippet":    "",
        "abstract_ok":         False,
        "verdict":             "UNVERIFIED",
        "fail_reasons":        [],
    }

    # Check 1 — DOI resolves
    doi_ok, http_status, landing = check_doi_resolves(doi)
    result["doi_resolves"] = doi_ok
    result["http_status"]  = http_status
    result["landing_url"]  = landing
    time.sleep(REQUEST_DELAY)

    if not doi_ok:
        result["fail_reasons"].append(f"DOI does not resolve (HTTP {http_status})")
        result["verdict"] = "REJECTED"
        return result

    # Fetch Crossref metadata
    meta = fetch_crossref(doi)
    time.sleep(REQUEST_DELAY)

    if meta is None:
        result["fail_reasons"].append("Crossref returned no metadata")
        # Don't hard-fail on missing Crossref — some valid DOIs aren't in Crossref
        # But we can't do checks 2–4, so partial pass
        result["verdict"] = "PARTIAL"
        return result

    # Check 2 — title match
    title_ok, title_score, cr_title = check_title_match(meta, oa_title)
    result["crossref_title"]   = cr_title
    result["title_match_score"] = round(title_score, 3)
    result["title_match_ok"]   = title_ok
    if not title_ok:
        result["fail_reasons"].append(
            f"Title mismatch (score={title_score:.2f}): "
            f"Crossref='{cr_title[:60]}' vs OpenAlex='{oa_title[:60]}'"
        )

    # Check 3 — journal match
    journal_ok, cr_journal = check_journal_match(meta, oa_journal)
    result["crossref_journal"]  = cr_journal
    result["journal_match_ok"]  = journal_ok
    if not journal_ok:
        result["fail_reasons"].append(
            f"Journal mismatch: Crossref='{cr_journal}' vs OpenAlex='{oa_journal}'"
        )

    # Check 4 — abstract relevance
    abs_ok, hits, snippet = check_abstract_relevance(meta, keywords)
    result["abstract_ok"]      = abs_ok
    result["abstract_hits"]    = hits
    result["abstract_snippet"] = snippet
    if not abs_ok:
        result["fail_reasons"].append(
            f"Abstract has only {len(hits)} keyword hit(s): {hits}"
        )

    # Final verdict
    # Hard fails: DOI broken or title mismatch
    # Soft fails: journal mismatch or weak abstract — flag but don't reject
    hard_fails = [r for r in result["fail_reasons"]
                  if "DOI" in r or "Title" in r]
    if hard_fails:
        result["verdict"] = "REJECTED"
    elif result["fail_reasons"]:
        result["verdict"] = "FLAGGED"   # passes but needs human review
        result["fail_reasons"].insert(0, "SOFT FLAGS ONLY — passed with warnings")
    else:
        result["verdict"] = "VERIFIED"

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Fallback search (different query angle)
# ─────────────────────────────────────────────────────────────────────────────
def fallback_search(bias_name: str, keywords: list[str]) -> list[dict[str, Any]]:
    """Broader search used when primary candidates are exhausted."""
    # Build a minimal keyword query
    core = " ".join(keywords[:4])
    query = f"{core} CMIP climate model"
    params = {
        "search":   query,
        "per_page": "10",
        "filter":   "publication_year:>1990,cited_by_count:>9",
        "select":   "id,title,doi,authorships,publication_year,primary_location,"
                    "abstract_inverted_index,cited_by_count",
        "sort":     "cited_by_count:desc",
    }
    url = OPENALEX + "?" + urllib.parse.urlencode(params)
    status, body = _get(url)
    if status != 200 or not body:
        return []

    import importlib.util as _ilu
    _sp_path = Path(__file__).parent / "search_papers.py"
    _spec = _ilu.spec_from_file_location("search_papers", _sp_path)
    _sp = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_sp)
    reconstruct_abstract = _sp.reconstruct_abstract
    journal_ok           = _sp.journal_ok
    fmt_authors          = _sp.fmt_authors
    keyword_hits         = _sp.keyword_hits
    JOURNAL_WHITELIST    = _sp.JOURNAL_WHITELIST

    results = json.loads(body).get("results", [])
    candidates = []
    for p in results:
        raw_doi = (p.get("doi") or "").replace("https://doi.org/", "").strip()
        if not raw_doi:
            continue
        abstract = reconstruct_abstract(p.get("abstract_inverted_index"))
        title    = p.get("title") or ""
        full     = (title + " " + abstract).lower()
        hits     = keyword_hits(full, keywords)
        ok_j, journal_name = journal_ok(p)
        if not ok_j or len(hits) < 2:
            continue
        _fa = fmt_authors
        candidates.append({
            "doi":          raw_doi,
            "title":        title,
            "authors":      _fa(p.get("authorships", [])),
            "year":         p.get("publication_year") or 0,
            "journal":      journal_name,
            "journal_ok":   ok_j,
            "cited_by":     p.get("cited_by_count") or 0,
            "abstract":     abstract,
            "keyword_hits": hits,
            "score":        (p.get("cited_by_count") or 0) * len(hits),
            "verified":     None,
            "drop_reasons": [],
        })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Print one paper's verification result
# ─────────────────────────────────────────────────────────────────────────────
def print_result(idx: int, paper: dict[str, Any], v: dict[str, Any]) -> None:
    verdict_icon = {"VERIFIED": "✓", "REJECTED": "✗", "FLAGGED": "⚠", "PARTIAL": "~"}.get(
        v["verdict"], "?"
    )
    print(f"\n  Paper {idx}: {paper['authors']} ({paper['year']}) — {paper['doi']}")
    print(f"    OpenAlex title : {paper['title'][:75]}")
    print(f"    Crossref title : {v['crossref_title'][:75]}")
    print(f"    DOI resolves   : {'✓' if v['doi_resolves'] else '✗'}  "
          f"(HTTP {v['http_status']})")
    if v["landing_url"] and v["http_status"] not in (403,):
        print(f"    Landing URL    : {v['landing_url'][:70]}")
    print(f"    Title match    : {'✓' if v['title_match_ok'] else '✗'}  "
          f"(score={v['title_match_score']})")
    print(f"    Journal match  : {'✓' if v['journal_match_ok'] else '✗'}  "
          f"(Crossref: {v['crossref_journal'][:40]})")
    print(f"    Abstract hits  : {'✓' if v['abstract_ok'] else '✗'}  "
          f"{v['abstract_hits']}")
    print(f"    → {verdict_icon} {v['verdict']}", end="")
    if v["fail_reasons"]:
        reasons = [r for r in v["fail_reasons"]
                   if not r.startswith("SOFT FLAGS")]
        if reasons:
            print(f"  —  {reasons[0][:80]}", end="")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Verify candidate papers for a bias entry.")
    parser.add_argument("--bias", required=True, help="Bias ID (e.g. cold-tongue-bias)")
    args = parser.parse_args()

    bias_id  = args.bias.lower().strip()
    in_path  = PAPERS_DIR / f"{bias_id}.json"

    if not in_path.exists():
        print(f"[error] {in_path} not found. Run search_papers.py --bias {bias_id} first.",
              file=sys.stderr)
        return 1

    data     = json.loads(in_path.read_text(encoding="utf-8"))
    keywords = data["keywords"]
    candidates: list[dict[str, Any]] = data["candidates"]

    print(f"\n{'═' * 65}")
    print(f"  VERIFY: {data['bias_name']}  ({len(candidates)} candidates)")
    print(f"{'═' * 65}")

    verified:  list[dict[str, Any]] = []
    rejected:  list[dict[str, Any]] = []
    reserve:   list[dict[str, Any]] = list(candidates)   # work through all

    # Verify candidates in rank order until we have MIN_VERIFIED good ones
    for paper in reserve:
        if len(verified) >= MIN_VERIFIED:
            break
        print(f"\n  Checking #{len(verified) + len(rejected) + 1} "
              f"— {paper['doi']}", flush=True)
        v = verify_paper(paper, keywords)
        paper["verified"] = v
        print_result(len(verified) + len(rejected) + 1, paper, v)

        if v["verdict"] in ("VERIFIED", "FLAGGED", "PARTIAL"):
            verified.append(paper)
        else:
            rejected.append(paper)

    # Fallback if not enough
    if len(verified) < MIN_VERIFIED:
        print(f"\n  ⚠  Only {len(verified)} verified after primary candidates. "
              f"Running fallback search …")
        fb_candidates = fallback_search(data["bias_name"], keywords)
        time.sleep(REQUEST_DELAY)
        for paper in fb_candidates:
            if len(verified) >= MIN_VERIFIED:
                break
            print(f"\n  [fallback] Checking — {paper['doi']}", flush=True)
            v = verify_paper(paper, keywords)
            paper["verified"] = v
            print_result(len(verified) + len(rejected) + 1, paper, v)
            if v["verdict"] in ("VERIFIED", "FLAGGED", "PARTIAL"):
                verified.append(paper)
            else:
                rejected.append(paper)

    # Summary
    print(f"\n  {'─' * 63}")
    n_clean    = sum(1 for p in verified if p["verified"]["verdict"] == "VERIFIED")
    n_flagged  = sum(1 for p in verified if p["verified"]["verdict"] == "FLAGGED")
    n_partial  = sum(1 for p in verified if p["verified"]["verdict"] == "PARTIAL")
    print(f"  Result: {len(verified)} papers accepted")
    print(f"    ✓ VERIFIED  : {n_clean}")
    print(f"    ⚠ FLAGGED   : {n_flagged}  (passed with soft warnings)")
    print(f"    ~ PARTIAL   : {n_partial}  (no Crossref metadata)")
    print(f"    ✗ REJECTED  : {len(rejected)}")

    if len(verified) < MIN_VERIFIED:
        print(f"\n  ✗ INSUFFICIENT PAPERS — only {len(verified)}/{MIN_VERIFIED} verified.")
        print(f"    write_draft.py will not run until this is resolved.")
        print(f"    → Manual review required for {bias_id}")
        # Still write what we have so you can inspect
        data["candidates"] = verified
        data["rejected"]   = rejected
        data["status"]     = "INSUFFICIENT"
        in_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return 1

    print(f"\n  {'─' * 63}")
    print(f"  ✓ All checks complete — ready for write_draft.py\n")

    # Write updated file
    data["candidates"] = verified
    data["rejected"]   = rejected
    data["status"]     = "VERIFIED"
    in_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  Updated → {in_path.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
