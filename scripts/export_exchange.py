#!/usr/bin/env python3
"""Write a sheet's or a tileset's data in the JSON shapes other tools read.

  python scripts/export_exchange.py --atlas SHEET.atlas.json [--format aseprite-array|aseprite-hash] [--output FILE]
  python scripts/export_exchange.py --tileset NAME.tileset.json [--format tiled] [--output FILE]
  python scripts/export_exchange.py --layered-map NAME.layered_map.json [--format tiled] [--output FILE]

aseprite-array / aseprite-hash: the data file Aseprite writes beside a sprite sheet (`frames` as a list or as an object keyed by frame name, and
`meta`). Field names and meanings follow the exporter's own source (doc_exporter.cpp, read 2026-10-24): `frame` is the rectangle to cut from the
sheet, `spriteSourceSize` where that rectangle sat inside the source picture, `sourceSize` the source picture, `frameTags` the tags, with `repeat`
written as a string only when above zero. Two additions come from this framework: `pivot` (as a fraction of the source picture, the way many atlas formats
store a pivot) and `meta.key_colour`, because the sheet is delivered over the key colour and a reader must remove it.
tiled: a Tiled tileset (`type: "tileset"`, an image tileset on a regular grid) with a wang set for the layouts that have neighbour rules. The
extension .tsj is the one third-party Tiled readers use for JSON tilesets; the format level written (`version`, `tiledversion`) is the level of the
documentation the fields were taken from, not a release that was run.
tiled map (from a layered map): a Tiled map (`.tmj`) of the whole scene. Every layer of the map becomes a Tiled layer in the same order: the ground and one overlay per further
terrain as tile layers (the overlays are dual grids, so each is offset by half a cell and the map is one cell wider and taller than the scene), the objects as tile objects whose
position is the sprite's pivot, sorted by their y, and a `collision` object layer of the footprints that block. The terrain tilesets and the object atlas are embedded, so the file
needs only the pictures beside it. The gameplay grid is a map property. Tiled's own tile-object alignment (bottom left) is why an object's y is the bottom of its picture.
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
import gamearts_layered_map as layered  # noqa: E402
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


def _embedded_tileset(directory, tileset_file, first_gid):
    """A terrain's tileset, embedded in the map with its first global tile id."""
    tileset_path = Path(directory) / tileset_file
    tileset = common.read_json(tileset_path)
    atlas = common.read_json(tileset_path.with_name(Path(tileset["atlas"]).name))
    return dict(tiled_tileset(tileset, atlas), firstgid=first_gid), tileset


def _object_tileset(directory, atlas_file, first_gid):
    """An object atlas as a Tiled tileset of images: one tile per frame, each cut from the sheet by its rectangle, so any layout works."""
    atlas = common.read_json(Path(directory) / atlas_file)
    width, height = atlas["image_size"]
    tiles = [{"id": index, "image": atlas["image"], "imagewidth": width, "imageheight": height,
              "x": frame["rect"][0], "y": frame["rect"][1], "width": frame["rect"][2], "height": frame["rect"][3]} for index, frame in enumerate(atlas["frames"])]
    data = {"type": "tileset", "version": TILED_FORMAT, "tiledversion": TILED_LEVEL, "name": Path(atlas_file).name.replace(".atlas.json", ""), "firstgid": first_gid,
            "tilewidth": max(f["rect"][2] for f in atlas["frames"]), "tileheight": max(f["rect"][3] for f in atlas["frames"]), "tilecount": len(tiles), "columns": 0,
            "margin": 0, "spacing": 0, "objectalignment": "unspecified", "tiles": tiles}
    if atlas.get("mask_color") and not atlas.get("full_bleed"):
        data["transparentcolor"] = atlas["mask_color"].lower()
    return data, atlas


def tiled_map(map_path):
    """The Tiled map of a layered map. Refuses a map that fails its own checks or a terrain that names no tileset."""
    map_path = Path(map_path)
    problems = layered.validate(map_path)
    if problems:
        raise ValueError("cannot export a layered map that fails its own checks: " + "; ".join(problems[:3]))
    data = layered.load(map_path)
    directory = map_path.parent
    cell_w, cell_h = data["grid"]["cell_px"]
    width, height = data["grid"]["width"] + 1, data["grid"]["height"] + 1  # a dual grid has a tile at each corner of the cells
    base = min(data["terrains"], key=lambda t: t["priority"])["id"]
    tilesets, first, firsts, sets = [], 1, {}, {}
    for entry in sorted(data["terrains"], key=lambda t: t["priority"]):
        if "tileset" not in entry:
            raise ValueError(f"terrain {entry['id']} names no tileset, so there is nothing to draw it with")
        embedded, tileset = _embedded_tileset(directory, entry["tileset"], first)
        tilesets.append(embedded)
        firsts[entry["id"]], sets[entry["id"]] = first, tileset
        first += embedded["tilecount"]
    layers, next_id = [], 1
    for layer in data["layers"]:
        if layer["role"] in ("ground", "overlay"):
            terrain_id = layer["terrain"]
            cells = [0] * (width * height)
            if layer["role"] == "ground":
                tile_id = sets[terrain_id]["tiles"][0]["id"]
                for y in range(data["grid"]["height"]):
                    for x in range(data["grid"]["width"]):
                        cells[y * width + x] = firsts[terrain_id] + tile_id
                offsets = {}
            else:
                for (x, y), tile_id in layered.overlay_plan(data, directory, terrain_id)["tiles"].items():
                    cells[y * width + x] = firsts[terrain_id] + tile_id
                offsets = {"offsetx": -cell_w / 2, "offsety": -cell_h / 2}
            layers.append(dict({"id": next_id, "name": layer["id"], "type": "tilelayer", "width": width, "height": height, "x": 0, "y": 0, "opacity": 1, "visible": True,
                                "data": cells}, **offsets))
            next_id += 1
    objects_by_layer = {"objects": [o for o in data["objects"] if o.get("layer", "objects") == "objects"], "overhead": [o for o in data["objects"] if o.get("layer") == "overhead"]}
    object_ids = 0
    if data["objects"]:
        atlases = sorted({o["sprite"]["atlas"] for o in data["objects"]})
        atlas_info = {}
        for atlas_file in atlases:
            object_set, atlas = _object_tileset(directory, atlas_file, first)
            tilesets.append(object_set)
            atlas_info[atlas_file] = (first, {f["name"]: (i, f) for i, f in enumerate(atlas["frames"])})
            first += object_set["tilecount"]
    for layer in data["layers"]:
        if layer["role"] not in ("objects", "overhead"):
            continue
        placed = []
        for obj in objects_by_layer[layer["role"]]:
            object_ids += 1
            first_gid, frames = atlas_info[obj["sprite"]["atlas"]]
            index, frame = frames[obj["sprite"]["frame"]]
            pivot_x, pivot_y = frame["pivot"]
            frame_w, frame_h = frame["rect"][2], frame["rect"][3]
            entry = {"id": object_ids, "name": obj["id"], "type": obj["class"], "gid": first_gid + index, "x": obj["position_px"][0] - pivot_x,
                     "y": obj["position_px"][1] - pivot_y + frame_h, "width": frame_w, "height": frame_h, "rotation": 0, "visible": True}
            if obj.get("sort_offset_px"):
                entry["properties"] = [{"name": "sort_offset_px", "type": "int", "value": obj["sort_offset_px"]}]
            placed.append(entry)
        layers.append({"id": next_id, "name": layer["id"], "type": "objectgroup", "draworder": "topdown", "x": 0, "y": 0, "opacity": 1, "visible": True, "objects": placed})
        next_id += 1
    blockers = []
    for obj in data["objects"]:
        if obj.get("collision") == "footprint":
            left, top, right, bottom = layered._footprint(obj)
            object_ids += 1
            blockers.append({"id": object_ids, "name": obj["id"], "type": "footprint", "x": left, "y": top, "width": right - left, "height": bottom - top, "rotation": 0, "visible": True})
    layers.append({"id": next_id, "name": "collision", "type": "objectgroup", "draworder": "topdown", "x": 0, "y": 0, "opacity": 1, "visible": True, "objects": blockers})
    return {"type": "map", "version": TILED_FORMAT, "tiledversion": TILED_LEVEL, "orientation": "orthogonal", "renderorder": "right-down", "width": width, "height": height,
            "tilewidth": cell_w, "tileheight": cell_h, "infinite": False, "nextlayerid": next_id + 1, "nextobjectid": object_ids + 1, "layers": layers, "tilesets": tilesets,
            "properties": [{"name": "name", "type": "string", "value": data["name"]}, {"name": "base_terrain", "type": "string", "value": base},
                           {"name": "gameplay", "type": "string", "value": "\n".join(layered.gameplay_grid(data))},
                           {"name": "dual_grid_note", "type": "string", "value": "overlay layers are offset by half a cell: a tile sits where four cells meet"}]}


def export_layered_map(map_path, output=None):
    """Write the Tiled map of a layered map; returns the path written."""
    map_path = Path(map_path)
    data = tiled_map(map_path)
    name = common.read_json(map_path)["name"]
    return _write(output or map_path.with_name(name + ".tmj"), data)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--atlas", type=Path)
    source.add_argument("--tileset", type=Path)
    source.add_argument("--layered-map", type=Path)
    parser.add_argument("--format", help="aseprite-array (default), aseprite-hash, or tiled for a tileset")
    parser.add_argument("--frame-names", choices=FRAME_NAMES, default="name", help="name each frame by its own name (default) or by its frame number (some loaders find a tag's frames by number)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.atlas:
            written = export_atlas(args.atlas, args.format or "aseprite-array", args.output, args.frame_names)
        elif args.layered_map:
            if args.format not in (None, "tiled"):
                raise ValueError(f"Unknown format {args.format!r} for a layered map; the map format is tiled")
            written = export_layered_map(args.layered_map, args.output)
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
