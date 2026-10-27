#!/usr/bin/env python3
"""Build a real layered map with the framework and load its layers in headless Godot (plan P16.6). Evidence, not shipped.

  python plans/enhancements/evidence/godot_layered_map/run.py [--godot PATH] [--keep]

Builds in a scratch folder, with the framework's own tools: three tilesets (a base ground and two dual-grid overlays), a sheet of rocks, a 6 x 4 cell scene read
into a layered map with three rocks, and the overlay plans. Then `verify_layered_map.gd` loads the same files in the installed Godot console build, makes one
`TileMapLayer` per overlay on the dual grid, places the rocks both as atlas tiles on a y-sorted layer and as sprites, and reports what the engine did. This
script compares each observation with what the framework computed and writes output.json next to itself. Exit status 1 when a check fails.

What this cannot show: nothing is rendered, so draw order and how the pictures look are NOT observed; one engine version, one machine; the owner has not opened
these files in a game.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

import gamearts_common as common  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402
import gamearts_testkit as kit  # noqa: E402
import test_layered_map as fixtures  # noqa: E402

GODOT = r"H:\dev\Godot\Godot_v4.7.2-stable_mono_win64_console.exe"
OBJECTS = [(20, 20), (36, 28), (12, 26)]
FOOTPRINT = (8, 8)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--godot", default=GODOT)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="gamearts-godot-layered-"))
    try:
        built = work / "map"
        built.mkdir()
        fixtures.scene().save(work / "scene.png")
        below = (10, 10, 10)
        fixtures.make_tileset(built, "water_ground", "single", ["water"], {"water": fixtures.COLOURS["water"]})
        fixtures.make_tileset(built, "sand_overlay", "dual_grid_16", ["sand", "below"], {"sand": fixtures.COLOURS["sand"], "below": below})
        fixtures.make_tileset(built, "grass_overlay", "dual_grid_16", ["grass", "below"], {"grass": fixtures.COLOURS["grass"], "below": below})
        kit.make_sheet(built, "rocks", "rocks")
        terrains = [dict(t) for t in fixtures.TERRAINS]
        for entry, file in zip(terrains, ("water_ground.tileset.json", "sand_overlay.tileset.json", "grass_overlay.tileset.json")):
            entry["tileset"] = file
        objects = [{"id": f"rock_{i}", "class": "prop", "sprite": {"atlas": "rocks.atlas.json", "frame": "S0"}, "position_px": [x, y],
                    "footprint_px": list(FOOTPRINT), "collision": "footprint"} for i, (x, y) in enumerate(OBJECTS)]
        map_path, data = layered.build(work / "scene.png", terrains, (fixtures.CELL, fixtures.CELL), "shore", built, objects=objects)
        assert layered.validate(map_path) == []
        cell = [fixtures.CELL, fixtures.CELL]

        proj = work / "proj"
        (proj / "data").mkdir(parents=True)
        shutil.copyfile(HERE.parent / "godot_profile_verification" / "project.godot", proj / "project.godot")
        shutil.copyfile(HERE / "verify_layered_map.gd", proj / "verify_layered_map.gd")
        overlays, plans = [], {}
        for terrain in ("sand", "grass"):
            tileset = common.read_json(built / f"{terrain}_overlay.tileset.json")
            shutil.copyfile(built / f"{terrain}_overlay.png", proj / "data" / f"{terrain}_overlay.png")
            plan = layered.overlay_plan(data, built, terrain)
            plans[terrain] = plan
            overlays.append({"layer": f"overlay_{terrain}", "png": f"res://data/{terrain}_overlay.png", "tile": tileset["tile_size"], "columns": tileset["columns"],
                             "frames": len(tileset["tiles"]), "cells": [[x, y, tile] for (x, y), tile in sorted(plan["tiles"].items())]})
        atlas = common.read_json(built / "rocks.atlas.json")
        shutil.copyfile(built / "rocks.png", proj / "data" / "rocks.png")
        frames = atlas["frames"]
        width, height = frames[0]["rect"][2], frames[0]["rect"][3]
        separation = frames[1]["rect"][0] - frames[0]["rect"][0] - width
        pivot = frames[0]["pivot"]
        # sprites read each frame's rectangle; the tile source needs the frame count, its columns and the gap between frames
        rocks = {"png": "res://data/rocks.png", "frame_size": [width, height], "separation": separation, "columns": atlas["columns"], "tile_frames": len(frames),
                 "frames": [f["rect"] for f in frames], "pivot": pivot, "pivot_y_from_centre": pivot[1] - height / 2}
        spec = {"cell": cell, "overlays": overlays, "footprint": list(FOOTPRINT), "rocks": rocks, "objects": [{"x": x, "y": y, "frame": 0} for x, y in OBJECTS]}
        (proj / "expected.json").write_text(json.dumps(spec), encoding="utf-8")
        command = [args.godot, "--headless", "--path", str(proj), "--script", "res://verify_layered_map.gd"]
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        line = next((l for l in run.stdout.splitlines() if l.startswith("VERIFY_JSON ")), None)
        if run.returncode != 0 or line is None:
            print("The engine run failed.\n", run.stdout[-2000:], run.stderr[-2000:], file=sys.stderr)
            return 1
        observed = json.loads(line[len("VERIFY_JSON "):])
        checks = []

        def check(name, ok, detail=""):
            checks.append({"name": name, "ok": bool(ok), "detail": detail})

        for overlay in overlays:
            got = observed["overlays"][overlay["layer"]]
            ids = [c[2] for c in overlay["cells"]]
            check(f"{overlay['layer']}: the engine made one tile per tile of the overlay tileset", got["tile_count"] == overlay["frames"], f"{got['tile_count']} of {overlay['frames']}")
            check(f"{overlay['layer']}: every position of the framework's plan holds a tile", got["used_cells"] == len(ids), f"{got['used_cells']} of {len(ids)}")
            check(f"{overlay['layer']}: each position reads back the tile id the framework chose", got["ids_back"] == ids, "")
            expected_world = [[c[0] * cell[0], c[1] * cell[1]] for c in overlay["cells"]]
            check(f"{overlay['layer']}: with the layer offset by half a cell, each display tile is centred where four cells meet",
                  got["junction_world"] == [[float(a), float(b)] for a, b in expected_world], "")
        check("the layers were added, and appear in the engine's tree, in the framework's order", observed["children_in_order"][:2] == ["overlay_sand", "overlay_grass"],
              str(observed["children_in_order"]))
        tiles = observed["tile_objects"]
        snapped = [[x // cell[0], y // cell[1]] for x, y in OBJECTS]
        check("rocks as tiles: each rock lands on the cell its pixel position falls in", tiles["snapped_cells"] == snapped, str(tiles["snapped_cells"]))
        check("rocks as tiles: the layer is y-sorted", tiles["y_sort_enabled"] is True, "")
        check("rocks as tiles: every tile's y-sort origin is its pivot's distance below the tile centre", set(tiles["y_sort_origins"]) == {rocks["pivot_y_from_centre"]},
              str(tiles["y_sort_origins"]))
        half, base = FOOTPRINT[0] / 2, rocks["pivot_y_from_centre"]
        want = [[-half, base - FOOTPRINT[1]], [half, base - FOOTPRINT[1]], [half, base], [-half, base]]
        check("rocks as tiles: the footprint is stored as one collision polygon per tile, with the framework's corners", tiles["polygons_per_tile"] == [1] * len(tiles["polygons_per_tile"])
              and tiles["polygon_points"] == want, str(tiles["polygon_points"]))
        sprites = observed["sprite_objects"]
        check("rocks as sprites: each rock is placed at its exact pixel position", sprites["positions"] == [[float(x), float(y)] for x, y in OBJECTS], str(sprites["positions"]))
        check("rocks as sprites: the holder is y-sorted", sprites["y_sort_enabled"] is True, "")
        error = max(max(abs(x - (cx * cell[0] + cell[0] / 2)), abs(y - (cy * cell[1] + cell[1] / 2))) for (x, y), (cx, cy) in zip(OBJECTS, snapped))
        result = {"godot": observed["godot"], "command": " ".join(command[:1] + ["--headless", "--path", "<scratch project>", "--script", "res://verify_layered_map.gd"]),
                  "exit_status": run.returncode, "observed": observed, "framework": {"plans": {t: {"tiles": len(p["tiles"]), "empty": p["empty_positions"]} for t, p in plans.items()},
                                                                                       "snapping_error_px_max": error},
                  "checks": checks, "failed": [c["name"] for c in checks if not c["ok"]],
                  "not_observed": ["draw order of the y-sorted layers and sprites (nothing is rendered)", "how the pictures look", "the meaning of a tile's texture origin for placing a sprite by its pivot",
                                   "navigation", "performance with many objects", "other engine versions"]}
        (HERE / "output.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{len(checks)} checks, {len(result['failed'])} failed (Godot {observed['godot']}); a tile snaps a free position by up to {error:.1f} px")
        for name in result["failed"]:
            print("FAILED:", name)
        if args.keep:
            print("scratch project kept at", proj)
        return 1 if result["failed"] else 0
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
