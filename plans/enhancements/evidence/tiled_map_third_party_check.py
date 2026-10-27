#!/usr/bin/env python3
"""Does an independent reader of Tiled's JSON map format accept the framework's exported layered map? (plan P16, evidence, not shipped)

  python plans/enhancements/evidence/tiled_map_third_party_check.py [--libs DIR]     (DIR holds `pip install --target DIR pytiled-parser`)

Builds a real layered map (three tilesets, a rock atlas, a 6 x 4 cell scene) with the framework's own tools, exports it with `export_exchange.py --layered-map`, and loads the
.tmj with pytiled-parser, a third-party reader of the Tiled map format. It prints what that reader found. This shows the file is well-formed JSON of the shape such a reader
expects; it does NOT show that Tiled itself opens it (Tiled was not run) or how it looks.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--libs", type=Path)
ARGS = parser.parse_args()
if ARGS.libs:
    sys.path.insert(0, str(ARGS.libs))
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

import export_exchange as exchange  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402
import gamearts_testkit as kit  # noqa: E402
import test_layered_map as fixtures  # noqa: E402


def main():
    work = Path(tempfile.mkdtemp(prefix="gamearts-tiled-check-"))
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
    objects = [{"id": "rock_a", "class": "prop", "sprite": {"atlas": "rocks.atlas.json", "frame": "S0"}, "position_px": [20, 20], "footprint_px": [8, 8], "collision": "footprint"}]
    path, _ = layered.build(work / "scene.png", terrains, (fixtures.CELL, fixtures.CELL), "shore", built, objects=objects)
    tmj = exchange.export_layered_map(path)
    result = {"file": tmj.name, "bytes": tmj.stat().st_size}
    try:
        import pytiled_parser
        parsed = pytiled_parser.parse_map(tmj)
        result["reader"] = "pytiled-parser"
        result["loaded"] = {"map_size": [parsed.map_size.width, parsed.map_size.height], "tile_size": [parsed.tile_size.width, parsed.tile_size.height],
                            "layers": [layer.name for layer in parsed.layers], "tileset_first_gids": sorted(parsed.tilesets),
                            "tile_layer_offsets": {layer.name: [layer.offset.x, layer.offset.y] for layer in parsed.layers if hasattr(layer, "data")},
                            "tile_layer_non_empty_cells": {layer.name: sum(1 for row in layer.data for value in row if value) for layer in parsed.layers if hasattr(layer, "data")},
                            "object_layer_sizes": {layer.name: len(layer.tiled_objects) for layer in parsed.layers if hasattr(layer, "tiled_objects")}}
        result["accepted"] = True
    except ImportError:
        result["accepted"] = None
        result["note"] = "pytiled-parser is not installed (pip install --target DIR pytiled-parser, then --libs DIR); nothing was checked"
    except Exception as exc:  # the reader's own refusal is the finding, so it is reported, not hidden
        result["accepted"] = False
        result["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
    print(json.dumps(result, indent=1))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
