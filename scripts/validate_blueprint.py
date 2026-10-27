#!/usr/bin/env python3
"""Blueprint completeness and schema gate (schemas/mockup-blueprint.schema.json). Requires jsonschema."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

REQUIRED = {"schema_version", "mockup_id", "mockup_revision", "approval_status", "scope", "elements", "coverage_audit"}
ELEMENT_REQUIRED = {"element_id", "scope", "evidence_status", "observed_details", "motion_candidates", "production_strategy"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blueprint")
    parser.add_argument("--allow-pending", action="store_true",
                        help="Validate structure/schema for a generated or pending blueprint without claiming approval.")
    args = parser.parse_args()
    try:
        data = common.read_json(args.blueprint)
    except (OSError, ValueError) as exc:
        print(f"FAIL cannot read blueprint: {exc}")
        return 1
    if not isinstance(data, dict):
        print("FAIL blueprint must be a JSON object")
        return 1
    missing = REQUIRED - set(data)
    if missing:
        print("FAIL missing:", sorted(missing))
        return 1
    if data["approval_status"] != "approved" and not args.allow_pending:
        print("INCOMPLETE: mockup not approved")
        return 1
    if not isinstance(data["elements"], list) or not data["elements"]:
        print("FAIL empty elements")
        return 1
    for index, element in enumerate(data["elements"]):
        if not isinstance(element, dict):
            print("FAIL element", index, "is not an object")
            return 1
        need = ELEMENT_REQUIRED - set(element)
        if need:
            print("FAIL element", index, "missing", sorted(need))
            return 1
    coverage = data["coverage_audit"] if isinstance(data["coverage_audit"], dict) else {}
    if coverage.get("status") != "pass" and not args.allow_pending:
        print("INCOMPLETE coverage audit not pass")
        return 1
    try:
        common.validate_schema(data, "mockup-blueprint")
    except ValueError as exc:  # includes a missing jsonschema: the check could not run, so it cannot pass
        print(f"FAIL {exc}")
        return 1
    if args.allow_pending:
        print(f"PASS pending/generated blueprint syntax and schema (approval_status={data['approval_status']}). Visual completeness NOT proven.")
    else:
        print("PASS blueprint syntax, required fields and schema. Visual completeness NOT proven.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
