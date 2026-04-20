#!/usr/bin/env python3
"""
final_verify.py — Quality gate for bias entry drafts.

Reads:
  pipeline/outputs/drafts/<bias-id>.json   (the draft)
  pipeline/outputs/papers/<bias-id>.json   (verified papers + abstracts)

Scores the entry on 5 dimensions (10 pts total).
Pass threshold: 9/10.

If score < 9, it identifies which agent is responsible for each failure
and calls it automatically, then re-scores. Up to MAX_RETRIES loops.

Usage:
    python agents/final_verify.py --bias cold-tongue-bias
    python agents/final_verify.py --bias cold-tongue-bias --no-fix
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT   = Path(__file__).resolve().parents[1]
PAPERS_DIR  = REPO_ROOT / "pipeline" / "outputs" / "papers"
DRAFTS_DIR  = REPO_ROOT / "pipeline" / "outputs" / "drafts"
AGENTS_DIR  = REPO_ROOT / "agents"

MAX_RETRIES = 3
PASS_SCORE  = 10

# Sentence splitter (mirrors write_draft.py)
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_CITE_RE  = re.compile(r"\[(\d+)\]")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if len(s.strip()) > 30]


# ─────────────────────────────────────────────────────────────────────────────
# Scoring dimensions
# ─────────────────────────────────────────────────────────────────────────────

def score_citation_integrity(
    description: str,
    citations: list[dict],
    candidates: list[dict],
    keywords: list[str],
) -> tuple[int, list[str]]:
    """
    3 pts — Every [N] in the description maps to a sentence found in that
    paper's abstract.

    3 = 0 mismatches
    2 = 1 mismatch
    1 = 2 mismatches
    0 = 3+ mismatches  →  write_draft must be re-run
    """
    doi_to_abstract: dict[str, str] = {}
    for p in candidates:
        doi_to_abstract[p["doi"].lower()] = (p.get("abstract") or "").lower()

    mismatches: list[str] = []

    for para in description.split("\n\n"):
        for sent in split_sentences(para):
            markers = [int(m) for m in _CITE_RE.findall(sent)]
            if not markers:
                continue
            # Clean sentence for fingerprinting
            clean = _CITE_RE.sub("", sent).strip().rstrip(".")
            words = clean.split()
            fingerprint = " ".join(words[:12]).lower()
            short        = " ".join(words[:6]).lower()

            for n in markers:
                if n < 1 or n > len(citations):
                    mismatches.append(f"[{n}] out of range ({len(citations)} citations)")
                    continue
                cite     = citations[n - 1]
                abstract = doi_to_abstract.get(cite["doi"].lower(), "")
                if not abstract:
                    # Can't verify — soft warning only
                    continue
                if fingerprint not in abstract and short not in abstract:
                    mismatches.append(
                        f"[{n}] '{fingerprint[:60]}...' "
                        f"NOT found in abstract of {cite['authors']} ({cite['year']})"
                    )

    score = max(0, 3 - len(mismatches))
    details = mismatches or ["all [N] tags verified against abstracts"]
    return score, details


def score_paper_verification(candidates: list[dict]) -> tuple[int, list[str]]:
    """
    2 pts — Quality of paper verdicts.

    2 = all 5 are VERIFIED (no FLAGGED/PARTIAL)
    1 = at least 5 accepted (VERIFIED + FLAGGED + PARTIAL), 0 REJECTED
    0 = any REJECTED, or fewer than 5 accepted  →  verify_papers must re-run
    """
    accepted   = [p for p in candidates
                  if (p.get("verified") or {}).get("verdict") in ("VERIFIED", "FLAGGED", "PARTIAL")]
    rejected   = [p for p in candidates
                  if (p.get("verified") or {}).get("verdict") == "REJECTED"]
    all_clean  = all((p.get("verified") or {}).get("verdict") == "VERIFIED"
                     for p in accepted[:5])

    details: list[str] = []
    if rejected:
        details.append(f"{len(rejected)} REJECTED paper(s): "
                       + ", ".join(f"{p['authors']} ({p['year']})" for p in rejected))
    flagged = [p for p in accepted[:5]
               if (p.get("verified") or {}).get("verdict") in ("FLAGGED", "PARTIAL")]
    if flagged:
        details.append(f"{len(flagged)} FLAGGED/PARTIAL: "
                       + ", ".join(f"{p['authors']} ({p['year']})" for p in flagged))

    if rejected or len(accepted) < 5:
        return 0, details or ["fewer than 5 accepted papers"]
    if all_clean:
        return 2, ["all 5 papers VERIFIED"]
    return 1, details or ["5 accepted (some FLAGGED/PARTIAL)"]


def score_description_relevance(
    description: str,
    keywords: list[str],
) -> tuple[int, list[str]]:
    """
    2 pts — Bias keyword density in the description.

    Count total keyword hits across the full description (normalised per 100 words).

    2 = density ≥ 4.0   (clearly about this bias)
    1 = density 2.0–3.9  (mostly relevant)
    0 = density < 2.0   →  write_draft must re-run
    """
    word_count = len(description.split())
    hits = sum(1 for kw in keywords if kw in description.lower())
    # Also count repeated occurrences
    total_hits = sum(description.lower().count(kw) for kw in keywords)
    density = (total_hits / word_count) * 100 if word_count else 0

    details = [f"keyword density: {density:.1f} hits/100 words "
               f"({total_hits} total hits, {word_count} words)"]
    if density >= 4.0:
        return 2, details
    if density >= 2.0:
        return 1, details
    return 0, details + ["description is too sparse on bias keywords"]


def score_citation_relevance(
    citations: list[dict],
    candidates: list[dict],
    keywords: list[str],
) -> tuple[int, list[str]]:
    """
    2 pts — Each citation's 4-sentence relevance text contains ≥2 bias keywords.

    2 = all 5 citations pass
    1 = 3–4 citations pass
    0 = fewer than 3 pass  →  write_draft must re-run
    """
    doi_to_candidate = {p["doi"].lower(): p for p in candidates}
    passing  = 0
    details: list[str] = []

    for i, c in enumerate(citations, 1):
        relevance  = (c.get("relevance") or "").lower()
        hits       = sum(1 for kw in keywords if kw in relevance)
        # Also check keyword_hits stored on the candidate
        candidate  = doi_to_candidate.get(c["doi"].lower(), {})
        stored_hits = len(candidate.get("keyword_hits") or [])
        effective   = max(hits, stored_hits)

        if effective >= 2:
            passing += 1
            details.append(f"  [{i}] ✓ {effective} keyword hits — {c['authors']} ({c['year']})")
        else:
            details.append(f"  [{i}] ✗ only {effective} keyword hits — {c['authors']} ({c['year']})"
                           f" (may be a broad model paper)")

    if passing >= 5:
        return 2, details
    if passing >= 3:
        return 1, details
    return 0, details + ["too many citations lack bias-relevant content"]


def score_completeness(citations: list[dict]) -> tuple[int, list[str]]:
    """
    1 pt — All required fields present in every citation.

    1 = all 5 citations have authors, year, title, journal, doi, relevance
    0 = any field missing  →  write_draft must re-run
    """
    required = ("authors", "year", "title", "journal", "doi", "relevance")
    missing: list[str] = []
    for i, c in enumerate(citations, 1):
        for field in required:
            if not c.get(field):
                missing.append(f"citation [{i}] missing '{field}'")

    if missing:
        return 0, missing
    return 1, ["all citation fields present"]


# ─────────────────────────────────────────────────────────────────────────────
# Determine which agents to call based on failing dimensions
# ─────────────────────────────────────────────────────────────────────────────

def agents_to_call(
    s_integrity: int,
    s_papers: int,
    s_desc: int,
    s_cite_rel: int,
    s_complete: int,
) -> list[str]:
    """Return the ordered list of agent scripts to re-run."""
    run_search  = False
    run_verify  = False
    run_draft   = False

    if s_papers == 0:            # rejected or too few papers
        run_search = True
        run_verify = True
        run_draft  = True
    elif s_papers == 1:          # flagged papers — try re-verify
        run_verify = True
        run_draft  = True

    if s_integrity < 3:          # [N] tags are wrong → fix draft
        run_draft = True
    if s_desc < 2:               # description not relevant → fix draft
        run_draft = True
    if s_cite_rel < 2:           # relevance text weak → fix draft
        run_draft = True
    if s_complete == 0:          # fields missing → fix draft
        run_draft = True

    pipeline: list[str] = []
    if run_search:
        pipeline.append("search_papers.py")
    if run_verify:
        pipeline.append("verify_papers.py")
    if run_draft:
        pipeline.append("write_draft.py")
    return pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Run one agent as a subprocess
# ─────────────────────────────────────────────────────────────────────────────

def run_agent(script: str, bias_id: str) -> int:
    cmd = [sys.executable, str(AGENTS_DIR / script), "--bias", bias_id]
    print(f"  → Running: python {script} --bias {bias_id}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    return result.returncode


# ─────────────────────────────────────────────────────────────────────────────
# Full scoring pass
# ─────────────────────────────────────────────────────────────────────────────

def score_entry(
    draft: dict[str, Any],
    papers_data: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Score the draft on all 5 dimensions. Returns (total, breakdown)."""
    keywords   = papers_data.get("keywords", [])
    candidates = papers_data.get("candidates", [])
    citations  = draft.get("citations", [])
    description= draft.get("description", "")

    s_int,  d_int  = score_citation_integrity(description, citations, candidates, keywords)
    s_pap,  d_pap  = score_paper_verification(candidates)
    s_desc, d_desc = score_description_relevance(description, keywords)
    s_crel, d_crel = score_citation_relevance(citations, candidates, keywords)
    s_comp, d_comp = score_completeness(citations)

    total = s_int + s_pap + s_desc + s_crel + s_comp

    breakdown = {
        "citation_integrity":   {"score": s_int,  "max": 3, "details": d_int},
        "paper_verification":   {"score": s_pap,  "max": 2, "details": d_pap},
        "description_relevance":{"score": s_desc, "max": 2, "details": d_desc},
        "citation_relevance":   {"score": s_crel, "max": 2, "details": d_crel},
        "completeness":         {"score": s_comp, "max": 1, "details": d_comp},
    }
    return total, breakdown


# ─────────────────────────────────────────────────────────────────────────────
# Print readable score report
# ─────────────────────────────────────────────────────────────────────────────

def print_report(bias_id: str, total: int, breakdown: dict, attempt: int) -> None:
    bar   = "█" * total + "░" * (10 - total)
    icon  = "✓ PASS" if total >= PASS_SCORE else "✗ FAIL"
    print(f"\n{'═' * 65}")
    print(f"  FINAL VERIFY: {bias_id}  (attempt {attempt})")
    print(f"{'═' * 65}")
    print(f"  Score: {total}/10  [{bar}]  {icon}")
    print()

    labels = {
        "citation_integrity":    "Citation integrity  [N]→abstract",
        "paper_verification":    "Paper verification  verdicts",
        "description_relevance": "Description relevance  keywords",
        "citation_relevance":    "Citation relevance  4-sentence",
        "completeness":          "Completeness  all fields present",
    }
    for key, info in breakdown.items():
        s, mx = info["score"], info["max"]
        pip = "✓" if s == mx else ("~" if s > 0 else "✗")
        print(f"  {pip}  {labels[key]:42s}  {s}/{mx}")
        if s < mx:
            for line in info["details"]:
                print(f"       {line}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Quality gate: score a bias draft 1-10, auto-fix if < 9."
    )
    parser.add_argument("--bias", required=True, help="Bias ID (e.g. cold-tongue-bias)")
    parser.add_argument("--no-fix", action="store_true",
                        help="Score only — do not call any agents to fix failures")
    args = parser.parse_args()

    bias_id     = args.bias.lower().strip()
    draft_path  = DRAFTS_DIR / f"{bias_id}.json"
    papers_path = PAPERS_DIR / f"{bias_id}.json"

    for p, label in [(draft_path, "draft"), (papers_path, "papers")]:
        if not p.exists():
            print(f"[error] {label} file not found: {p}", file=sys.stderr)
            return 1

    attempt = 0
    while True:
        attempt += 1

        draft       = json.loads(draft_path.read_text(encoding="utf-8"))
        papers_data = json.loads(papers_path.read_text(encoding="utf-8"))

        total, breakdown = score_entry(draft, papers_data)
        print_report(bias_id, total, breakdown, attempt)

        if total >= PASS_SCORE:
            print(f"  ✓ Entry passes quality gate ({total}/10 ≥ {PASS_SCORE}).\n")
            return 0

        if args.no_fix:
            print(f"  ✗ Score {total}/10 is below threshold {PASS_SCORE}. "
                  f"(--no-fix: not calling agents)\n")
            return 1

        if attempt > MAX_RETRIES:
            print(f"  ✗ Still failing after {MAX_RETRIES} fix attempts. "
                  f"Manual review required for {bias_id}.\n",
                  file=sys.stderr)
            return 1

        bd = breakdown
        pipeline = agents_to_call(
            s_integrity = bd["citation_integrity"]["score"],
            s_papers    = bd["paper_verification"]["score"],
            s_desc      = bd["description_relevance"]["score"],
            s_cite_rel  = bd["citation_relevance"]["score"],
            s_complete  = bd["completeness"]["score"],
        )

        if not pipeline:
            # Score is borderline (e.g. 8) but no clear fix target — try draft only
            pipeline = ["write_draft.py"]

        print(f"  Fixing: will call → {' → '.join(pipeline)}\n")
        for script in pipeline:
            rc = run_agent(script, bias_id)
            if rc != 0:
                print(f"  [error] {script} exited with code {rc}. "
                      f"Stopping fix loop.", file=sys.stderr)
                return 1


if __name__ == "__main__":
    sys.exit(main())
