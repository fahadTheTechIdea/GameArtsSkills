#!/usr/bin/env python3
"""Create a reproducible miniature game project for real Godot smoke tests."""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_component_bundle import build as build_bundle
from generate_godot_scene import generate as generate_scene
from validate_component_bundle import validate as validate_bundle

PINK = (255, 0, 255, 255)


def frame(path, color, anchor=None):
    image = Image.new("RGBA", (24, 24), PINK)
    for y in range(7, 18):
        for x in range(8, 17):
            image.putpixel((x, y), (*color, 255))
    image.save(path)


def create(root):
    root = root.resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="GameArtsSmoke"\n'
        'run/main_scene="res://test_component.tscn"\n\n[rendering]\n'
        'renderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
    addon = root / "addons" / "gamearts"
    addon.mkdir(parents=True)
    for name in ("chroma_key.gdshader", "game_arts_component.gd", "game_arts_component.tscn"):
        shutil.copy2(ROOT / "godot" / "addons" / "gamearts" / name, addon / name)
    art = root / "source_frames"
    art.mkdir()
    dirs = ["S", "E"]
    for d in dirs:
        for comp, rgb in [("base", (35, 85, 140)), ("joint", (200, 130, 40)),
                          ("tip", (30, 160, 90))]:
            frame(art / f"{comp}_{d}.png", rgb)
    components = [
        {"id": "base", "parent": None, "views": {
            d: {"frames": [{"file": f"base_{d}.png", "pivot": [12, 20],
                             "anchors": {"mount_joint": [15, 10]}}]} for d in dirs}},
        {"id": "joint", "parent": "base", "mount": "mount_joint", "action": "extend",
         "views": {d: {"frames": [{"file": f"joint_{d}.png", "pivot": [12, 20],
                                   "anchors": {"mount_tip": [12, 8]}}]} for d in dirs},
         "mount_tracks": {"extend": {
             "S": [{"time": 0, "position": [0, 0], "rotation_degrees": 0},
                   {"time": 1, "position": [4, 0], "rotation_degrees": 90}],
             "E": [{"time": 0, "position": [0, 0], "rotation_degrees": 0},
                   {"time": 1, "position": [-4, 0], "rotation_degrees": -90}]}},
         "motion_tracks": {"extend": {
             "*": [{"time": 0, "position": [0, 0]},
                   {"time": 1, "position": [0, 1]}]}}},
        {"id": "tip", "parent": "joint", "mount": "mount_tip",
         "views": {d: {"frames": [{"file": f"tip_{d}.png", "pivot": [12, 20]}]} for d in dirs},
         "motion_tracks": {"default": {"*": [
             {"time": 0, "position": [0, 0]},
             {"time": 1, "position": [2, 0]}]}}}
    ]
    manifest = {"name": "test_component", "directions": dirs,
                "sample_times": [0, .25, .5, .75, 1], "components": components,
                "source_mockups": [{"mockup_id": "smoke_mockup", "revision": "v001"}]}
    candidate = root / ".gamearts" / "outputs" / "assets" / "generated" / "test_component"
    build_bundle(manifest, candidate, art)
    errors = validate_bundle(candidate)
    if errors:
        raise AssertionError("\n".join(errors))
    scene = generate_scene(candidate / "test_component.bundle.json", root)
    # Generate a test-only main scene that can be loaded without editor GUI.
    (root / "test_component.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="Script" path="res://addons/gamearts/game_arts_component.gd" id="1"]\n\n'
        '[node name="TestComponent" type="Node2D"]\n'
        'script = ExtResource("1")\n'
        'bundle_path = "res://.gamearts/outputs/assets/generated/test_component/test_component.bundle.json"\n',
        encoding="utf-8")
    shutil.copy2(ROOT / "tests" / "godot" / "test_runtime.gd", root / "test_runtime.gd")
    print(f"Generated Godot smoke project: {root}")
    print(f"Native scene: {scene}")
    return root


if __name__ == "__main__":
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "_godot_generated"
    create(destination)
