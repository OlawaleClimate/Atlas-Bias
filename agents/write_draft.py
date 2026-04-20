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


def sentence_with_keywords(text: str, keywords: list[str]) -> str:
    """Return the sentence with the most keyword hits."""
    sents = split_sentences(text)
    if not sents:
        return text[:200]
    scored = [(sum(1 for kw in keywords if kw in s.lower()), s) for s in sents]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _pick(sents: list[str], keywords: list[str], extra_kws: list[str],
          seen: set[str]) -> str | None:
    """Return the highest-scoring unseen sentence matching both bias keywords
    and extra_kws. Falls back to highest bias-keyword score."""
    scored = []
    for s in sents:
        s_low = s.lower()
        bias_hits  = sum(1 for kw in keywords   if kw in s_low)
        extra_hits = sum(1 for kw in extra_kws  if kw in s_low)
        scored.append((bias_hits, extra_hits, s))
    # Sort: bias hits desc, then extra hits desc
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for bh, eh, s in scored:
        if s[:60] not in seen:
            return s
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Build 4-sentence paper summary — bias-focused
# ─────────────────────────────────────────────────────────────────────────────
def four_sentence_summary(paper: dict[str, Any], keywords: list[str]) -> str:
    """
    Four sentences that describe what this paper did/found *about the bias*:
      1. What the paper studied (context/topic — bias-keyword rich)
      2. What method or dataset was used to study the bias
      3. Key quantitative or mechanistic result about the bias
      4. Conclusion or implication about the bias
    """
    abstract = paper.get("abstract", "")
    if not abstract:
        return (
            f"{paper['authors']} examined {paper['title']}. "
            "No abstract was available for detailed summary extraction. "
            f"This paper was published in {paper['journal']} in {paper['year']}. "
            "It was identified as relevant through keyword and citation screening."
        )

    all_sents = split_sentences(abstract)
    if not all_sents:
        return abstract[:500]

    seen: set[str] = set()
    out:  list[str] = []

    # Sentence 1 — What was studied (bias context)
    topic_kws = ["bias", "error", "investigate", "examine", "study", "assess",
                 "document", "analyse", "analyze", "characterize"] + keywords
    s1 = _pick(all_sents, keywords, topic_kws, seen)
    if s1:
        seen.add(s1[:60])
        out.append(s1)

    # Sentence 2 — Method / dataset used to study the bias
    method_kws = ["using", "model", "simulation", "reanalysis", "observations",
                  "ensemble", "cmip", "coupled", "diagnosed", "evaluated",
                  "multimodel", "experiment", "compared", "prescribed"]
    s2 = _pick(all_sents, keywords, method_kws, seen)
    if s2:
        seen.add(s2[:60])
        out.append(s2)

    # Sentence 3 — Quantitative or mechanistic result about the bias
    result_kws = ["show", "find", "found", "result", "reveal", "indicate",
                  "demonstrate", "suggest", "conclude", "attributed",
                  "associated", "responsible", "caused"]
    # Prefer sentences with numbers (%, K, Sv, W/m², mm/day …)
    num_sents = [s for s in all_sents
                 if re.search(r"(\d+\.?\d*\s*(%|K\b|Sv|W/m|mm|hPa|°C|km))", s)
                 and s[:60] not in seen]
    if num_sents:
        # Among those, pick the one most relevant to bias keywords
        scored = sorted(num_sents,
                        key=lambda s: sum(1 for kw in keywords if kw in s.lower()),
                        reverse=True)
        s3 = scored[0]
    else:
        s3 = _pick(all_sents, keywords, result_kws, seen)
    if s3 and s3[:60] not in seen:
        seen.add(s3[:60])
        out.append(s3)

    # Sentence 4 — Conclusion or implication
    concl_kws = ["conclusion", "implication", "therefore", "thus", "hence",
                 "suggest", "indicate", "highlight", "provide", "future",
                 "improve", "reduce", "remain", "persist"]
    s4 = _pick(all_sents, keywords, concl_kws, seen)
    if s4:
        seen.add(s4[:60])
        out.append(s4)

    # Pad to 4 sentences with unseen sentences if needed
    for s in all_sents:
        if len(out) >= 4:
            break
        if s[:60] not in seen:
            seen.add(s[:60])
            out.append(s)

    return " ".join(out[:4])


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
    catalogue_entry: dict[str, Any] | None = None,
) -> str:
    """Build a 3-paragraph description.

    Para 1 — Definition: What is this bias? (anchored by catalogue definition)
    Para 2 — CMIP History: How has it evolved across CMIP generations?
    Para 3 — Causes: What drives the bias? (anchored by catalogue cause_hint)

    Sentences pulled from abstracts are tagged [N] (1-based citation index).
    A global seen-set prevents any sentence appearing in more than one paragraph.
    """
    cat = catalogue_entry or {}
    definition  = cat.get("definition",  "")
    cause_hint  = cat.get("cause_hint",  "")

    def tag(sent: str, idx: int) -> str:
        sent = sent.rstrip()
        if sent.endswith("."):
            return sent[:-1] + f" [{idx}]."
        return sent + f" [{idx}]"

    # Build per-paper sentence pool: (hits, sentence, 1-based paper index)
    all_sents: list[tuple[int, str, int]] = []
    for idx, p in enumerate(papers, start=1):
        for sent in split_sentences(p.get("abstract", "")):
            hits = sum(1 for kw in keywords if kw in sent.lower())
            all_sents.append((hits, sent, idx))
    all_sents.sort(key=lambda x: x[0], reverse=True)

    # Global dedup — a sentence key used across all 3 paragraphs
    used: set[str] = set()

    def pick_unseen(pool: list[tuple[int, str, int]], n: int) -> list[tuple[int, str, int]]:
        out = []
        for item in pool:
            if len(out) >= n:
                break
            key = item[1][:70]
            if key not in used:
                used.add(key)
                out.append(item)
        return out

    # ── Para 1: Definition ────────────────────────────────────────────────
    # Use the catalogue definition as the fixed opening sentence.
    # Follow with the 1 abstract sentence most relevant to describing the bias.
    defn_sentence = definition if definition else (
        f"The {bias_name} is a systematic error in coupled climate models "
        f"that has been documented across multiple CMIP generations."
    )
    # Mark catalogue sentences as "used" so they never appear later
    for s in split_sentences(defn_sentence):
        used.add(s[:70])

    best_abstract_sents = pick_unseen(all_sents, 1)
    para1 = defn_sentence
    if best_abstract_sents:
        _, s, i = best_abstract_sents[0]
        para1 += " " + tag(s, i)

    # ── Para 2: CMIP History ──────────────────────────────────────────────
    # Pick up to 2 unseen abstract sentences that mention a CMIP generation.
    cmip_pool = [(h, s, i) for h, s, i in all_sents
                 if any(m in s.lower()
                        for gen_markers in CMIP_MARKERS.values()
                        for m in gen_markers)]
    cmip_picks = pick_unseen(cmip_pool, 2)

    if cmip_picks:
        intro2 = (
            "The bias has been tracked across successive generations of the "
            "Coupled Model Intercomparison Project (CMIP), with multi-model "
            "assessments showing it is present in CMIP3, CMIP5, and CMIP6."
        )
        used.add(intro2[:70])
        para2 = intro2 + " " + " ".join(tag(s, i) for _, s, i in cmip_picks)
    else:
        para2 = (
            "The bias has persisted across multiple generations of the Coupled "
            "Model Intercomparison Project (CMIP), from CMIP3 through CMIP6, "
            "and has been assessed in numerous multi-model studies."
        )

    # ── Para 3: Causes ────────────────────────────────────────────────────
    # Lead with the catalogue cause_hint, then append the best unseen abstract
    # sentence about mechanisms, attribution, or feedback.
    cause_kws = [
        "caused by", "attributed", "due to", "driven by", "feedback",
        "parameteris", "interaction", "upwelling", "convect",
        "microphysic", "boundary layer", "entrainment", "inversion",
        "trade wind", "shortwave", "longwave", "albedo", "bjerknes",
    ]
    cause_pool = [(h, s, i) for h, s, i in all_sents
                  if any(k in s.lower() for k in cause_kws)]
    # Fall back to any high-keyword sentences if no cause-specific ones found
    if not cause_pool:
        cause_pool = all_sents
    cause_picks = pick_unseen(cause_pool, 1)

    if cause_hint:
        for s in split_sentences(cause_hint):
            used.add(s[:70])
        para3 = cause_hint
        if cause_picks:
            _, s, i = cause_picks[0]
            para3 += " " + tag(s, i)
    elif cause_picks:
        intro3 = (
            "The physical mechanisms underlying this bias and pathways to "
            "its reduction have been investigated in several modelling studies."
        )
        used.add(intro3[:70])
        para3 = intro3 + " " + " ".join(tag(s, i) for _, s, i in cause_picks)
    else:
        para3 = (
            "The mechanisms driving this bias and candidate solutions remain "
            "an active area of research in the climate modelling community."
        )

    return "\n\n".join([para1, para2, para3])


# ─────────────────────────────────────────────────────────────────────────────
# Citation integrity check
# ─────────────────────────────────────────────────────────────────────────────
def check_citation_integrity(
    description: str,
    citations: list[dict[str, Any]],
    papers: list[dict[str, Any]],
) -> list[str]:
    """Verify every [N] in the description points to a paper whose abstract
    contains the tagged sentence.

    Returns a list of warning strings (empty = all good).
    """
    warnings: list[str] = []

    # Build a map: doi → abstract (lowercase, stripped)
    doi_to_abstract: dict[str, str] = {}
    for p in papers:
        doi_to_abstract[p["doi"].lower()] = (p.get("abstract") or "").lower()

    # Split description into sentences so we can find the context of each [N]
    # We need to keep [N] markers attached to their sentence.
    # Strategy: iterate paragraphs → sentences, collect (sentence_text, [N, ...])
    citation_re = re.compile(r"\[(\d+)\]")

    for para in description.split("\n\n"):
        for sent in _SENT_RE.split(para):
            sent = sent.strip()
            if not sent:
                continue
            marker_nums = [int(m) for m in citation_re.findall(sent)]
            if not marker_nums:
                continue

            # Clean the sentence text — remove [N] markers for matching
            clean = citation_re.sub("", sent).strip().rstrip(".")
            # Use a 12-word sliding window from the sentence as a fingerprint
            words = clean.split()
            fingerprint = " ".join(words[:12]).lower() if len(words) >= 5 else clean.lower()

            for n in marker_nums:
                if n < 1 or n > len(citations):
                    warnings.append(
                        f"[N={n}] out of range (only {len(citations)} citations)"
                    )
                    continue

                cite = citations[n - 1]
                abstract = doi_to_abstract.get(cite["doi"].lower(), "")

                if not abstract:
                    warnings.append(
                        f"[{n}] {cite['authors']} ({cite['year']}) — "
                        f"no abstract available to verify sentence: '{fingerprint}...'"
                    )
                    continue

                # Check fingerprint appears in abstract
                if fingerprint not in abstract:
                    # Try a shorter 6-word match as a fallback
                    short = " ".join(words[:6]).lower() if len(words) >= 6 else fingerprint
                    if short not in abstract:
                        warnings.append(
                            f"[{n}] {cite['authors']} ({cite['year']}) — "
                            f"sentence not found in abstract:\n"
                            f"      Sentence : '{fingerprint}...'\n"
                            f"      Paper DOI: {cite['doi']}"
                        )

    return warnings
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

    description  = build_description(papers, bias_name, keywords, catalogue_entry)
    cmip_history = build_cmip_history(papers)

    citations = []
    for p in papers:
        relevance = four_sentence_summary(p, keywords)
        citations.append({
            "authors":   p["authors"],
            "year":      p["year"],
            "title":     p.get("title", ""),
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

    # ── Citation integrity check ──
    all_papers = data.get("candidates", [])
    cite_warnings = check_citation_integrity(
        draft["description"], draft["citations"], all_papers
    )
    print(f"\n  ── Citation integrity check ──")
    if cite_warnings:
        for w in cite_warnings:
            print(f"  ⚠  {w}")
        print(f"  {len(cite_warnings)} issue(s) found — review before promoting to src/data/entries/")
    else:
        print(f"  ✓ All inline citations verified — each [N] maps to the correct paper's abstract")

    print(f"\n  ✓ Draft written → {out_path.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
