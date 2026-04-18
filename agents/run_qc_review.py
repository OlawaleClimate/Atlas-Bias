#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRIES_DIR = REPO_ROOT / "src" / "data" / "entries"
VALIDATED_DIR = REPO_ROOT / "pipeline" / "outputs" / "validated"
REVIEWED_DIR = REPO_ROOT / "pipeline" / "outputs" / "reviewed"

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
NEGATIVE_SIDE_EFFECT_TOKENS = (
    "degrad",
    "regress",
    "worsen",
    "backfir",
    "increase bias",
    "higher bias",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def all_known_bias_ids() -> set[str]:
    ids: set[str] = set()
    for entry in sorted(ENTRIES_DIR.glob("*.json")):
        try:
            payload = load_json(entry)
        except json.JSONDecodeError:
            continue
        maybe_id = payload.get("id")
        if isinstance(maybe_id, str) and maybe_id:
            ids.add(maybe_id)
    return ids


def qc_findings(record: dict[str, Any], known_ids: set[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    rid = str(record.get("id", "unknown"))

    citations = record.get("citations", [])
    if not isinstance(citations, list) or len(citations) == 0:
        findings.append(
            {
                "severity": "warning",
                "check": "citations",
                "message": "No citations provided for this record.",
            }
        )
    else:
        for idx, citation in enumerate(citations):
            if not isinstance(citation, dict):
                findings.append(
                    {
                        "severity": "error",
                        "check": "citations",
                        "message": f"citations[{idx}] must be an object.",
                    }
                )
                continue
            doi = citation.get("doi")
            if not isinstance(doi, str) or not DOI_RE.match(doi.strip()):
                findings.append(
                    {
                        "severity": "error",
                        "check": "doi_format",
                        "message": f"citations[{idx}] has invalid DOI format: {doi!r}",
                    }
                )
            year = citation.get("year")
            current_year = date.today().year
            if isinstance(year, int) and (year < 1850 or year > current_year + 1):
                findings.append(
                    {
                        "severity": "warning",
                        "check": "citation_year",
                        "message": f"citations[{idx}] year {year} looks implausible.",
                    }
                )

    for idx, link in enumerate(record.get("cascade_links", [])):
        if not isinstance(link, dict):
            findings.append(
                {
                    "severity": "error",
                    "check": "cascade_links",
                    "message": f"cascade_links[{idx}] must be an object.",
                }
            )
            continue
        target = link.get("target_bias")
        if isinstance(target, str) and target and target not in known_ids:
            findings.append(
                {
                    "severity": "error",
                    "check": "cascade_target",
                    "message": f"cascade_links[{idx}] target '{target}' is unknown.",
                }
            )

    strong_models = 0
    for details in record.get("severity_by_model", {}).values():
        if isinstance(details, dict) and details.get("severity") == "strong":
            strong_models += 1
    if strong_models > 0 and not record.get("implicated_params"):
        findings.append(
            {
                "severity": "warning",
                "check": "parameterization_evidence",
                "message": "Strong model severity exists but implicated_params is empty.",
            }
        )

    for idx, attempt in enumerate(record.get("fix_attempts", [])):
        if not isinstance(attempt, dict):
            findings.append(
                {
                    "severity": "error",
                    "check": "fix_attempts",
                    "message": f"fix_attempts[{idx}] must be an object.",
                }
            )
            continue
        outcome = str(attempt.get("outcome", "")).strip().lower()
        side_effects = str(attempt.get("side_effects", "")).strip().lower()
        if outcome == "success" and any(tok in side_effects for tok in NEGATIVE_SIDE_EFFECT_TOKENS):
            findings.append(
                {
                    "severity": "error",
                    "check": "fix_consistency",
                    "message": (
                        "fix_attempts[{idx}] outcome='success' contradicts negative "
                        "side_effects text."
                    ).format(idx=idx),
                }
            )
        if outcome == "backfired" and (side_effects == "" or side_effects in {"none", "n/a", "na"}):
            findings.append(
                {
                    "severity": "error",
                    "check": "fix_consistency",
                    "message": (
                        "fix_attempts[{idx}] outcome='backfired' requires explicit "
                        "negative side_effects details."
                    ).format(idx=idx),
                }
            )

    if rid == "unknown":
        findings.append(
            {
                "severity": "error",
                "check": "record_id",
                "message": "Record missing id.",
            }
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QC review across validated bias records.")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return non-zero exit code when warnings are present.",
    )
    args = parser.parse_args()

    REVIEWED_DIR.mkdir(parents=True, exist_ok=True)
    known_ids = all_known_bias_ids()

    source_files = sorted(VALIDATED_DIR.glob("*.json"))
    # Ignore any summary file.
    source_files = [p for p in source_files if not p.name.startswith("_")]

    if not source_files:
        print("No validated files found; run schema validation first.")
        return 2

    passed = 0
    flagged = 0
    error_flagged = 0
    warning_flagged = 0
    summaries: list[dict[str, Any]] = []

    for path in source_files:
        record = load_json(path)
        rid = str(record.get("id", path.stem))
        findings = qc_findings(record, known_ids)
        has_errors = any(f["severity"] == "error" for f in findings)
        has_warnings = any(f["severity"] == "warning" for f in findings)

        if has_errors or has_warnings:
            flagged += 1
            if has_errors:
                error_flagged += 1
            else:
                warning_flagged += 1

            flag_payload = {
                "id": rid,
                "source": str(path.relative_to(REPO_ROOT)),
                "status": "flagged",
                "findings": findings,
            }
            (REVIEWED_DIR / f"{path.stem}.flag.json").write_text(
                json.dumps(flag_payload, indent=2),
                encoding="utf-8",
            )
            summaries.append(
                {
                    "id": rid,
                    "status": "flagged",
                    "error_count": sum(1 for f in findings if f["severity"] == "error"),
                    "warning_count": sum(1 for f in findings if f["severity"] == "warning"),
                }
            )
            continue

        passed += 1
        shutil.copy2(path, REVIEWED_DIR / path.name)
        summaries.append({"id": rid, "status": "pass", "error_count": 0, "warning_count": 0})

    summary = {
        "scanned": len(source_files),
        "passed": passed,
        "flagged": flagged,
        "flagged_errors": error_flagged,
        "flagged_warnings": warning_flagged,
        "fail_on_warning": args.fail_on_warning,
        "results": summaries,
    }
    (REVIEWED_DIR / "_qc_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(
        "QC complete: "
        f"scanned={len(source_files)} passed={passed} flagged={flagged} "
        f"(errors={error_flagged}, warnings={warning_flagged})"
    )
    if error_flagged > 0:
        return 1
    if args.fail_on_warning and warning_flagged > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
