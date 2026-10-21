#!/usr/bin/env python3
"""Game Arts project setup wizard. Python 3.9+, standard library only."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path(".gamearts/project.json")
STYLES = ["pixel_art", "hand_painted", "illustrated", "vector", "rendered_2d", "custom"]
SCOPES = ["world", "scene", "asset", "character", "ui_screen", "ui_flow", "mixed"]
DIRECTIONS = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]

def ask(label, default, choices=None):
    hint = " / ".join(choices) if choices else str(default)
    while True:
        value = input(f"{label} [{hint}] (default: {default}): ").strip() or str(default)
        if not choices or value in choices:
            return value
        print("Invalid selection. Choose one of:", ", ".join(choices))

def positive_float(value, label):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be numeric") from None
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number

def positive_int(value, label):
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be an integer") from None
    if n <= 0:
        raise ValueError(f"{label} must be positive")
    return n

def validate(data):
    errors = []
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if not str(data.get("project_id", "")).strip():
        errors.append("project_id cannot be empty")
    art = data.get("art_style", {})
    if art.get("id") not in STYLES:
        errors.append("art_style.id is invalid")
    world = data.get("world", {})
    if world.get("grid") not in ["orthogonal_square", "custom"]:
        errors.append("world.grid invalid")
    for key in ["logical_tile_m", "ground_tile_px"]:
        v = world.get(key)
        if not isinstance(v, list) or len(v)!=2:
            errors.append(f"world.{key} must be [width,height]")
        else:
            try:
                for value in v: positive_float(value, key)
            except ValueError as e: errors.append(str(e))
    for key in ["pixels_per_meter", "construction_snap_m"]:
        try: positive_float(world.get(key), key)
        except ValueError as e: errors.append(str(e))
    if world.get("grid")=="orthogonal_square" and art.get("id")=="pixel_art":
        # Compatible by default, but custom dimensions may be deliberately approved.
        pass
    ds = data.get("directions", [])
    if not isinstance(ds, list) or not ds or len(ds)!=len(set(ds)):
        errors.append("directions must be a unique nonempty list")
    if data.get("export",{}).get("background_hex")!="#FF00FF" or data.get("export",{}).get("background_alpha")!=255:
        errors.append("global source PNG background MUST be exact opaque #FF00FF")
    if data.get("export",{}).get("atlas_per_sheet") is not True:
        errors.append("atlas_per_sheet must remain true")
    if data.get("workflow",{}).get("mockup_approval_required") is not True:
        errors.append("mockup approval must remain required")
    if data.get("workflow",{}).get("detail_decomposition_required") is not True:
        errors.append("mockup decomposition must remain required")
    if data.get("export",{}).get("no_zip") is not True:
        errors.append("no_zip must remain true")
    return errors

def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=".", help="Target GAME repository directory, not necessarily GameArtsSkills")
    parser.add_argument("--show", action="store_true", help="Display saved Game Arts settings")
    parser.add_argument("--validate", action="store_true", help="Validate saved Game Arts settings")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing configuration")
    args=parser.parse_args()
    root=Path(args.project_dir).expanduser().resolve()
    path=root/CONFIG
    if args.show or args.validate:
        if not path.is_file():
            parser.error(f"Missing {path}; run setup first.")
        data=json.loads(path.read_text(encoding="utf-8"))
        problems=validate(data)
        if args.show: print(json.dumps(data,indent=2))
        if args.validate: print("VALID" if not problems else "INVALID: "+"; ".join(problems))
        raise SystemExit(1 if problems else 0)
    if path.exists() and not args.overwrite:
        parser.error(f"{path} already exists. Use --show to inspect or --overwrite to reconfigure.")
    print(f"Game Arts setup for: {root}")
    print("Press Enter for a default. Choices are persisted in .gamearts/project.json.")
    project_id=ask("Project ID", re.sub(r"[^a-z0-9_-]+","-",root.name.lower()).strip("-") or "game")
    style=ask("Art style", "pixel_art", STYLES)
    style_reference=ask("Approved style reference ID/path (or 'pending')", "pending")
    camera=ask("World object camera depiction", "elevated_3_4_oblique",["elevated_3_4_oblique","top_down","side","custom"])
    grid=ask("World grid", "orthogonal_square",["orthogonal_square","custom"])
    tw=positive_float(ask("Terrain tile world width (m)", "16"),"tile width")
    th=positive_float(ask("Terrain tile world height (m)", "16"),"tile height")
    pw=positive_int(ask("Terrain cell image width (px)", "256"),"tile pixel width")
    ph=positive_int(ask("Terrain cell image height (px)", "256"),"tile pixel height")
    ppm=positive_float(ask("Nominal pixels per world meter", "16"),"pixels_per_meter")
    snap=positive_float(ask("Construction snap (m)", "1"),"construction_snap")
    directions_text=ask("Default directional views (comma-separated)", ",".join(DIRECTIONS))
    directions=[x.strip().upper() for x in directions_text.split(",") if x.strip()]
    animation=ask("Animation planning preference", "hybrid",["hybrid","frame_based","transform_based"])
    scope=ask("Typical mockup scope", "scene",SCOPES)
    data={
      "schema_version":"1.0",
      "project_id":project_id,
      "master_standard":"GAME_ARTS_MASTER_STANDARD_v7.2.md",
      "configured_at_utc":datetime.now(timezone.utc).isoformat(),
      "art_style":{"id":style,"reference":style_reference},
      "world":{"grid":grid,"object_camera":camera,"logical_tile_m":[tw,th],
               "ground_tile_px":[pw,ph],"pixels_per_meter":ppm,
               "construction_snap_m":snap,"continuous_world_coordinates":True,
               "native_sprite_scale":[1,1]},
      "directions":directions,
      "animation":{"preferred_method":animation,"discover_moving_components":True,
                   "directional_component_coverage":True,"animated_attachment_anchors":True,
                   "frame_count_policy":"per_asset_profile"},
      "workflow":{"mockup_approval_required":True,"detail_decomposition_required":True,
                  "typical_mockup_scope":scope,"reference_locked_after_approval":True},
      "export":{"background_hex":"#FF00FF","background_alpha":255,"atlas_per_sheet":True,"no_zip":True},
      "godot":{"major_version":4,"validation_required":True},
      "overrides":{"asset_profiles_directory":".gamearts/asset-profiles"}
    }
    errors=validate(data)
    if errors:
        parser.error("; ".join(errors))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"\nSaved {path}")
    print("Commit the file to your game repository. Future Claude/Codex sessions should read it before generating art.")

if __name__=="__main__":
    run()
