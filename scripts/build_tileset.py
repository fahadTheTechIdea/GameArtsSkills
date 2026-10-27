#!/usr/bin/env python3
"""Assemble supplied tile pictures into a sheet, an atlas and a tileset description.

  python scripts/build_tileset.py job.json --output-dir DIR

The job (schemas/gamearts-tileset-job.schema.json) names the tile size, the layout (gamearts_tileset.LAYOUTS), the terrains and, for each tile,
its picture and the terrain at each place around it. The tiles must make a complete set for the layout: a missing, repeated or impossible tile is
refused by name. The result is a regular grid of tile-sized cells with no spacing (so any tile editor can read it) in three files:
<name>.png and <name>.atlas.json from the one sheet builder, and <name>.tileset.json with the layout and labels. Nothing is overwritten and a failed
build leaves nothing behind. It cannot draw a tile: the pictures come from the approved art.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_sheet_atlas as sheets  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_tileset as rules  # noqa: E402

DEFAULT_COLUMNS = 8


def build(job, output_dir):
    """Build the three files; returns (sheet png, atlas, tileset) paths."""
    from PIL import Image
    common.validate_schema(job, "gamearts-tileset-job")
    output_dir, base, name = Path(output_dir), Path(job["_input_dir"]), job["name"]
    layout, terrains, (tile_w, tile_h) = job["layout"], job["terrains"], job["tile_size"]
    full_bleed = job.get("full_bleed", True)
    columns = min(job.get("columns", DEFAULT_COLUMNS), len(job["tiles"]))
    tiles = []
    for index, item in enumerate(job["tiles"]):
        neighbours = item.get("neighbours")
        if layout in ("single", "variants") and not neighbours:
            neighbours = {side: terrains[0] for side in rules.SIDES}
        tiles.append({"id": index, "terrain": item.get("terrain", terrains[0]),
                      "neighbours": {side: label for side, label in (neighbours or {}).items() if label is not None}})
    tileset = {"schema_version": "1.0", "name": name, "atlas": f"{name}.atlas.json", "tile_size": [tile_w, tile_h], "layout": layout,
               "terrains": terrains, "full_bleed": full_bleed, "columns": columns, "tiles": tiles}
    problems = rules.label_problems(tileset)
    if problems:
        raise ValueError("tileset: " + "; ".join(problems))
    for item in job["tiles"]:
        path = common.safe_member(base, item["file"], "tile file")
        if not path.is_file():
            raise ValueError(f"Missing tile file: {path}")
        with Image.open(path) as opened:
            if opened.size != (tile_w, tile_h):
                raise ValueError(f"{path.name} is {opened.width}x{opened.height}, but the tiles of this tileset are {tile_w}x{tile_h}")
    tileset_path = output_dir / f"{name}.tileset.json"
    if tileset_path.exists():
        raise FileExistsError("Output revision already exists; choose a new descriptive revision/name")
    sheet_job = {"_input_dir": str(base), "name": name, "asset_id": job.get("asset_id", name), "columns": columns, "padding": 0, "spacing": 0,
                 "full_bleed": full_bleed, "source_mockups": job.get("source_mockups", []),
                 "frames": [{"file": item["file"], "name": f"tile_{index:03d}", "pivot": [0, 0]} for index, item in enumerate(job["tiles"])]}
    png, atlas = sheets.build(sheet_job, output_dir)
    try:
        common.validate_schema(tileset, "gamearts-tileset")
        common.atomic_write_json(tileset_path, tileset)
    except BaseException:
        for leftover in (png, atlas, tileset_path):
            leftover.unlink(missing_ok=True)
        raise
    return png, atlas, tileset_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        job = json.loads(args.job.read_text(encoding="utf-8"))
        if not isinstance(job, dict):
            raise ValueError("The tileset job must be a JSON object")
        job["_input_dir"] = str(args.job.resolve().parent)
        png, atlas, tileset = build(job, args.output_dir.resolve())
        print(f"BUILT {png}, {atlas} and {tileset}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
