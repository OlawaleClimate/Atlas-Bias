#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRIES_DIR = REPO_ROOT / "src" / "data" / "entries"
DEFAULT_VERIFIED_PATH = REPO_ROOT / ".github" / "tmp" / "verified_feedback.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply verified feedback to a bias record.")
    parser.add_argument(
        "--verified-payload",
        default=str(DEFAULT_VERIFIED_PATH),
        help="Path to verified feedback JSON produced by verify_feedback.py.",
    )
    parser.add_argument(
        "--approved-by",
        default="qc_reviewer",
        help="Reviewer identity for changelog approval metadata.",
    )
    parser.add_argument(
        "--verified-by",
        default="schema_validator",
        help="Verifier identity for changelog metadata.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_verified_payload(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    if not doc.get("ok"):
        raise ValueError("Verified payload is not marked ok=true.")
    verified = doc.get("verified_feedback")
    if not isinstance(verified, dict):
        raise ValueError("Missing verified_feedback object.")
    return verified


def ensure_list_field(record: dict[str, Any], key: str) -> list[Any]:
    value = record.get(key)
    if isinstance(value, list):
        return value
    record[key] = []
    return record[key]


def apply_feedback(record: dict[str, Any], verified: dict[str, Any], approved_by: str, verified_by: str) -> dict[str, Any]:
    issue_number = verified.get("issue_number")
    pr_number = verified.get("pr_number")
    feedback_history = ensure_list_field(record, "feedback_history")

    already_present = any(
        isinstance(item, dict) and item.get("issue_number") == issue_number for item in feedback_history
    )
    if not already_present:
        feedback_history.append(
            {
                "issue_number": issue_number,
                "type": "external_feedback",
                "submitted_by": verified.get("submitted_by", "unknown"),
                "date": verified.get("date", date.today().isoformat()),
                "verdict": verified.get("verdict"),
                "confidence": verified.get("confidence"),
                "pr_number": int(pr_number) if isinstance(pr_number, int) else 0,
            }
        )

    citations = ensure_list_field(record, "citations")
    doi = verified.get("doi")
    if isinstance(doi, str) and doi.strip() != "":
        exists = any(isinstance(c, dict) and c.get("doi") == doi for c in citations)
        if not exists:
            citations.append(
                {
                    "authors": "Community submission",
                    "year": int(date.today().year),
                    "journal": "User Feedback",
                    "doi": doi,
                    "relevance": verified.get("summary", "Feedback-linked evidence"),
                }
            )

    changelog = ensure_list_field(record, "changelog")
    current_version = str(record.get("version", "1.0"))
    changelog.append(
        {
            "version": current_version,
            "date": date.today().isoformat(),
            "change": f"Integrated verified feedback from issue #{issue_number}",
            "submitted_by": verified.get("submitted_by", "unknown"),
            "issue": int(issue_number) if isinstance(issue_number, int) else 0,
            "pr": int(pr_number) if isinstance(pr_number, int) else 0,
            "verified_by": verified_by,
            "approved_by": approved_by,
        }
    )

    record["last_updated"] = date.today().isoformat()
    return record


def main() -> int:
    args = parse_args()
    verified_path = Path(args.verified_payload)
    if not verified_path.exists():
        print(f"Verified payload not found: {verified_path}")
        return 2

    try:
        verified = load_verified_payload(verified_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid verified payload: {exc}")
        return 1

    bias_id = verified.get("bias_id")
    if not isinstance(bias_id, str) or bias_id.strip() == "":
        print("verified_feedback.bias_id is missing or invalid")
        return 1

    record_path = ENTRIES_DIR / f"{bias_id}.json"
    if not record_path.exists():
        print(f"Record not found for bias_id={bias_id}: {record_path}")
        return 1

    record = read_json(record_path)
    updated = apply_feedback(record, verified, args.approved_by, args.verified_by)
    write_json(record_path, updated)
    print(f"Updated record: {record_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
