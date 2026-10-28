#!/usr/bin/env python3
"""Write a sheet's or a tileset's data in the JSON shapes other tools read.

  python scripts/export_exchange.py --atlas SHEET.atlas.json [--format aseprite-array|aseprite-hash] [--output FILE]
  python scripts/export_exchange.py --tileset NAME.tileset.json [--format tiled] [--output FILE]

aseprite-array / aseprite-hash: the data file Aseprite writes beside a sprite sheet (`frames` as a list or as an object keyed by frame name, and
`meta`). Field names and meanings follow the exporter's own source (doc_exporter.cpp, read 2026-10-24): `frame` is the rectangle to cut from the
sheet, `spriteSourceSize` where that rectangle sat inside the source picture, `sourceSize` the source picture, `frameTags` the tags, with `repeat`
written as a string only when above zero. Two additions come from this framework: `pivot` (as a fraction of the source picture, the way many atlas formats
store a pivot) and `meta.key_colour`, because the sheet is delivered over the key colour and a reader must remove it.
tiled: a Tiled tileset (`type: "tileset"`, an image tileset on a regular grid) with a wang set for the layouts that have neighbour rules. The
extension .tsj is the one third-party Tiled readers use for JSON tilesets; the format level written (`version`, `tiledversion`) is the level of the
documentation the fields were taken from, not a release that was run.
Compatibility is best effort until a real export has been opened in the tool. An atlas or tileset that fails its own checks is not exported, and an existing
file is never overwritten. The sheet itself is never changed.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_atlas as atlas_rules  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_tileset as tile_rules  # noqa: E402
import validate_sheet_atlas as sheet_validator  # noqa: E402
import validate_tileset as tileset_validator  # noqa: E402

APP = "Game Arts (scripts/export_exchange.py)"
EXCHANGE_VERSION = "1.0"
TILED_FORMAT = "1.10"  # the level of the Tiled format documentation the fields were taken from
TILED_LEVEL = "1.10.0"
WANG_COLOURS = ("#e6194b", "#4363d8")  # only how the editor shows the two terrains
WANG_TYPE = {"wang_corner_16": "corner", "dual_grid_16": "corner", "wang_edge_16": "edge", "blob_47": "mixed"}
NOTE = "Compatibility is best effort until a real export has been opened in the tool that reads it."


def _write(path, data):
    path = Path(path)
    if path.exists():
        raise ValueError(f"{path.name} already exists; an export never overwrites a file (choose another --output)")
    path.parent.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(path, data)
    return path


# ------------------------------------------------------------------------------------------------ Aseprite
def _aseprite_frame(frame):
    x, y, w, h = atlas_rules.image_rect(frame)
    kept_x, kept_y, kept_w, kept_h = atlas_rules.source_box(frame)
    size = frame.get("source_size") or [w, h]
    offset = frame.get("source_offset_in_cell", [0, 0])
    entry = {"frame": {"x": x, "y": y, "w": w, "h": h}, "rotated": False, "trimmed": bool(frame.get("trimmed", False)),
             "spriteSourceSize": {"x": kept_x, "y": kept_y, "w": kept_w, "h": kept_h}, "sourceSize": {"w": size[0], "h": size[1]},
             "duration": frame["duration_ms"],
             "pivot": {"x": (frame["pivot"][0] - offset[0]) / size[0], "y": (frame["pivot"][1] - offset[1]) / size[1]}}
    return entry


def _aseprite_meta(atlas):
    meta = {"app": APP, "version": EXCHANGE_VERSION, "image": atlas["image"], "format": "RGBA8888",
            "size": {"w": atlas["image_size"][0], "h": atlas["image_size"][1]}, "scale": "1", "key_colour": atlas["mask_color"]}
    if atlas.get("tags"):
        meta["frameTags"] = []
        for tag in atlas["tags"]:
            shown = {"name": tag["name"], "from": tag["from"], "to": tag["to"], "direction": tag["direction"]}
            if tag.get("repeat", 0) > 0:
                shown["repeat"] = str(tag["repeat"])
            meta["frameTags"].append(shown)
    return meta


FRAME_NAMES = ("name", "index")


def _filename(frame, names):
    """A frame's name in the file: its own name, or its frame number as text (what Aseprite writes for the item filename `{frame}`)."""
    return str(frame["index"]) if names == "index" else frame.get("name", f"frame_{frame['index']:03d}")


def aseprite_array(atlas, names="name"):
    return {"frames": [{"filename": _filename(frame, names), **_aseprite_frame(frame)} for frame in atlas["frames"]], "meta": _aseprite_meta(atlas)}


def aseprite_hash(atlas, names="name"):
    return {"frames": {_filename(frame, names): _aseprite_frame(frame) for frame in atlas["frames"]}, "meta": _aseprite_meta(atlas)}


ATLAS_FORMATS = {"aseprite-array": (aseprite_array, ".array.json"), "aseprite-hash": (aseprite_hash, ".hash.json")}


def export_atlas(atlas_path, kind="aseprite-array", output=None, names="name"):
    """Write the atlas in one of ATLAS_FORMATS; returns the path written. Refuses an atlas that fails its own checks. `names="index"` names every
    frame by its frame number, which loaders that find a tag's frames by number need."""
    if kind not in ATLAS_FORMATS:
        raise ValueError(f"Unknown format {kind!r}; the atlas formats are {', '.join(ATLAS_FORMATS)} and the tileset format is tiled")
    if names not in FRAME_NAMES:
        raise ValueError(f"Unknown frame naming {names!r}; use {' or '.join(FRAME_NAMES)}")
    atlas_path = Path(atlas_path)
    atlas = common.read_json(atlas_path)
    common.validate_schema(atlas, "gamearts-atlas")
    issues = sheet_validator.validate(atlas_path.with_name(Path(atlas["image"]).name), atlas_path)
    if issues:
        raise ValueError("cannot export an atlas that fails its own checks: " + "; ".join(issues[:3]))
    build, suffix = ATLAS_FORMATS[kind]
    return _write(output or atlas_path.with_name(atlas["name"] + suffix), build(atlas, names))


# ------------------------------------------------------------------------------------------------ Tiled
def _representative(tiles, layout, terrains, index):
    """The id of the tile made wholly of one terrain (Tiled's representative tile for a colour), or -1 when the layout has none."""
    for tile in tiles:
        if all(tile["neighbours"].get(side) == terrains[index] for side in tile_rules.USED[layout]):
            return tile["id"]
    return -1


def tiled_tileset(tileset, atlas):
    layout, terrains, tiles = tileset["layout"], tileset["terrains"], tileset["tiles"]
    tile_w, tile_h = tileset["tile_size"]
    columns = tileset.get("columns") or atlas.get("columns") or len(tiles)
    data = {"type": "tileset", "version": TILED_FORMAT, "tiledversion": TILED_LEVEL, "name": tileset["name"], "image": atlas["image"],
            "imagewidth": atlas["image_size"][0], "imageheight": atlas["image_size"][1], "tilewidth": tile_w, "tileheight": tile_h,
            "tilecount": len(tiles), "columns": columns, "margin": 0, "spacing": 0}
    if not tileset.get("full_bleed", True):
        data["transparentcolor"] = atlas["mask_color"].lower()
    data["properties"] = [{"name": "layout", "type": "string", "value": layout}, {"name": "terrains", "type": "string", "value": ", ".join(terrains)}]
    data["wangsets"] = []
    if layout in WANG_TYPE:
        data["wangsets"].append({
            "name": tileset["name"], "type": WANG_TYPE[layout], "tile": -1, "properties": [],
            "colors": [{"name": terrain, "color": WANG_COLOURS[i], "probability": 1, "tile": _representative(tiles, layout, terrains, i), "properties": []}
                       for i, terrain in enumerate(terrains)],
            "wangtiles": [{"tileid": tile["id"], "wangid": tile_rules.wang_id(layout, tile["neighbours"], terrains)} for tile in tiles]})
    return data


def export_tileset(tileset_path, output=None):
    """Write a Tiled tileset; returns the path written. Refuses a tileset that fails its own checks."""
    tileset_path = Path(tileset_path)
    issues = tileset_validator.validate(tileset_path)
    if issues:
        raise ValueError("cannot export a tileset that fails its own checks: " + "; ".join(issues[:3]))
    tileset = common.read_json(tileset_path)
    atlas = common.read_json(tileset_path.with_name(Path(tileset["atlas"]).name))
    return _write(output or tileset_path.with_name(tileset["name"] + ".tsj"), tiled_tileset(tileset, atlas))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--atlas", type=Path)
    source.add_argument("--tileset", type=Path)
    parser.add_argument("--format", help="aseprite-array (default), aseprite-hash, or tiled for a tileset")
    parser.add_argument("--frame-names", choices=FRAME_NAMES, default="name", help="name each frame by its own name (default) or by its frame number (some loaders find a tag's frames by number)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.atlas:
            written = export_atlas(args.atlas, args.format or "aseprite-array", args.output, args.frame_names)
        else:
            if args.format not in (None, "tiled"):
                raise ValueError(f"Unknown format {args.format!r} for a tileset; the tileset format is tiled")
            written = export_tileset(args.tileset, args.output)
        print(json.dumps({"written": str(written), "note": NOTE}, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
