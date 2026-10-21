#!/usr/bin/env python3
"""Create a native Godot 4 PackedScene (.tscn) for a built Game Arts component bundle.

The scene uses the universal GameArtsComponent runtime and references an existing
bundle JSON copied into the target game's res:// filesystem. No Godot test is
claimed until the resulting scene is actually loaded in the engine.
"""
import argparse
import json
import re
from pathlib import Path

SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def generate(bundle_file, project_root):
    bundle_file = bundle_file.resolve()
    project_root = project_root.resolve()
    data = json.loads(bundle_file.read_text(encoding="utf-8"))
    name = data.get("asset_id")
    if not isinstance(name, str) or not SAFE.fullmatch(name):
        raise ValueError("Invalid asset ID for scene")
    try:
        rel = bundle_file.relative_to(project_root).as_posix()
    except ValueError:
        raise ValueError("Bundle must be inside the Godot project root") from None
    runtime = project_root / "addons" / "gamearts" / "game_arts_component.gd"
    if not runtime.is_file():
        raise ValueError("Game Arts Godot addon not installed under res://addons/gamearts/")
    if not data.get("component_order") or not data.get("directions"):
        raise ValueError("Bundle lacks components/directions")
    scene = (
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="Script" path="res://addons/gamearts/game_arts_component.gd" id="1_rig"]\n\n'
        f'[node name="{name}" type="Node2D"]\n'
        'script = ExtResource("1_rig")\n'
        f'bundle_path = "res://{rel}"\n'
        f'direction = "{data["directions"][0]}"\n'
    )
    path = bundle_file.parent / (name + ".tscn")
    if path.exists():
        raise FileExistsError(f"Scene exists: {path}")
    path.write_text(scene, encoding="utf-8")
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle_file", type=Path)
    p.add_argument("--godot-project", required=True, type=Path)
    args = p.parse_args()
    try:
        result = generate(args.bundle_file, args.godot_project)
        print(f"CREATED {result}")
        print("Godot scene not yet runtime-verified.")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        p.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
