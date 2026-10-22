#!/usr/bin/env python3
"""Validate a Game Arts component bundle and all companion PNG/atlas files.

Does not certify visual correctness, mechanical physics or Godot runtime behavior.
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image

from validate_parent_cleanup import checked_report


def valid_matrix(value):
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(row, list) and len(row) == 3 and all(
            isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)
            for x in row
        ) for row in value)
    )


def validate(bundle_dir, approval_gate=False):
    issues = []
    files = list(bundle_dir.glob("*.bundle.json"))
    if len(files) != 1:
        return ["Expected exactly one .bundle.json in candidate folder"]
    data = json.loads(files[0].read_text(encoding="utf-8"))
    components = data.get("components", [])
    directions = data.get("directions", [])
    if not isinstance(components, list) or not components or not directions:
        issues.append("Missing components/directions")
        return issues
    ids = [c.get("id") for c in components]
    if len(set(ids)) != len(ids):
        issues.append("Duplicate component IDs")
    available = {c.get("id"): c for c in components}
    for comp in components:
        cid = comp.get("id")
        parent = comp.get("parent")
        if parent is not None and (parent not in available or parent == cid):
            issues.append(f"{cid}: unknown/invalid parent {parent}")
        if parent is not None and not comp.get("mount"):
            issues.append(f"{cid}: missing named mount")
        atlases = comp.get("atlases", {})
        if set(atlases) != set(directions):
            issues.append(f"{cid}: incomplete atlas directions")
        for direction in directions:
            name = atlases.get(direction)
            if not isinstance(name, str) or Path(name).name != name:
                issues.append(f"{cid}/{direction}: invalid atlas path")
                continue
            atlas_path = bundle_dir / name
            if not atlas_path.is_file():
                issues.append(f"{cid}/{direction}: missing atlas {name}")
                continue
            atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
            image_name = atlas.get("image")
            if not isinstance(image_name, str) or Path(image_name).name != image_name:
                issues.append(f"{cid}/{direction}: invalid PNG path")
                continue
            img_path = bundle_dir / image_name
            if not img_path.is_file():
                issues.append(f"{cid}/{direction}: missing PNG {image_name}")
                continue
            with Image.open(img_path) as img:
                rgba = img.convert("RGBA")
                size = list(rgba.size)
                if rgba.getchannel("A").getextrema() != (255, 255):
                    issues.append(f"{cid}/{direction}: transparent pixels")
            if atlas.get("mask_color") != "#FF00FF":
                issues.append(f"{cid}/{direction}: incorrect mask declaration")
            if atlas.get("image_size") != size:
                issues.append(f"{cid}/{direction}: incorrect image size")
            frames = atlas.get("frames", [])
            if not frames:
                issues.append(f"{cid}/{direction}: empty frame atlas")
            for i, f in enumerate(frames):
                rect = f.get("rect", [])
                if len(rect) != 4 or any(type(n) is not int for n in rect):
                    issues.append(f"{cid}/{direction}/{i}: invalid rect")
                    continue
                x, y, w, h = rect
                if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > size[0] or y + h > size[1]:
                    issues.append(f"{cid}/{direction}/{i}: frame outside PNG")
                if not isinstance(f.get("pivot"), list) or len(f["pivot"]) != 2:
                    issues.append(f"{cid}/{direction}/{i}: missing pivot")

    if approval_gate:
        # Every independently separated component must be absent from the parent
        # source art in EVERY applicable parent direction and source frame.
        # An ordinary builder pass is not approval: approval requires this gate.
        children = {}
        for part in components:
            if part.get("parent") is not None:
                children.setdefault(part["parent"], set()).add(part["id"])
        entries = data.get("parent_cleanup_evidence", [])
        if not isinstance(entries, list):
            issues.append("parent_cleanup_evidence must be a list")
            entries = []
        declarations = data.get("detached_inventory", {})
        if not isinstance(declarations, dict):
            issues.append("detached_inventory must be a parent-ID keyed object")
            declarations = {}
        slots = {}
        for row in entries:
            if not isinstance(row, dict):
                issues.append("invalid parent-cleanup evidence entry")
                continue
            key = (row.get("parent_component"), row.get("direction"), row.get("frame_index"))
            if key in slots:
                issues.append(f"duplicate parent-cleanup evidence for {key}")
            slots[key] = row
        expected_keys = set()
        # Independently exported props may be in other asset bundles rather than
        # in this hierarchy. They still require cleanup of their visual parent.
        for parent_id, declared_ids in declarations.items():
            if not isinstance(declared_ids, list) or not declared_ids or any(
                not isinstance(v, str) or not v for v in declared_ids
            ):
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
                atlas_name = parent.get("atlases", {}).get(direction, "")
                if not isinstance(atlas_name, str) or Path(atlas_name).name != atlas_name:
                    continue
                atlas_path = bundle_dir / atlas_name
                if not atlas_path.is_file():
                    continue
                atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
                for index, frame in enumerate(atlas.get("frames", [])):
                    key = (parent_id, direction, index)
                    expected_keys.add(key)
                    if key not in slots:
                        issues.append(f"missing mandatory parent-cleanup evidence: {key}")
                        continue
                    record = slots[key]
                    filename = record.get("manifest")
                    if not isinstance(filename, str) or not filename.endswith(".json"):
                        issues.append(f"invalid cleanup manifest name for {key}")
                        continue
                    manifest_path = (bundle_dir / filename).resolve()
                    try:
                        manifest_path.relative_to(bundle_dir.resolve())
                    except ValueError:
                        issues.append(f"cleanup manifest escapes candidate folder: {key}")
                        continue
                    if not manifest_path.is_file():
                        issues.append(f"missing cleanup manifest for {key}")
                        continue
                    try:
                        report = checked_report(manifest_path, strict_props=True)
                        if report["technical_status"] != "passed":
                            issues.extend(f"{key}: {message}" for message in report["failures"])
                        cleanup = json.loads(manifest_path.read_text(encoding="utf-8"))
                        declared = {v.get("id") for v in cleanup.get("detached_components", [])
                                    if isinstance(v, dict)}
                        missing_ids = mandatory - declared
                        if missing_ids:
                            issues.append(f"{key}: detached assets absent from cleanup proof: {sorted(missing_ids)}")
                        source_frame = (manifest_path.parent / cleanup["static_parent"]).resolve()
                        if not source_frame.is_file() or frame.get("source_sha256") != __import__("hashlib").sha256(source_frame.read_bytes()).hexdigest():
                            issues.append(f"{key}: static parent cleanup image does not match actual atlas source frame")
                    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
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
    p.add_argument("--approval-gate", action="store_true", help="Require pixel-verified parent cleanup for every separated component and direction")
    args = p.parse_args()
    try:
        problems = validate(args.bundle_dir.resolve(), approval_gate=args.approval_gate)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        p.exit(1, f"FAIL {error}\n")
    if problems:
        for problem in problems:
            print("FAIL", problem)
        raise SystemExit(1)
    print("PASS component files, atlas geometry and sampled transform structure")
    if args.approval_gate:
        print("PASS mandatory parent cleanup technical gate for all declared separated components")
    else:
        print("NOT APPROVAL VERIFIED: run --approval-gate for all separated components")
    print("NOT VERIFIED: visual alignment, unsampled time, physics, Godot runtime")


if __name__ == "__main__":
    main()
