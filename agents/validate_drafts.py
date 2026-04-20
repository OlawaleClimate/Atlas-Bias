#!/usr/bin/env python3
"""Validate all drafts in pipeline/outputs/drafts/ against the schema."""
from __future__ import annotations
import json
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parents[1]
DRAFTS_DIR  = REPO_ROOT / "pipeline" / "outputs" / "drafts"

REQUIRED_FIELDS = [
    "id", "name", "version", "last_updated", "category", "region",
    "season", "affected_variables", "description", "persistence",
    "cmip_history", "severity_by_model", "implicated_params",
    "fix_attempts", "cascade_links", "disputed_mechanisms",
    "citations", "feedback_history", "changelog",
]
CATEGORY_ENUM   = ["precipitation", "temperature", "circulation",
                   "clouds", "ocean", "land", "sea_ice"]
PERSISTENCE_ENUM = ["longstanding", "improved", "resolved", "introduced"]
CMIP_GENS       = ["CMIP3", "CMIP5", "CMIP6", "CMIP7"]
SEVERITIES      = ["strong", "moderate", "weak", "absent"]


def validate(path: Path) -> list[str]:
    d = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in d:
            errors.append(f"missing required field: {field}")

    if d.get("category") not in CATEGORY_ENUM:
        errors.append(f"category={d.get('category')!r} not in enum")

    if d.get("persistence") not in PERSISTENCE_ENUM:
        errors.append(f"persistence={d.get('persistence')!r} not in enum")

    for i, h in enumerate(d.get("cmip_history", [])):
        if h.get("generation") not in CMIP_GENS:
            errors.append(f"cmip_history[{i}].generation={h.get('generation')!r}")
        if h.get("severity") not in SEVERITIES:
            errors.append(f"cmip_history[{i}].severity={h.get('severity')!r}")
        if not h.get("notes"):
            errors.append(f"cmip_history[{i}].notes is empty")

    for i, c in enumerate(d.get("citations", [])):
        for k in ("authors", "year", "journal", "doi", "relevance"):
            if not c.get(k):
                errors.append(f"citations[{i}] missing/empty: {k}")

    if len(d.get("citations", [])) < 5:
        errors.append(f"only {len(d.get('citations', []))} citations — need 5")

    return errors


def main() -> None:
    files = sorted(DRAFTS_DIR.glob("*.json"))
    if not files:
        print("[WARN] No draft files found in", DRAFTS_DIR)
        return

    passed = 0
    for f in files:
        errors = validate(f)
        icon = "OK  " if not errors else "FAIL"
        d = json.loads(f.read_text(encoding="utf-8"))
        print(f"[{icon}]  {f.name}  "
              f"(citations={len(d.get('citations', []))}, "
              f"cmip_history={len(d.get('cmip_history', []))})")
        for e in errors:
            print(f"         ! {e}")
        if not errors:
            passed += 1

    print(f"\n{passed}/{len(files)} drafts valid")


if __name__ == "__main__":
    main()
