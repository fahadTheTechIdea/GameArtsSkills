#!/usr/bin/env python3
"""One command from a scene to a complete tilemap: the surface and the environment (plan P16). Works for any game's scene; nothing here is specific to one.

  python scripts/gamearts_tilemap.py build --image SCENE.png --job tilemap_job.json --name NAME --output-dir DIR [--tiled]

It composes the framework's own owners and adds no logic of its own:
  1. environment objects (`gamearts_props.py`): the trees, fences, hedges, props and plants the job's class masks mark are cut out as sprites with an atlas and map objects;
  2. the surface (`gamearts_terrain.py` through `gamearts_layered_map.py`): a terrain label for every cell, with whatever stands on the ground (those objects, any occlusion
     mask, solid structures) hidden from the read and its ground inferred from the nearest visible ground, and every inference listed;
  3. the plan (`gamearts_layered_map.py plan`): which overlay tilesets the map still needs, a job skeleton for each and the cleanest crop of each terrain as a reference;
  4. optionally (`--tiled`) the Tiled map of the whole scene (`export_exchange.py`).

Structures (buildings) and characters are not drawn as environment: a solid structure is a mask that blocks movement and is built as its own thing, and characters are
handled separately; both are refused as environment kinds. The job is schemas/gamearts-tilemap-job.schema.json. Nothing is overwritten, and a refusal leaves nothing behind.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_exchange as exchange  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402
import gamearts_props as props  # noqa: E402


def build(image_path, job, name, output_dir, tiled=False):
    """Build the tilemap of a scene; returns a report naming every file written and what was not assessed."""
    from PIL import Image, ImageChops
    common.validate_schema(job, "gamearts-tilemap-job")
    output_dir = Path(output_dir)
    base = Path(job["_input_dir"]) if "_input_dir" in job else Path(image_path).resolve().parent
    cell = tuple(job["cell"])
    with Image.open(image_path) as opened:
        size = opened.size
    if size[0] % cell[0] or size[1] % cell[1]:
        raise ValueError(f"the scene is {size[0]} x {size[1]} and a cell is {cell[0]} x {cell[1]}; crop the scene to whole cells first, so the map's grid matches the picture")
    if tiled and any("tileset" not in terrain for terrain in job["terrains"]):
        raise ValueError("--tiled draws the surface with each terrain's tileset, and a terrain here names none; make the tilesets from the plan first, then export the map")
    targets = [output_dir / f"{name}{layered.SUFFIX}", output_dir / f"{name}.all.occlusion.png", output_dir / f"{name}.tmj"]
    for target in targets:
        if target.exists():
            raise ValueError(f"{target.name} already exists; it is never overwritten")
    environment = job.get("environment")
    objects, hides, written = None, [], []
    if environment:
        environment = dict(environment, _input_dir=str(base))
        made = props.extract(image_path, environment, name, output_dir)
        objects = common.read_json(output_dir / made["objects_file"])
        hides.append(output_dir / made["occlusion_mask"])
        written += [made["atlas"], made["atlas"].replace(".json", ".png"), made["objects_file"], made["occlusion_mask"]]
    if job.get("occlusion_mask"):
        hides.append(common.safe_member(base, job["occlusion_mask"], "occlusion mask"))
    occlusion = None
    if len(hides) == 1:
        occlusion = hides[0]
    elif hides:
        merged = None
        for path in hides:
            with Image.open(path) as picture:
                if picture.size != size:
                    raise ValueError(f"{path.name} is {picture.size[0]} x {picture.size[1]} and the scene is {size[0]} x {size[1]}; they must be the same size")
                white = picture.convert("L").point(lambda value: 255 if value >= 128 else 0)
            merged = white if merged is None else ImageChops.lighter(merged, white)
        merged.save(targets[1])
        occlusion = targets[1]
        written.append(targets[1].name)
    solid = common.safe_member(base, job["solid_mask"], "solid mask") if job.get("solid_mask") else None
    path, data = layered.build(image_path, job["terrains"], cell, name, output_dir, job.get("min_region", 1), objects, job.get("occluders"), occlusion, solid)
    written.append(path.name)
    plan = layered.plan(path, output_dir / f"{name}.jobs", image_path, output_dir / f"{name}.swatches")
    exported = None
    if tiled:
        exported = exchange.export_layered_map(path, targets[2]).name
        written.append(exported)
    read = data["source"]["read"]
    return {"name": name, "grid": [data["grid"]["width"], data["grid"]["height"]], "objects": len(data["objects"]), "files": written, "tiled_map": exported,
            "surface": {"occluded_cells": len(read["occluded_cells"]), "unclassified_cells": len(read["unclassified_cells"]), "solid_cells": len(read.get("solid_cells", []))},
            "tilesets_still_to_make": [item["terrain"] for item in plan["tilesets"] if item["status"] != "present"], "tileset_job_skeletons": f"{name}.jobs",
            "reference_swatches": f"{name}.swatches",
            "not_assessed": ["whether each hidden cell's inferred ground is what lies under the object", "whether each mask region is one real object",
                             "the overlay tilesets' art, which is made from the plan's jobs", "any engine's opening of the map"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("build")
    one.add_argument("--image", type=Path, required=True)
    one.add_argument("--job", type=Path, required=True)
    one.add_argument("--name", required=True)
    one.add_argument("--output-dir", type=Path, required=True)
    one.add_argument("--tiled", action="store_true", help="also write the Tiled map of the scene")
    args = parser.parse_args()
    try:
        job = common.read_json(args.job)
        if not isinstance(job, dict):
            raise ValueError("the job must be a JSON object")
        job["_input_dir"] = str(args.job.resolve().parent)
        result = build(args.image, job, args.name, args.output_dir, args.tiled)
    except (OSError, ValueError, KeyError, TypeError) as exc:  # ValueError covers JSON, schema and contract errors
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
