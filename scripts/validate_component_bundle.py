#!/usr/bin/env python3
"""Validate a Game Arts component bundle and all companion PNG/atlas files.

Does not certify visual correctness, mechanical physics or Godot runtime behavior.
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image


def valid_matrix(value):
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(row, list) and len(row) == 3 and all(
            isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)
            for x in row
        ) for row in value)
    )


def validate(bundle_dir):
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
    args = p.parse_args()
    try:
        problems = validate(args.bundle_dir.resolve())
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        p.exit(1, f"FAIL {error}\n")
    if problems:
        for problem in problems:
            print("FAIL", problem)
        raise SystemExit(1)
    print("PASS component files, atlas geometry and sampled transform structure")
    print("NOT VERIFIED: visual alignment, unsampled time, physics, Godot runtime")


if __name__ == "__main__":
    main()
