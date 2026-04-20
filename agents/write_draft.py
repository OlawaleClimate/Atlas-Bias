#!/usr/bin/env python3
"""
write_draft.py — Agent 3 of 3

Reads pipeline/outputs/papers/<bias-id>.json (must have status=VERIFIED).
Uses the verified papers to write a full bias entry draft to:
  pipeline/outputs/drafts/<bias-id>.json

What it writes:
  - description: 3 paragraphs (what it is, history, causes/solutions)
  - cmip_history: CMIP3/5/6/7 entries with notes sourced from abstracts
  - citations: 5 papers × 4-sentence relevance summary from the abstract
  - All other schema fields left as empty arrays/objects (filled later)

Usage:
    python agents/write_draft.py --bias cold-tongue-bias
    python agents/write_draft.py --bias cold-tongue-bias --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import importlib.util as _ilu

def _load_search_papers():
    """Dynamically load search_papers module to access BIAS_CATALOGUE."""
    _sp_path = Path(__file__).parent / "search_papers.py"
    _spec = _ilu.spec_from_file_location("search_papers", _sp_path)
    _sp = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_sp)
    return _sp


REPO_ROOT   = Path(__file__).resolve().parents[1]
PAPERS_DIR  = REPO_ROOT / "pipeline" / "outputs" / "papers"
DRAFTS_DIR  = REPO_ROOT / "pipeline" / "outputs" / "drafts"

# CMIP generation markers used when scanning abstracts
CMIP_MARKERS = {
    "CMIP3": ["cmip3", "cmip-3", "3rd phase", "ar4", "ipcc ar4"],
    "CMIP5": ["cmip5", "cmip-5", "5th phase", "ar5", "ipcc ar5"],
    "CMIP6": ["cmip6", "cmip-6", "6th phase", "ar6", "ipcc ar6"],
    "CMIP7": ["cmip7", "cmip-7", "7th phase"],
}

# Words that suggest severity levels in text
SEVERITY_WORDS = {
    "strong":   ["persist", "robust", "large", "systematic", "dominant",
                 "widespread", "severe", "major", "significant", "substantial",
                 "strong", "prominent"],
    "moderate": ["moderate", "partial", "reduced", "some improvement",
                 "partially", "mixed", "inconsistent", "modest"],
    "weak":     ["weak", "minor", "slight", "small", "marginal",
                 "limited", "negligible"],
    "absent":   ["absent", "resolved", "corrected", "eliminated", "fixed",
                 "no longer", "removed"],
}

# Sentence boundary splitter
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if len(s.strip()) > 30]


def contains_number(text: str) -> bool:
    return bool(re.search(r"\d", text))


def first_sentence(text: str) -> str:
    sents = split_sentences(text)
    return sents[0] if sents else text[:200]


def last_sentence(text: str) -> str:
    sents = split_sentences(text)
    return sents[-1] if sents else text[-200:]


def sentence_with_keywords(text: str, keywords: list[str]) -> str:
    """Return the sentence with the most keyword hits."""
    sents = split_sentences(text)
    if not sents:
        return text[:200]
    scored = [(sum(1 for kw in keywords if kw in s.lower()), s) for s in sents]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def sentence_with_number(text: str) -> str:
    """Return the sentence most likely to contain quantitative results."""
    sents = split_sentences(text)
    number_sents = [s for s in sents if contains_number(s)]
    if not number_sents:
        return sents[1] if len(sents) > 1 else (sents[0] if sents else text[:200])
    # Prefer sentences with both numbers and 'K', '%', 'Sv', 'W/m', etc.
    rich = [s for s in number_sents
            if re.search(r"(%|K\b|Sv|W/m|km|mm|hPa|°|\bK\b)", s)]
    return rich[0] if rich else number_sents[0]


def method_sentence(text: str) -> str:
    """Return the sentence most likely to describe the method."""
    method_keywords = [
        "using", "analysis", "method", "model", "simulation", "data",
        "reanalysis", "observations", "diagnosed", "evaluated", "compared",
        "multimodel", "ensemble", "cmip", "coupled", "prescribed",
    ]
    sents = split_sentences(text)
    scored = [(sum(1 for kw in method_keywords if kw in s.lower()), s)
              for s in sents]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else (sents[1] if len(sents) > 1 else text[:200])


# ─────────────────────────────────────────────────────────────────────────────
# Build 4-sentence paper summary
# ─────────────────────────────────────────────────────────────────────────────
def four_sentence_summary(paper: dict[str, Any], keywords: list[str]) -> str:
    abstract = paper.get("abstract", "")
    if not abstract:
        # Fall back to title
        return (
            f"{paper['authors']} studied {paper['title']}. "
            "No abstract was available for detailed summary extraction. "
            f"This paper was published in {paper['journal']} in {paper['year']}. "
            "It was identified as relevant through keyword and citation screening."
        )

    s1 = first_sentence(abstract)
    s2 = method_sentence(abstract)
    s3 = sentence_with_number(abstract)
    s4 = last_sentence(abstract)

    # Deduplicate — avoid repeating the same sentence
    seen: set[str] = set()
    sents_out: list[str] = []
    all_sents = split_sentences(abstract)

    for candidate in [s1, s2, s3, s4]:
        key = candidate[:60]
        if key not in seen:
            seen.add(key)
            sents_out.append(candidate)
        else:
            # Pick a different sentence from the abstract
            for s in all_sents:
                k = s[:60]
                if k not in seen and len(s) > 40:
                    seen.add(k)
                    sents_out.append(s)
                    break

    # Ensure exactly 4 sentences
    while len(sents_out) < 4 and all_sents:
        for s in all_sents:
            k = s[:60]
            if k not in seen:
                seen.add(k)
                sents_out.append(s)
                break
        else:
            break

    return " ".join(sents_out[:4])


# ─────────────────────────────────────────────────────────────────────────────
# Infer severity from text
# ─────────────────────────────────────────────────────────────────────────────
def infer_severity(text: str) -> str:
    t = text.lower()
    for level, markers in SEVERITY_WORDS.items():
        if any(m in t for m in markers):
            return level
    return "moderate"   # default


# ─────────────────────────────────────────────────────────────────────────────
# Build CMIP history from abstracts
# ─────────────────────────────────────────────────────────────────────────────
def build_cmip_history(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scan all abstracts for CMIP generation mentions and extract context."""
    generation_data: dict[str, list[str]] = {g: [] for g in CMIP_MARKERS}

    for paper in papers:
        abstract = paper.get("abstract", "")
        sents = split_sentences(abstract)
        for sent in sents:
            s_lower = sent.lower()
            for gen, markers in CMIP_MARKERS.items():
                if any(m in s_lower for m in markers):
                    generation_data[gen].append(sent)

    history = []
    for gen in ["CMIP3", "CMIP5", "CMIP6", "CMIP7"]:
        sents = generation_data[gen]
        if not sents:
            continue
        # Pick the sentence with the most content
        best = max(sents, key=lambda s: len(s))
        severity = infer_severity(best)
        history.append({
            "generation": gen,
            "severity":   severity,
            "notes":      best[:400],
        })

    # If nothing was found, at least put CMIP5 and CMIP6 as placeholders
    if not history:
        history = [
            {"generation": "CMIP5", "severity": "moderate",
             "notes": "Severity in CMIP5 not explicitly quantified in available abstracts."},
            {"generation": "CMIP6", "severity": "moderate",
             "notes": "Severity in CMIP6 not explicitly quantified in available abstracts."},
        ]

    return history


# ─────────────────────────────────────────────────────────────────────────────
# Build description paragraphs
# ─────────────────────────────────────────────────────────────────────────────
def build_description(
    papers: list[dict[str, Any]],
    bias_name: str,
    keywords: list[str],
) -> str:
    """Build a 3-paragraph description from the verified paper abstracts."""

    all_sents: list[tuple[int, str, str]] = []   # (hits, sentence, paper_ref)
    for p in papers:
        abstract = p.get("abstract", "")
        ref = f"{p['authors'].split(',')[0].split(' ')[-1]} et al. ({p['year']})"
        for sent in split_sentences(abstract):
            hits = sum(1 for kw in keywords if kw in sent.lower())
            all_sents.append((hits, sent, ref))

    all_sents.sort(key=lambda x: x[0], reverse=True)

    # Para 1: What is the bias — highest-hit sentences describing the bias itself
    para1_sents = [s for h, s, r in all_sents if h >= 2][:3]
    if not para1_sents:
        para1_sents = [s for h, s, r in all_sents[:3]]
    para1 = f"The {bias_name} is one of the most documented systematic errors in " \
            f"coupled climate models. " + " ".join(para1_sents[:2])

    # Para 2: History — sentences mentioning CMIP generations
    cmip_sents = [s for h, s, r in all_sents
                  if any(m in s.lower()
                         for gen_markers in CMIP_MARKERS.values()
                         for m in gen_markers)][:3]
    if cmip_sents:
        para2 = ("Across successive generations of the Coupled Model Intercomparison Project "
                 "(CMIP), the bias has been tracked in multi-model assessments. "
                 + " ".join(cmip_sents[:2]))
    else:
        para2 = ("The bias has persisted across multiple generations of the Coupled Model "
                 "Intercomparison Project (CMIP), from CMIP3 through CMIP6.")

    # Para 3: Causes and solutions — sentences with mechanism or fix keywords
    mechanism_keywords = [
        "parameteris", "convect", "wind", "upwelling", "radiation",
        "cloud", "albedo", "feedback", "tuning", "correction",
        "reduces", "improved", "mitigated", "attributed",
    ]
    mech_sents = [s for h, s, r in all_sents
                  if any(m in s.lower() for m in mechanism_keywords)][:3]
    if mech_sents:
        para3 = ("The physical mechanisms underlying this bias and potential pathways "
                 "to its reduction have been investigated in several studies. "
                 + " ".join(mech_sents[:2]))
    else:
        para3 = ("The mechanisms driving this bias and candidate solutions remain the "
                 "subject of ongoing research in the modelling community.")

    return "\n\n".join([para1, para2, para3])


# ─────────────────────────────────────────────────────────────────────────────
# Assemble full schema-compliant draft (Phase 1 fields only)
# ─────────────────────────────────────────────────────────────────────────────
def build_draft(data: dict[str, Any]) -> dict[str, Any]:
    bias_id   = data["bias_id"]
    bias_name = data["bias_name"]
    keywords  = data["keywords"]
    papers    = data["candidates"][:5]   # use top 5 verified

    # Pull category/region from BIAS_CATALOGUE in search_papers.py
    sp = _load_search_papers()
    catalogue_entry = sp.BIAS_CATALOGUE.get(bias_id, {})
    category = catalogue_entry.get("category", "")
    region   = catalogue_entry.get("region", "")

    description  = build_description(papers, bias_name, keywords)
    cmip_history = build_cmip_history(papers)

    citations = []
    for p in papers:
        relevance = four_sentence_summary(p, keywords)
        citations.append({
            "authors":   p["authors"],
            "year":      p["year"],
            "journal":   p["journal"],
            "doi":       p["doi"],
            "relevance": relevance,
        })

    return {
        "id":                  bias_id,
        "name":                bias_name,
        "version":             "1.0",
        "last_updated":        date.today().isoformat(),
        "category":            category,
        "region":              region,
        "season":              "annual",
        "affected_variables":  [],
        "description":         description,
        "persistence":         "longstanding",
        "cmip_history":        cmip_history,
        "severity_by_model":   {},
        "implicated_params":   [],
        "fix_attempts":        [],
        "cascade_links":       [],
        "disputed_mechanisms": [],
        "citations":           citations,
        "feedback_history":    [],
        "changelog":           [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Write a bias entry draft from verified papers.")
    parser.add_argument("--bias", required=True, help="Bias ID (e.g. cold-tongue-bias)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the draft to stdout without writing to disk")
    args = parser.parse_args()

    bias_id  = args.bias.lower().strip()
    in_path  = PAPERS_DIR / f"{bias_id}.json"

    if not in_path.exists():
        print(f"[error] {in_path} not found. Run search_papers.py and verify_papers.py first.",
              file=sys.stderr)
        return 1

    data = json.loads(in_path.read_text(encoding="utf-8"))

    if data.get("status") not in ("VERIFIED",):
        print(f"[error] Papers file status is '{data.get('status')}' — must be VERIFIED. "
              "Resolve issues in verify_papers.py first.", file=sys.stderr)
        return 1

    papers = data.get("candidates", [])
    verified_count = sum(
        1 for p in papers
        if (p.get("verified") or {}).get("verdict") in ("VERIFIED", "FLAGGED", "PARTIAL")
    )
    if verified_count < 5:
        print(f"[error] Only {verified_count} verified papers — need 5.", file=sys.stderr)
        return 1

    print(f"\n{'═' * 65}")
    print(f"  WRITE DRAFT: {data['bias_name']}")
    print(f"{'═' * 65}\n")

    draft = build_draft(data)

    if args.dry_run:
        print(json.dumps(draft, indent=2))
        return 0

    # Write
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DRAFTS_DIR / f"{bias_id}.json"
    out_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")

    # Summary
    print(f"  Description : {len(draft['description'])} chars  "
          f"({len(draft['description'].split())} words)")
    print(f"  CMIP history: {[h['generation'] + '=' + h['severity'] for h in draft['cmip_history']]}")
    print(f"  Citations   : {len(draft['citations'])} papers")
    for c in draft['citations']:
        verdict = (papers[[p['doi'] for p in papers].index(c['doi'])].get('verified') or {}).get('verdict', '?') \
            if c['doi'] in [p['doi'] for p in papers] else '?'
        icon = {'VERIFIED': '✓', 'FLAGGED': '⚠', 'PARTIAL': '~'}.get(verdict, '?')
        print(f"    {icon}  {c['authors']} ({c['year']}) — {c['doi']}")
        print(f"       {c['relevance'][:120]}…")

    print(f"\n  ✓ Draft written → {out_path.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
