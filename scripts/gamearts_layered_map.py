#!/usr/bin/env python3
"""Layered maps: a scene read as terrain layers and static objects (plan P16). The one owner of what a layered map is and when it is consistent.

  python scripts/gamearts_layered_map.py build --image SCENE.png --terrains terrains.json --cell 16x16 --name NAME --output-dir DIR [--objects objects.json] [--min-region N]
  python scripts/gamearts_layered_map.py validate MAP.layered_map.json
  python scripts/gamearts_layered_map.py overlay MAP.layered_map.json --terrain ID      # the tile each position of that overlay uses, and any it lacks
  python scripts/gamearts_layered_map.py gameplay MAP.layered_map.json                  # '.' walkable, '#' blocked, derived from the terrains and the objects' footprints
  python scripts/gamearts_layered_map.py plan MAP.layered_map.json [--write-jobs DIR] [--scene SCENE.png --swatches DIR]
                                                                                          # which tilesets the map still needs, a job skeleton for each, and the cleanest crop of each terrain
  python scripts/gamearts_layered_map.py mask --size WxH --boxes boxes.json --output mask.png    # an occlusion mask from measured regions

The map is engine-neutral data. It names a terrain label for every cell, the draw order (a base ground, then one overlay per further terrain by priority,
then objects, overhead objects and a gameplay layer), and the objects with the atlas frame that draws each. It does not build an engine scene: that belongs
to the game project, which reads this file. Objects are SUPPLIED (from the approved mockup's analysis or an external segmenter's masks); a measured test
showed blind colour-based object detection is not reliable, so this tool does not guess them. The label reader is in `gamearts_terrain.py`.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_terrain as terrain  # noqa: E402
import gamearts_tileset as tile_rules  # noqa: E402

SUFFIX = ".layered_map.json"
BASE_LAYOUTS = ("single", "variants")
OVERLAY_LAYOUT = "dual_grid_16"


def map_name(name):
    return name + SUFFIX


def _terrain_problems(terrains):
    problems = []
    for key in ("id", "symbol", "priority"):
        values = [t[key] for t in terrains]
        if len(set(values)) != len(values):
            problems.append(f"two terrains share a {key}")
    return problems


def layers_for(terrains, objects):
    """The layer stack a map with these terrains and objects has, back to front: the base ground, an overlay per further terrain in priority order, the
    objects, the overhead objects when there are any, and the gameplay layer."""
    ordered = sorted(terrains, key=lambda t: t["priority"])
    layers = [{"id": f"ground_{ordered[0]['id']}", "role": "ground", "terrain": ordered[0]["id"]}]
    layers += [{"id": f"overlay_{t['id']}", "role": "overlay", "terrain": t["id"]} for t in ordered[1:]]
    layers.append({"id": "objects", "role": "objects"})
    if any(o.get("layer") == "overhead" for o in objects):
        layers.append({"id": "overhead", "role": "overhead"})
    layers.append({"id": "gameplay", "role": "gameplay"})
    return layers


def build(image_path, terrains, cell_px, name, output_dir, min_region=1, objects=None, occluders=None, occlusion_mask=None, solid_mask=None):
    """Read the scene into a layered map file; returns (path, the map). `occluders` name the things drawn on top of the ground (trees, roofs, characters) by their sample
    colours, so the cells they cover take the terrain of the nearest visible ground and are recorded as inferred. Nothing is overwritten and a map that fails its own
    check is not left behind. `occlusion_mask` is a picture the size of the scene, white where an object lies (from the scene's analysis or a segmenter): the cells it
    covers are hidden whatever their colour, together with those the colour occluders find. `solid_mask` is the same kind of picture for solid structures (buildings, walls):
    its cells are hidden too, and they also block movement; the terrain under them is inferred, not seen."""
    from PIL import Image
    image_path, output_dir = Path(image_path), Path(output_dir)
    objects = list(objects or [])
    problems = _terrain_problems(terrains)
    if problems:
        raise ValueError("; ".join(problems))
    if min_region < 1:
        raise ValueError("the smallest region kept must be at least 1 cell (1 changes nothing)")
    with Image.open(image_path) as opened:
        read = terrain.read_labels(opened, terrains, tuple(cell_px), occluders=occluders or ())
        size = opened.size
    mask_hash, solid_hash, solid = None, None, set()
    if solid_mask is not None:
        with Image.open(solid_mask) as picture:
            if picture.size != size:
                raise ValueError(f"the solid mask is {picture.size[0]} x {picture.size[1]} and the scene is {size[0]} x {size[1]}; they must be the same size")
            solid = terrain.cells_from_mask(picture, tuple(cell_px))
        for x, y in solid:
            read["labels"][y][x] = len(terrains)
        solid_hash = common.sha256_file(solid_mask)
    if occlusion_mask is not None:
        with Image.open(occlusion_mask) as mask:
            if mask.size != size:
                raise ValueError(f"the occlusion mask is {mask.size[0]} x {mask.size[1]} and the scene is {size[0]} x {size[1]}; they must be the same size")
            for x, y in terrain.cells_from_mask(mask, tuple(cell_px)):
                read["labels"][y][x] = len(terrains)  # an occluder: its ground is filled in from the nearest visible ground
        mask_hash = common.sha256_file(occlusion_mask)
    seen, occluded = terrain.fill_occluded(read["labels"], len(terrains))
    labels, changes = terrain.area_open(seen, min_region)
    symbols = [t["symbol"] for t in terrains]
    data = {"schema_version": "1.0", "name": name, "grid": {"width": len(labels[0]), "height": len(labels), "cell_px": list(cell_px)},
            "terrains": [dict(t) for t in terrains], "labels": terrain.encode_rows(labels, symbols), "layers": layers_for(terrains, objects), "objects": objects,
            "source": {"image": image_path.name, "image_sha256": common.sha256_file(image_path),
                       "read": {"method": "nearest_palette_colour_of_cell_median", "unclassified_cells": [list(c) for c in read["unclassified"]],
                                "area_opening_minimum": min_region, "cells_changed": sum(len(c["cells"]) for c in changes),
                                "occluded_cells": [list(c) for c in occluded], **({"occlusion_mask_sha256": mask_hash} if mask_hash else {}),
                                **({"solid_cells": [list(c) for c in sorted(solid, key=lambda c: (c[1], c[0]))], "solid_mask_sha256": solid_hash} if solid_hash else {})}},
            "validation": {"geometry": "generated_from_scene", "engine_validation": "not_tested"}}
    target = output_dir / map_name(name)
    if target.exists():
        raise FileExistsError(f"{target.name} already exists; choose a new name")
    output_dir.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(target, data)
    found = validate(target)
    if found:
        target.unlink()
        raise ValueError("the map does not hold together: " + "; ".join(found[:3]))
    return target, data


def load(path):
    data = common.read_json(path)
    common.validate_schema(data, "gamearts-layered-map")
    return data


def labels_of(data):
    return terrain.decode_rows(data["labels"], [t["symbol"] for t in data["terrains"]])


def _tileset(directory, data, terrain_id):
    """The tileset file of a terrain, as data, or None when the terrain names none."""
    entry = next(t for t in data["terrains"] if t["id"] == terrain_id)
    if "tileset" not in entry:
        return None, entry
    return common.read_json(Path(directory) / entry["tileset"]), entry


def overlay_plan(data, directory, terrain_id):
    """For one overlay: the atlas tile id each display position uses, how many positions need no tile, and the positions whose tile the tileset lacks."""
    tileset, entry = _tileset(directory, data, terrain_id)
    if tileset is None:
        raise ValueError(f"terrain {terrain_id} names no tileset")
    labels = labels_of(data)
    priorities = [t["priority"] for t in data["terrains"]]
    index = next(i for i, t in enumerate(data["terrains"]) if t["id"] == terrain_id)
    terrains = tileset["terrains"]
    by_identity = {tile_rules.identity(tileset["layout"], tile.get("neighbours", {}), terrains): tile["id"] for tile in tileset["tiles"]}
    tiles, missing, empty = {}, [], 0
    for position, corners in terrain.overlay_corners(terrain.covered(labels, priorities, index)).items():
        if not any(corners):
            empty += 1
            continue
        neighbours = {side: (terrains[0] if on else terrains[1]) for side, on in zip(("top_left", "top_right", "bottom_right", "bottom_left"), corners)}  # the pieces are made of terrains[0]
        found = by_identity.get(tile_rules.identity(tileset["layout"], neighbours, terrains))
        if found is None:
            missing.append({"position": list(position), "needs": tile_rules.tile_name(tileset["layout"], neighbours, terrains)})
        else:
            tiles[position] = found
    return {"tiles": tiles, "empty_positions": empty, "missing": missing}


def _footprint(obj):
    x, y = obj["position_px"]
    w, h = obj["footprint_px"]
    left = x - w // 2
    return (left, y - h, left + w, y)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def gameplay_grid(data):
    """Rows of '.' (walkable) and '#' (blocked): a cell is blocked when its terrain is not walkable or an object with footprint collision stands on any of it."""
    walkable = [t["walkable"] for t in data["terrains"]]
    solid = {tuple(c) for c in data["source"]["read"].get("solid_cells", [])}
    cell_w, cell_h = data["grid"]["cell_px"]
    blockers = [_footprint(o) for o in data["objects"] if o.get("collision") == "footprint" and "footprint_px" in o]
    rows = []
    for y, row in enumerate(labels_of(data)):
        out = []
        for x, label in enumerate(row):
            cell = (x * cell_w, y * cell_h, (x + 1) * cell_w, (y + 1) * cell_h)
            out.append("." if walkable[label] and (x, y) not in solid and not any(_overlap(cell, b) for b in blockers) else "#")
        rows.append("".join(out))
    return rows


def _object_problems(data, directory):
    problems = []
    cell_w, cell_h = data["grid"]["cell_px"]
    width_px, height_px = data["grid"]["width"] * cell_w, data["grid"]["height"] * cell_h
    ids = [o["id"] for o in data["objects"]]
    if len(set(ids)) != len(ids):
        problems.append("two objects share an id")
    atlases = {}
    for obj in data["objects"]:
        x, y = obj["position_px"]
        if not (0 <= x <= width_px and 0 <= y <= height_px):
            problems.append(f"object {obj['id']}: position {obj['position_px']} lies outside the {width_px} x {height_px} map")
        path = Path(directory) / obj["sprite"]["atlas"]
        if str(path) not in atlases:
            atlases[str(path)] = {f["name"] for f in common.read_json(path)["frames"]} if path.is_file() else None
        names = atlases[str(path)]
        if names is None:
            problems.append(f"object {obj['id']}: atlas {obj['sprite']['atlas']} is missing")
        elif obj["sprite"]["frame"] not in names:
            problems.append(f"object {obj['id']}: the atlas has no frame named {obj['sprite']['frame']}")
        if obj.get("collision") == "footprint" and "footprint_px" not in obj:
            problems.append(f"object {obj['id']}: collision is footprint but no footprint_px is given")
        if "footprint_px" in obj:
            left, top, right, bottom = _footprint(obj)
            if left < 0 or top < 0 or right > width_px or bottom > height_px:
                problems.append(f"object {obj['id']}: its footprint {[left, top, right, bottom]} runs outside the map")
    placed = [(o, _footprint(o)) for o in data["objects"] if "footprint_px" in o and not o.get("allow_overlap")]
    buckets = {}
    for index, (obj, box) in enumerate(placed):
        for bx in range(box[0] // 64, box[2] // 64 + 1):
            for by in range(box[1] // 64, box[3] // 64 + 1):
                buckets.setdefault((bx, by), []).append(index)
    reported = set()
    for members in buckets.values():
        for i, first in enumerate(members):
            for second in members[i + 1:]:
                if (first, second) not in reported and _overlap(placed[first][1], placed[second][1]):
                    reported.add((first, second))
                    problems.append(f"objects {placed[first][0]['id']} and {placed[second][0]['id']} overlap on the ground (set allow_overlap if they are meant to touch)")
    return problems


def validate(path):
    """Everything wrong with a layered map, in words; an empty list means it holds together. It does not judge the art or any engine's behaviour."""
    path = Path(path)
    try:
        data = load(path)
    except (OSError, ValueError) as exc:
        return [f"layered map contract: {exc}"]
    problems = _terrain_problems(data["terrains"])
    symbols = [t["symbol"] for t in data["terrains"]]
    try:
        labels = terrain.decode_rows(data["labels"], symbols)
    except ValueError as exc:
        return problems + [f"labels: {exc}"]
    if (len(labels[0]), len(labels)) != (data["grid"]["width"], data["grid"]["height"]):
        problems.append(f"the grid says {data['grid']['width']} x {data['grid']['height']} cells and the labels hold {len(labels[0])} x {len(labels)}")
    if data["layers"] != layers_for(data["terrains"], data["objects"]):
        problems.append("the layers are not the stack these terrains and objects make (base ground, overlays in priority order, objects, overhead if any, gameplay)")
    base = min(data["terrains"], key=lambda t: t["priority"])["id"]
    for entry in data["terrains"]:
        if "tileset" not in entry:
            continue
        file = path.parent / entry["tileset"]
        if not file.is_file():
            problems.append(f"terrain {entry['id']}: tileset {entry['tileset']} is missing")
            continue
        try:
            tileset = common.read_json(file)
            common.validate_schema(tileset, "gamearts-tileset")
        except ValueError as exc:
            problems.append(f"terrain {entry['id']}: tileset {entry['tileset']}: {exc}")
            continue
        wanted = BASE_LAYOUTS if entry["id"] == base else (OVERLAY_LAYOUT,)
        if tileset["layout"] not in wanted:
            problems.append(f"terrain {entry['id']}: its tileset is {tileset['layout']}, and this terrain needs {' or '.join(wanted)}")
        elif entry["id"] != base and (len(tileset["terrains"]) != 2 or tileset["terrains"][0] != entry["id"]):
            problems.append(f"terrain {entry['id']}: its overlay tileset must list {entry['id']} (what its pieces are made of) first and the terrain around it second, not {tileset['terrains']}")
        if list(tileset["tile_size"]) != list(data["grid"]["cell_px"]):
            problems.append(f"terrain {entry['id']}: its tiles are {tileset['tile_size']} and the grid's cells are {data['grid']['cell_px']}")
        problems += [f"terrain {entry['id']}: {p}" for p in validate_tileset_problems(file)]
        if entry["id"] != base and tileset["layout"] == OVERLAY_LAYOUT and tileset["terrains"][0] == entry["id"]:
            plan = overlay_plan(data, path.parent, entry["id"])
            problems += [f"overlay {entry['id']}: no tile for position {m['position']} ({m['needs']})" for m in plan["missing"][:3]]
    problems += _object_problems(data, path.parent)
    return problems


def validate_tileset_problems(file):
    import validate_tileset
    return validate_tileset.validate(file, check_sheet=False)  # the technical gate checks each sheet; this is the labels and structure


BELOW = "below"  # what lies around an overlay's pieces: the terrain beneath, whatever it is


def mask_command(size, boxes_file, output):
    """Write an occlusion mask picture from a JSON list of measured boxes; never overwrites."""
    output = Path(output)
    if output.exists():
        raise ValueError(f"{output.name} already exists; a mask is never overwritten")
    mask = terrain.mask_from_boxes(size, common.read_json(boxes_file))
    output.parent.mkdir(parents=True, exist_ok=True)
    mask.save(output)
    return {"written": output.name, "boxes": len(common.read_json(boxes_file)), "white_share": round(mask.tobytes().count(255) / (size[0] * size[1]), 3)}


def swatches(data, scene_path, directory):
    """The cleanest crop of each terrain: the biggest square of cells read as that terrain with nothing hidden or doubtful, cut from the scene, as a reference picture to
    make the terrain's tiles from. A terrain with no such cell says so."""
    from PIL import Image
    labels = labels_of(data)
    cell_w, cell_h = data["grid"]["cell_px"]
    read = data["source"]["read"]
    unsure = {tuple(c) for c in read["occluded_cells"]} | {tuple(c) for c in read["unclassified_cells"]}  # solid cells are among the occluded
    directory = Path(directory)
    out = {}
    with Image.open(scene_path) as scene:
        if scene.size != (data["grid"]["width"] * cell_w, data["grid"]["height"] * cell_h):
            raise ValueError("the scene picture is not the size of the map's grid; pass the picture the map was built from (a cropped copy keeps the grid)")
        for index, entry in enumerate(data["terrains"]):
            clean = [[labels[y][x] == index and (x, y) not in unsure for x in range(len(labels[0]))] for y in range(len(labels))]
            found = terrain.largest_square(clean)
            if found is None:
                out[entry["id"]] = {"file": None, "why": "no cell of this terrain was read in plain view"}
                continue
            x, y, size = found
            target = directory / f"{entry['id']}_swatch.png"
            if target.exists():
                raise ValueError(f"{target.name} already exists; a swatch is never overwritten")
            directory.mkdir(parents=True, exist_ok=True)
            scene.crop((x * cell_w, y * cell_h, (x + size) * cell_w, (y + size) * cell_h)).save(target)
            out[entry["id"]] = {"file": target.name, "cells": [x, y, size], "pixels": [size * cell_w, size * cell_h]}
    return out


def plan(path, jobs_dir=None, scene=None, swatch_dir=None):
    """The tilesets a map needs and where each stands. For every terrain: the layout it needs (single for the base ground, dual_grid_16 for an overlay), the terrains
    the tileset lists (an overlay lists itself first and BELOW second), the tile size, how many pictures that is, and whether the file named is missing, invalid or
    present. With `jobs_dir`, a tileset job skeleton is written for each tileset that is not present: one entry per tile with its labels and a picture name to fill in
    (an existing file is never overwritten). The art itself is made elsewhere; this says exactly what to ask for."""
    path = Path(path)
    data = load(path)
    base = min(data["terrains"], key=lambda t: t["priority"])["id"]
    cell = list(data["grid"]["cell_px"])
    needs = []
    for entry in sorted(data["terrains"], key=lambda t: t["priority"]):
        overlay = entry["id"] != base
        layout, terrains = (OVERLAY_LAYOUT, [entry["id"], BELOW]) if overlay else ("single", [entry["id"]])
        tiles = tile_rules.layout_tiles(layout, terrains)
        item = {"terrain": entry["id"], "role": "overlay" if overlay else "ground", "layout": layout, "terrains": terrains, "tile_size": cell,
                "pictures": len(tiles), "tileset": entry.get("tileset")}
        if overlay:
            item["note"] = "the tile with no overlay in any corner is never drawn, but the layout requires it; make it blank"
        if not entry.get("tileset"):
            item["status"] = "missing"
        elif not (path.parent / entry["tileset"]).is_file():
            item["status"] = "missing"
        else:
            found = validate_tileset_problems(path.parent / entry["tileset"])
            item["status"] = "invalid" if found else "present"
            if found:
                item["problems"] = found[:5]
        item["tiles"] = [{"picture": f"{entry['id']}_{index:02d}.png", "describes": tile_rules.tile_name(layout, tile["neighbours"], terrains), "neighbours": tile["neighbours"]}
                         for index, tile in enumerate(tiles)] if item["status"] != "present" else []
        needs.append(item)
        if jobs_dir and item["status"] != "present":
            target = Path(jobs_dir) / f"{entry['id']}_tileset_job.json"
            if target.exists():
                raise ValueError(f"{target.name} already exists; a job skeleton is never overwritten")
            job = {"name": f"{entry['id']}_tileset", "tile_size": cell, "layout": layout, "terrains": terrains,
                   "tiles": [dict({"file": tile["picture"]}, **({"neighbours": tile["neighbours"]} if layout not in ("single", "variants") else {})) for tile in item["tiles"]]}
            Path(jobs_dir).mkdir(parents=True, exist_ok=True)
            common.atomic_write_json(target, job)
            item["job"] = target.name
    read = data["source"]["read"]
    crops = swatches(data, scene, swatch_dir) if (scene and swatch_dir) else None
    if crops:
        for item in needs:
            item["reference_swatch"] = crops[item["terrain"]]
    return {"map": data["name"], "tilesets": needs, "ready": all(n["status"] == "present" for n in needs),
            "uncertain": {"unclassified_cells": len(read["unclassified_cells"]), "occluded_cells": len(read["occluded_cells"]), "solid_cells": len(read.get("solid_cells", []))},
            "next": "make the pictures named under `tiles`, build each tileset with build_tileset.py, name it in the map's terrains, then validate the map"}


def _size(text):
    try:
        width, height = (int(part) for part in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, for example 16x16") from None
    return width, height


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("build")
    one.add_argument("--image", type=Path, required=True)
    one.add_argument("--terrains", type=Path, required=True, help="JSON list of {id, symbol, colour, priority, walkable, tileset?}")
    one.add_argument("--cell", type=_size, required=True)
    one.add_argument("--name", required=True)
    one.add_argument("--output-dir", type=Path, required=True)
    one.add_argument("--objects", type=Path)
    one.add_argument("--min-region", type=int, default=1)
    one.add_argument("--solid-mask", type=Path, help="like --occlusion-mask, for solid structures (buildings, walls): their cells also block movement")
    one.add_argument("--occlusion-mask", type=Path, help="a picture the size of the scene, white where an object lies (a segmenter's output or regions measured from the scene)")
    one.add_argument("--occluders", type=Path, help="JSON list of {id, colours} for what is drawn over the ground (trees, roofs, characters)")
    for name in ("validate", "overlay", "gameplay", "plan"):
        sub = ops.add_parser(name)
        sub.add_argument("map", type=Path)
        if name == "overlay":
            sub.add_argument("--terrain", required=True)
        if name == "plan":
            sub.add_argument("--write-jobs", type=Path, help="a folder to write a tileset job skeleton into for each tileset still to make")
            sub.add_argument("--scene", type=Path, help="the picture the map was read from (with --swatches)")
            sub.add_argument("--swatches", type=Path, help="a folder to write the cleanest crop of each terrain into, as a reference for making its tiles")
    mask = ops.add_parser("mask")
    mask.add_argument("--size", type=_size, required=True, help="the scene's size in pixels, WIDTHxHEIGHT")
    mask.add_argument("--boxes", type=Path, required=True, help="JSON list of [x, y, width, height] (or {box: [...]}) for each measured object")
    mask.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "build":
            path, data = build(args.image, common.read_json(args.terrains), args.cell, args.name, args.output_dir, args.min_region,
                               common.read_json(args.objects) if args.objects else None, common.read_json(args.occluders) if args.occluders else None, args.occlusion_mask, args.solid_mask)
            result = {"written": path.name, "cells": [data["grid"]["width"], data["grid"]["height"]], "layers": [layer["id"] for layer in data["layers"]],
                      "unclassified_cells": len(data["source"]["read"]["unclassified_cells"]), "cells_changed": data["source"]["read"]["cells_changed"],
                      "occluded_cells": len(data["source"]["read"]["occluded_cells"])}
        elif args.operation == "validate":
            found = validate(args.map)
            result = {"status": "failed" if found else "passed", "problems": found,
                      "not_assessed": "the art, and how any engine draws these layers (engine_validation: not_tested)"}
            print(json.dumps(result, indent=2))
            return 1 if found else 0
        elif args.operation == "overlay":
            plan = overlay_plan(load(args.map), args.map.parent, args.terrain)
            result = {"tiles": len(plan["tiles"]), "empty_positions": plan["empty_positions"], "missing": plan["missing"]}
        elif args.operation == "mask":
            result = mask_command(args.size, args.boxes, args.output)
        elif args.operation == "plan":
            result = plan(args.map, args.write_jobs, args.scene, args.swatches)
        else:
            result = {"gameplay": gameplay_grid(load(args.map))}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print("BLOCKED", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
