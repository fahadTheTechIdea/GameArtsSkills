#!/usr/bin/env python3
"""Validate a Game Arts component bundle and all companion PNG/atlas files.

Checks the bundle/atlas contracts, every sheet's exact-key pixels, parent mount names, track reachability and sampled
transforms. `--approval-gate` additionally requires pixel-verified parent cleanup for every separated component and
direction. It does not certify visual correctness or any engine's behavior.
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
from build_component_bundle import check_tracks  # noqa: E402
from validate_parent_cleanup import checked_report  # noqa: E402
from validate_sheet_atlas import validate as validate_sheet  # noqa: E402


def valid_matrix(value):
    return (isinstance(value, list) and len(value) == 3 and all(
        isinstance(row, list) and len(row) == 3 and all(
            isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in row) for row in value))


def validate(bundle_dir, approval_gate=False):
    bundle_dir = Path(bundle_dir)
    issues = []
    files = list(bundle_dir.glob("*.bundle.json"))
    if len(files) != 1:
        return ["Expected exactly one .bundle.json in candidate folder"]
    data = common.read_json(files[0])
    try:
        common.validate_schema(data, "gamearts-bundle")
    except ValueError as exc:
        return [f"bundle contract: {exc}"]
    components, directions = data["components"], data["directions"]
    ids = [c["id"] for c in components]
    if len(set(ids)) != len(ids):
        issues.append("Duplicate component IDs")
    available = {c["id"]: c for c in components}
    atlases_by_component = {}
    for comp in components:
        cid, parent = comp["id"], comp["parent"]
        if parent is not None and (parent not in available or parent == cid):
            issues.append(f"{cid}: unknown/invalid parent {parent}")
        if parent is not None and not comp.get("mount"):
            issues.append(f"{cid}: missing named mount")
        if set(comp["atlases"]) != set(directions):
            issues.append(f"{cid}: incomplete atlas directions")
        own_action = comp.get("action", "default")
        parent_action = comp.get("parent_action") or (available[parent].get("action", "default") if parent in available else own_action)
        for label, tracks, action in (("motion_tracks", comp.get("motion_tracks", {}), own_action),
                                      ("mount_tracks", comp.get("mount_tracks", {}), parent_action)):
            try:
                check_tracks(tracks, action, directions, f"{cid}.{label}")
            except ValueError as exc:
                issues.append(str(exc))
        for direction in directions:
            name = comp["atlases"].get(direction)
            if not isinstance(name, str) or Path(name).name != name:
                issues.append(f"{cid}/{direction}: invalid atlas path")
                continue
            atlas_path = bundle_dir / name
            if not atlas_path.is_file():
                issues.append(f"{cid}/{direction}: missing atlas {name}")
                continue
            atlas = common.read_json(atlas_path)
            image_name = atlas.get("image")
            if not isinstance(image_name, str) or Path(image_name).name != image_name:
                issues.append(f"{cid}/{direction}: invalid PNG path")
                continue
            issues += [f"{cid}/{direction}: {i}" for i in validate_sheet(bundle_dir / image_name, atlas_path)]
            atlases_by_component[(cid, direction)] = atlas
    for comp in components:  # a child's named mount must exist on every frame of its parent, in every direction
        if comp["parent"] in available and comp.get("mount"):
            for direction in directions:
                parent_atlas = atlases_by_component.get((comp["parent"], direction))
                if parent_atlas:
                    missing = [i for i, f in enumerate(parent_atlas["frames"]) if comp["mount"] not in f["anchors"]]
                    if missing:
                        issues.append(f"{comp['id']}/{direction}: mount {comp['mount']} missing from parent frames {missing}")

    if approval_gate:
        # Every independently separated component must be absent from the parent source art in EVERY applicable parent
        # direction and source frame. A plain builder pass is not approval: approval requires this gate.
        children = {}
        for part in components:
            if part["parent"] is not None:
                children.setdefault(part["parent"], set()).add(part["id"])
        entries = data.get("parent_cleanup_evidence", [])
        declarations = data.get("detached_inventory", {})
        if not isinstance(declarations, dict):
            issues.append("detached_inventory must be a parent-ID keyed object")
            declarations = {}
        slots = {}
        for row in entries:
            key = (row.get("parent_component"), row.get("direction"), row.get("frame_index"))
            if key in slots:
                issues.append(f"duplicate parent-cleanup evidence for {key}")
            slots[key] = row
        expected_keys = set()
        for parent_id, declared_ids in declarations.items():
            if not isinstance(declared_ids, list) or not declared_ids or any(not isinstance(v, str) or not v for v in declared_ids):
                issues.append(f"{parent_id}: detached inventory must contain nonempty component IDs")
                continue
            if parent_id not in available:
                issues.append(f"{parent_id}: detached inventory parent is not in bundle")
                continue
            children.setdefault(parent_id, set()).update(declared_ids)
        for parent_id, child_ids in children.items():
            parent = available.get(parent_id)
            if not parent:
                continue
            mandatory = set(declarations.get(parent_id, [])) | child_ids
            for direction in directions:
                atlas = atlases_by_component.get((parent_id, direction))
                if not atlas:
                    continue
                for index, frame in enumerate(atlas["frames"]):
                    key = (parent_id, direction, index)
                    expected_keys.add(key)
                    if key not in slots:
                        issues.append(f"missing mandatory parent-cleanup evidence: {key}")
                        continue
                    filename = slots[key].get("manifest")
                    try:
                        manifest_path = common.safe_member(bundle_dir, filename, "cleanup manifest")
                        if not filename.endswith(".json") or not manifest_path.is_file():
                            issues.append(f"missing cleanup manifest for {key}")
                            continue
                        report = checked_report(manifest_path, strict_props=True)
                        if report["technical_status"] != "passed":
                            issues.extend(f"{key}: {message}" for message in report["failures"])
                        cleanup = common.read_json(manifest_path)
                        declared = {v.get("id") for v in cleanup.get("detached_components", []) if isinstance(v, dict)}
                        missing_ids = mandatory - declared
                        if missing_ids:
                            issues.append(f"{key}: detached assets absent from cleanup proof: {sorted(missing_ids)}")
                        source_frame = common.safe_member(manifest_path.parent, cleanup["static_parent"], "static_parent")
                        if not source_frame.is_file() or frame.get("source_sha256") != common.sha256_file(source_frame):
                            issues.append(f"{key}: static parent cleanup image does not match actual atlas source frame")
                    except (ValueError, OSError, KeyError, TypeError) as error:
                        issues.append(f"{key}: cleanup proof invalid: {error}")
        for key in set(slots) - expected_keys:
            issues.append(f"unexpected parent-cleanup evidence entry: {key}")

    poses = data.get("sampled_poses", [])
    if not poses:
        issues.append("Missing evaluated animation poses")
    for pose in poses:
        if pose.get("direction") not in directions:
            issues.append("Pose contains unsupported direction")
        if set(pose.get("nodes", {})) != set(ids):
            issues.append("Pose missing component")
        for cid, node in pose.get("nodes", {}).items():
            if not valid_matrix(node.get("world_matrix_2d")):
                issues.append(f"{cid}: invalid composed transform matrix")
    return issues


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle_dir", type=Path)
    p.add_argument("--approval-gate", action="store_true",
                   help="Require pixel-verified parent cleanup for every separated component and direction")
    args = p.parse_args()
    try:
        problems = validate(args.bundle_dir.resolve(), approval_gate=args.approval_gate)
    except (OSError, ValueError, TypeError) as error:  # ValueError covers JSON and contract errors
        p.exit(1, f"FAIL {error}\n")
    if problems:
        for problem in problems:
            print("FAIL", problem)
        raise SystemExit(1)
    print("PASS component files, atlas geometry, exact-key pixels and sampled transform structure")
    if args.approval_gate:
        print("PASS mandatory parent cleanup technical gate for all declared separated components")
    else:
        print("NOT APPROVAL VERIFIED: run --approval-gate for all separated components")
    print("NOT VERIFIED: visual alignment, unsampled time, physics, engine behavior")


if __name__ == "__main__":
    main()
