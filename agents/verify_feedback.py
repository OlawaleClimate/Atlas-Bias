#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRIES_DIR = REPO_ROOT / "src" / "data" / "entries"
OUTPUT_DIR = REPO_ROOT / ".github" / "tmp"

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
VERDICTS = {"CONFIRMED", "DISPUTED", "REJECTED"}
CONFIDENCE = {"high", "medium", "low"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify structured bias feedback issue payload.")
    parser.add_argument(
        "--issue-payload",
        default="",
        help="Path to issue payload JSON (defaults to GITHUB_EVENT_PATH in Actions).",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "verified_feedback.json"),
        help="Output path for verification result.",
    )
    return parser.parse_args()


def list_known_bias_ids() -> set[str]:
    ids: set[str] = set()
    if not ENTRIES_DIR.exists():
        return ids
    for path in sorted(ENTRIES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        entry_id = data.get("id")
        if isinstance(entry_id, str) and entry_id:
            ids.add(entry_id)
    return ids


def parse_body_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        fields[normalized] = value.strip()

    # Support GitHub Issue Forms body style:
    # ### bias_id
    # value
    # ### verdict
    # CONFIRMED
    if len(fields) == 0:
        lines = [ln.rstrip() for ln in body.splitlines()]
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line.startswith("### "):
                i += 1
                continue

            key = line[4:].strip().lower().replace(" ", "_")
            i += 1
            value_parts: list[str] = []
            while i < len(lines):
                nxt = lines[i].strip()
                if nxt.startswith("### "):
                    break
                if nxt != "":
                    value_parts.append(nxt)
                i += 1

            if key and value_parts:
                fields[key] = " ".join(value_parts)

    return fields


def validate(payload: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    issue = payload.get("issue", {})
    if not isinstance(issue, dict):
        return ["Missing 'issue' object in payload."], {}

    issue_number = issue.get("number")
    issue_title = issue.get("title")
    issue_body = issue.get("body") or ""
    user = (issue.get("user") or {}).get("login", "unknown")

    if not isinstance(issue_number, int):
        errors.append("Issue number missing or invalid.")
    if not isinstance(issue_title, str) or issue_title.strip() == "":
        errors.append("Issue title missing or empty.")
    if not isinstance(issue_body, str) or issue_body.strip() == "":
        errors.append("Issue body missing or empty.")

    fields = parse_body_fields(issue_body if isinstance(issue_body, str) else "")
    bias_id = fields.get("bias_id", "")
    verdict = fields.get("verdict", "").upper()
    confidence = fields.get("confidence", "").lower()
    doi = fields.get("doi", "")
    summary = fields.get("summary", "")
    pr_number_raw = fields.get("pr_number", "")

    known_ids = list_known_bias_ids()
    if not bias_id:
        errors.append("Missing 'bias_id' in issue body.")
    elif bias_id not in known_ids:
        errors.append(f"Unknown bias_id '{bias_id}'.")

    if verdict not in VERDICTS:
        errors.append("Invalid or missing verdict (expected CONFIRMED, DISPUTED, or REJECTED).")

    if confidence not in CONFIDENCE:
        errors.append("Invalid or missing confidence (expected high, medium, or low).")

    if doi and not DOI_RE.match(doi):
        errors.append(f"Invalid DOI format '{doi}'.")

    pr_number: int | None = None
    if pr_number_raw:
        try:
            pr_number = int(pr_number_raw)
        except ValueError:
            errors.append(f"Invalid pr_number '{pr_number_raw}', expected integer.")

    verified = {
        "issue_number": issue_number,
        "title": issue_title,
        "submitted_by": user,
        "date": date.today().isoformat(),
        "bias_id": bias_id,
        "verdict": verdict,
        "confidence": confidence,
        "doi": doi,
        "summary": summary,
        "pr_number": pr_number,
        "raw_fields": fields,
    }
    return errors, verified


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    payload_path_str = args.issue_payload or os.getenv("GITHUB_EVENT_PATH", "")
    payload_path = Path(payload_path_str) if payload_path_str else Path(".github/tmp/issue_payload.json")

    if not payload_path.exists():
        print(f"No issue payload found at {payload_path}")
        return 2

    payload = load_payload(payload_path)
    errors, verified = validate(payload)
    result = {
        "ok": len(errors) == 0,
        "errors": errors,
        "verified_feedback": verified,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if errors:
        print("Verification failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(f"Verification passed for bias_id={verified['bias_id']} issue={verified['issue_number']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
