#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema" / "bias_record_schema.json"
ENTRIES_DIR = REPO_ROOT / "src" / "data" / "entries"
VALIDATED_DIR = REPO_ROOT / "pipeline" / "outputs" / "validated"
DRAFTS_DIR = REPO_ROOT / "pipeline" / "outputs" / "drafts"


def validate_node(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    schema_type = schema.get("type")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")

    if schema_type == "object":
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {type(value).__name__}")
            return

        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key '{key}'")

        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties")

        for key, child in value.items():
            if key in properties:
                validate_node(child, properties[key], f"{path}.{key}", errors)
            elif isinstance(additional, dict):
                validate_node(child, additional, f"{path}.{key}", errors)
        return

    if schema_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array, got {type(value).__name__}")
            return
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                validate_node(item, item_schema, f"{path}[{idx}]", errors)
        return

    if schema_type == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string, got {type(value).__name__}")
            return
        min_len = schema.get("minLength")
        if isinstance(min_len, int) and len(value) < min_len:
            errors.append(f"{path}: string shorter than minLength={min_len}")
        if schema.get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{path}: malformed date '{value}' (expected YYYY-MM-DD)")
        return

    if schema_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{path}: expected integer, got {type(value).__name__}")
        return


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def main() -> int:
    if not SCHEMA_PATH.exists():
        print(f"Schema file missing: {SCHEMA_PATH}")
        return 2
    if not ENTRIES_DIR.exists():
        print(f"Entries directory missing: {ENTRIES_DIR}")
        return 2

    VALIDATED_DIR.mkdir(parents=True, exist_ok=True)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    schema = load_schema()
    files = sorted(ENTRIES_DIR.glob("*.json"))
    if not files:
        print("No entry files found.")
        return 1

    valid_count = 0
    invalid_count = 0
    invalid_reports: list[dict[str, Any]] = []

    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            invalid_count += 1
            report = {
                "file": path.name,
                "errors": [f"$root: invalid JSON ({exc.msg}) at line {exc.lineno} column {exc.colno}"],
            }
            invalid_reports.append(report)
            (DRAFTS_DIR / f"{path.stem}.errors.json").write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            continue

        errors: list[str] = []
        validate_node(payload, schema, "$root", errors)

        if errors:
            invalid_count += 1
            report = {"file": path.name, "errors": errors}
            invalid_reports.append(report)
            (DRAFTS_DIR / f"{path.stem}.errors.json").write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            continue

        valid_count += 1
        shutil.copy2(path, VALIDATED_DIR / path.name)

    summary = {
        "scanned": len(files),
        "valid": valid_count,
        "invalid": invalid_count,
        "reports": invalid_reports,
    }
    (VALIDATED_DIR / "_validation_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(f"Validation complete: scanned={len(files)} valid={valid_count} invalid={invalid_count}")
    return 0 if invalid_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
