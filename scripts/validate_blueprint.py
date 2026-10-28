#!/usr/bin/env python3
"""Blueprint completeness and schema gate (schemas/mockup-blueprint.schema.json). Requires jsonschema."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

SWEEP_SCOPES = {"world", "scene", "mixed"}  # a scene is emptied of everything separable, so the sweep of object classes is required for these once approved
REQUIRED = {"schema_version", "mockup_id", "mockup_revision", "approval_status", "scope", "elements", "coverage_audit"}
ELEMENT_REQUIRED = {"element_id", "scope", "evidence_status", "observed_details", "motion_candidates", "production_strategy"}


def object_classes():
    """The object classes, read from the contract so there is one list."""
    schema = common.read_json(common.SCHEMAS / "mockup-blueprint.schema.json")
    return schema["properties"]["object_sweep"]["items"]["properties"]["object_class"]["enum"]


def sweep_problems(data):
    """What is wrong with the object sweep, in words (an empty list means it is consistent). Every class is addressed exactly once; a present class names the separation_inventory
    components that are of it, and each exists; an absent class names none and no component claims it; a component that declares a class appears in that class's entry."""
    classes = object_classes()
    components = {}
    for element in data["elements"]:
        for component in element.get("separation_inventory", []) or []:
            components[component.get("component_id")] = component.get("object_class")
    problems, seen = [], {}
    for entry in data["object_sweep"]:
        name = entry.get("object_class")
        if name in seen:
            problems.append(f"class {name} is addressed more than once")
        seen[name] = entry
    for name in classes:
        if name not in seen:
            problems.append(f"class {name} is not addressed: say present (with its components) or absent (with what was checked)")
    for name, entry in seen.items():
        ids = entry.get("component_ids") or []
        if entry.get("status") == "present":
            if not ids:
                problems.append(f"class {name} is marked present but names no component")
            for component_id in ids:
                if component_id not in components:
                    problems.append(f"class {name} names {component_id}, which no element's separation_inventory has")
                elif components[component_id] not in (None, name):
                    problems.append(f"{component_id} is listed under {name} but declares the class {components[component_id]}")
        elif ids:
            problems.append(f"class {name} is marked absent but names components")
    for component_id, declared in components.items():
        if declared is None:
            continue
        entry = seen.get(declared)
        if entry is None or entry.get("status") != "present" or component_id not in (entry.get("component_ids") or []):
            problems.append(f"{component_id} declares the class {declared} but the sweep does not list it there")
    return problems


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
    if "object_sweep" in data:
        found = sweep_problems(data)
        if found:
            print("FAIL object sweep:", "; ".join(found))
            return 1
    elif data["scope"] in SWEEP_SCOPES and not args.allow_pending:
        print("INCOMPLETE object sweep missing: a " + data["scope"] + " blueprint must address every object class (" + ", ".join(object_classes()) + ") as present or absent")
        return 1
    if args.allow_pending:
        print(f"PASS pending/generated blueprint syntax and schema (approval_status={data['approval_status']}). Visual completeness NOT proven.")
    else:
        print("PASS blueprint syntax, required fields and schema. Visual completeness NOT proven.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
