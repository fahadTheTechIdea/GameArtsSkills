#!/usr/bin/env python3
"""Environment objects for a layered map: the props, fences, trees and plants of a scene cut out as sprites (plan P16).

  python scripts/gamearts_props.py extract --image SCENE.png --job props_job.json --name NAME --output-dir DIR

The job (schemas/gamearts-props-job.schema.json) lists classes of object, each a kind and a mask picture the size of the scene that is white where objects of that kind
lie (a segmenter's output, or regions measured from the approved scene). Each white connected region becomes one object: a sprite cut from the scene (everything else in
its box is the key colour), placed by its bottom-centre, with a footprint and collision from its kind. The sprites are packed into one atlas by the existing atlas builder.

It writes NAME.props.atlas.json + .png (the sprites), NAME.objects.json (the objects, for `gamearts_layered_map.py build --objects`; keep the atlas beside the map) and
NAME.occlusion.png (the union of the masks, for `--occlusion-mask`, so the ground read hides what these objects cover), and never overwrites any of them.

This is the environment only. The ground is the terrain read (`gamearts_terrain.py`); structures (buildings, walls of buildings) and characters are handled separately and
are refused here by kind, so the same pixels are not drawn twice. Nothing is guessed: a region is an object only because a mask says so, and the footprint rules below are
design choices, written into the output.
"""
import argparse
import json
import sys
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_sheet_atlas as atlas_builder  # noqa: E402
import gamearts_common as common  # noqa: E402

KEY = (255, 0, 255, 255)

# What each kind of environment object stands on. share: the footprint's width as a share of the sprite's width (a tree stands on its trunk, a fence on its whole length);
# depth_share and depth_min: the footprint's depth as a share of the sprite's height, at least depth_min pixels, at most the sprite's height; collision: whether it blocks
# walking; overlap: whether neighbours of the kind may touch (a fence's pieces do).
KINDS = {
    "tree": {"share": 0.3, "depth_share": 0.1, "depth_min": 4, "collision": "footprint", "overlap": False},
    "bush": {"share": 0.8, "depth_share": 0.4, "depth_min": 4, "collision": "footprint", "overlap": False},
    "hedge": {"share": 1.0, "depth_share": 0.4, "depth_min": 4, "collision": "footprint", "overlap": True},
    "fence": {"share": 1.0, "depth_share": 0.15, "depth_min": 3, "collision": "footprint", "overlap": True},
    "rock": {"share": 0.8, "depth_share": 0.5, "depth_min": 3, "collision": "footprint", "overlap": False},
    "lamp": {"share": 0.25, "depth_share": 0.1, "depth_min": 3, "collision": "footprint", "overlap": False},
    "bin": {"share": 0.8, "depth_share": 0.4, "depth_min": 3, "collision": "footprint", "overlap": False},
    "bench": {"share": 1.0, "depth_share": 0.4, "depth_min": 3, "collision": "footprint", "overlap": False},
    "sign": {"share": 0.3, "depth_share": 0.1, "depth_min": 3, "collision": "footprint", "overlap": False},
    "planter": {"share": 0.9, "depth_share": 0.5, "depth_min": 3, "collision": "footprint", "overlap": False},
    "flower": {"share": 0.8, "depth_share": 0.4, "depth_min": 3, "collision": "none", "overlap": True},
    "grass_tuft": {"share": 0.8, "depth_share": 0.4, "depth_min": 3, "collision": "none", "overlap": True},
    "prop": {"share": 0.8, "depth_share": 0.4, "depth_min": 3, "collision": "footprint", "overlap": False},
}
# Kinds that belong to other work: refused, with the reason, rather than drawn twice.
SEPARATE = {"building": "structures", "structure": "structures", "wall": "structures", "house": "structures", "roof": "structures",
            "character": "characters", "person": "characters", "player": "characters", "npc": "characters",
            "ground": "the terrain layers", "surface": "the terrain layers", "terrain": "the terrain layers", "road": "the terrain layers", "pavement": "the terrain layers"}


def components(mask, min_area):
    """The 8-connected white regions of a mask picture, in reading order of their first pixel: (box, pixels, dropped) where box is (x0, y0, x1, y1) with x1, y1 exclusive
    and pixels is a set of (x, y) in the picture; regions smaller than min_area pixels are counted in `dropped`, not returned."""
    on = mask.convert("L").point(lambda value: 255 if value >= 128 else 0)
    width, height = on.size
    data = on.tobytes()
    seen = bytearray(width * height)
    found, dropped = [], 0
    for start in range(width * height):
        if not data[start] or seen[start]:
            continue
        stack, region = [start], array("i")
        seen[start] = 1
        while stack:
            at = stack.pop()
            region.append(at)
            y, x = divmod(at, width)
            for ny in (y - 1, y, y + 1):
                if 0 <= ny < height:
                    for nx in (x - 1, x, x + 1):
                        if 0 <= nx < width:
                            to = ny * width + nx
                            if data[to] and not seen[to]:
                                seen[to] = 1
                                stack.append(to)
        if len(region) < min_area:
            dropped += 1
            continue
        xs = [at % width for at in region]
        ys = [at // width for at in region]
        found.append(((min(xs), min(ys), max(xs) + 1, max(ys) + 1), {(at % width, at // width) for at in region}))
    return found, dropped


def footprint(kind, width, height):
    """[width, height] of the ground a sprite of this kind and size stands on."""
    rule = KINDS[kind]
    return [max(1, round(width * rule["share"])), min(height, max(rule["depth_min"], round(height * rule["depth_share"])))]


def extract(image_path, job, name, output_dir, min_area=None):
    """Cut the objects of every class in the job out of the scene; returns a report. Nothing is written when any file of the set already exists or any class is refused."""
    from PIL import Image
    common.validate_schema(job, "gamearts-props-job")
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise ValueError("the name uses letters, digits, underscore and hyphen only")
    output_dir = Path(output_dir)
    base = Path(job["_input_dir"]) if "_input_dir" in job else Path(image_path).resolve().parent
    floor = job.get("min_area_px", 16) if min_area is None else min_area
    for item in job["classes"]:
        if item["kind"] in SEPARATE:
            raise ValueError(f"class {item['id']}: '{item['kind']}' belongs to {SEPARATE[item['kind']]}, which is handled separately; this pipeline makes the environment only")
        if item["kind"] not in KINDS:
            raise ValueError(f"class {item['id']}: unknown kind '{item['kind']}' (known: {', '.join(sorted(KINDS))})")
    ids = [item["id"] for item in job["classes"]]
    if len(set(ids)) != len(ids):
        raise ValueError("class ids repeat")
    targets = [output_dir / f"{name}.props.atlas.json", output_dir / f"{name}.props.atlas.png", output_dir / f"{name}.objects.json", output_dir / f"{name}.occlusion.png"]
    for target in targets:
        if target.exists():
            raise ValueError(f"{target.name} already exists; it is never overwritten")
    with Image.open(image_path) as opened:
        scene = opened.convert("RGBA")
    union = Image.new("L", scene.size, 0)
    objects, frames, report, sprites = [], [], {}, {}
    for item in job["classes"]:
        with Image.open(common.safe_member(base, item["mask"], "mask")) as mask:
            if mask.size != scene.size:
                raise ValueError(f"class {item['id']}: the mask is {mask.size[0]} x {mask.size[1]} and the scene is {scene.size[0]} x {scene.size[1]}; they must be the same size")
            regions, dropped = components(mask, floor)
            union.paste(255, mask=mask.convert("L").point(lambda value: 255 if value >= 128 else 0))
        report[item["id"]] = {"kind": item["kind"], "objects": len(regions), "dropped_below_min_area": dropped}
        for number, (box, pixels) in enumerate(regions):
            x0, y0, x1, y1 = box
            w, h = x1 - x0, y1 - y0
            object_id = f"{item['id']}_{number:03d}"
            sprite = Image.new("RGBA", (w, h), KEY)
            source = scene.crop(box)
            for px, py in pixels:
                sprite.putpixel((px - x0, py - y0), source.getpixel((px - x0, py - y0)))
            sprites[object_id] = sprite
            rule = KINDS[item["kind"]]
            entry = {"id": object_id, "class": "prop", "kind": item["kind"], "sprite": {"atlas": targets[0].name, "frame": object_id},
                     "position_px": [x0 + w // 2, y1 - 1], "footprint_px": footprint(item["kind"], w, h), "collision": rule["collision"]}
            if rule["overlap"]:
                entry["allow_overlap"] = True
            objects.append(entry)
            frames.append({"file": f"{object_id}.png", "name": object_id, "pivot": [w // 2, h - 1]})
    if not objects:
        raise ValueError("no object was found: every mask region was below the minimum area, or the masks are empty")
    work = output_dir / f"{name}.props.sprites"
    work.mkdir(parents=True, exist_ok=True)
    try:
        for object_id, sprite in sprites.items():
            sprite.save(work / f"{object_id}.png")
        manifest = {"name": name + "_props", "frames": frames, "pack": "shelf", "padding": 2, "_input_dir": str(work)}
        png, atlas = atlas_builder.build(manifest, output_dir)
        Path(png).replace(targets[1])
        built = common.read_json(atlas)
        built["image"] = targets[1].name
        Path(atlas).unlink()
        common.atomic_write_json(targets[0], built)
    finally:
        for leftover in work.glob("*.png"):
            leftover.unlink()
        work.rmdir()
    common.atomic_write_json(targets[2], objects)
    union.save(targets[3])
    return {"name": name, "objects": len(objects), "by_class": report, "atlas": targets[0].name, "objects_file": targets[2].name, "occlusion_mask": targets[3].name,
            "min_area_px": floor, "footprint_rules": {k: KINDS[k] for k in sorted({o["kind"] for o in objects})},
            "not_assessed": ["whether each mask region is one real object (touching objects merge, one object split by something in front becomes two)",
                             "the footprint sizes, which follow the kind's rule and are not measured from the picture",
                             "the objects in an engine"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("extract")
    one.add_argument("--image", type=Path, required=True)
    one.add_argument("--job", type=Path, required=True)
    one.add_argument("--name", required=True)
    one.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        job = common.read_json(args.job)
        if not isinstance(job, dict):
            raise ValueError("the job must be a JSON object")
        job["_input_dir"] = str(args.job.resolve().parent)
        result = extract(args.image, job, args.name, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:  # ValueError covers JSON, schema and contract errors
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
