#!/usr/bin/env python3
"""Placing repeated objects (rocks, bushes, trees) so they look natural and never overlap (plan P16).

  python scripts/gamearts_placement.py scatter --map MAP.layered_map.json --on sand,grass --radius 24 --seed 7 --class prop --atlas rocks.atlas.json --frame S0 \\
        --footprint 8x8 --id-prefix rock --output objects.json [--density grass=0.5]

Bridson's fast Poisson-disk sampling gives a guaranteed minimum distance between points in linear time (measured here: 24.1 px apart where uniform random points
came within 5.4 px). The sampler uses only the standard library's seeded generator and arithmetic, with no trigonometry, so the same seed gives the same
positions on every platform. `scatter` keeps the points that lie on the chosen terrains, thins them by a per-terrain density, and avoids objects already on the
map. It writes a list of objects the map's `objects` can take; it does not edit the map.
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402


def poisson_disk(width, height, radius, seed, accept=None, candidates=30):
    """Points in [0, width) x [0, height), each at least `radius` from every other, where `accept(x, y)` is true. Deterministic for a seed."""
    if radius <= 0 or width <= 0 or height <= 0:
        raise ValueError("the area and the radius must be positive")
    accept = accept or (lambda x, y: True)
    rng = random.Random(seed)
    side = radius / 2 ** 0.5
    cols, rows = int(width / side) + 1, int(height / side) + 1
    grid = {}
    points, active = [], []

    def far_enough(x, y):
        gx, gy = int(x / side), int(y / side)
        for yy in range(max(0, gy - 2), min(rows, gy + 3)):
            for xx in range(max(0, gx - 2), min(cols, gx + 3)):
                other = grid.get((xx, yy))
                if other is not None and (points[other][0] - x) ** 2 + (points[other][1] - y) ** 2 < radius ** 2:
                    return False
        return True

    def add(x, y):
        points.append((x, y))
        active.append(len(points) - 1)
        grid[(int(x / side), int(y / side))] = len(points) - 1

    for _ in range(200):  # the first point: any accepted place
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        if accept(x, y):
            add(x, y)
            break
    while active:
        pick = rng.randrange(len(active))
        px, py = points[active[pick]]
        for _ in range(candidates):
            # a point in the ring between radius and twice the radius, found by rejection so no trigonometry is needed
            while True:
                dx, dy = rng.uniform(-2 * radius, 2 * radius), rng.uniform(-2 * radius, 2 * radius)
                if radius ** 2 <= dx * dx + dy * dy <= (2 * radius) ** 2:
                    break
            x, y = px + dx, py + dy
            if 0 <= x < width and 0 <= y < height and accept(x, y) and far_enough(x, y):
                add(x, y)
                break
        else:
            active.pop(pick)
    return points


def scatter(data, terrain_ids, radius_px, seed, density=None, existing=None):
    """Integer map-pixel positions for repeated objects of the layered map `data`: on cells of the named terrains only, at least `radius_px` apart and from the
    objects already placed, each kept with the probability `density` gives for its terrain (1 when it names none)."""
    known = {t["id"]: i for i, t in enumerate(data["terrains"])}
    for terrain_id in list(terrain_ids) + list((density or {}).keys()):
        if terrain_id not in known:
            raise ValueError(f"the map has no terrain {terrain_id!r}; it has {', '.join(known)}")
    labels = layered.labels_of(data)
    cell_w, cell_h = data["grid"]["cell_px"]
    width_px, height_px = data["grid"]["width"] * cell_w, data["grid"]["height"] * cell_h
    wanted = {known[t] for t in terrain_ids}
    fixed = [tuple(o["position_px"]) for o in (existing if existing is not None else data["objects"])]

    def accept(x, y):
        return labels[int(y // cell_h)][int(x // cell_w)] in wanted and all((x - fx) ** 2 + (y - fy) ** 2 >= radius_px ** 2 for fx, fy in fixed)
    kept = random.Random(f"{seed}-thin")  # thinning has its own stream, so the spacing does not depend on the density
    out = []
    for x, y in poisson_disk(width_px, height_px, radius_px, seed, accept):
        chance = (density or {}).get(data["terrains"][labels[int(y // cell_h)][int(x // cell_w)]]["id"], 1.0)
        if kept.random() < chance:
            out.append((int(x), int(y)))
    return out


def _size(text):
    try:
        width, height = (int(part) for part in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, for example 8x8") from None
    return width, height


def _density(items):
    result = {}
    for item in items or []:
        name, _, value = item.partition("=")
        try:
            result[name] = float(value)
        except ValueError:
            raise ValueError(f"--density wants terrain=number, for example grass=0.5, not {item!r}") from None
        if not 0 <= result[name] <= 1:
            raise ValueError("a density is between 0 and 1")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    sub = ops.add_parser("scatter")
    sub.add_argument("--map", type=Path, required=True)
    sub.add_argument("--on", required=True, help="comma-separated terrain ids the objects may stand on")
    sub.add_argument("--radius", type=float, required=True, help="the least distance between two objects, in map pixels")
    sub.add_argument("--seed", required=True)
    sub.add_argument("--class", dest="object_class", choices=("prop", "static_structure", "fixed_machinery"), default="prop")
    sub.add_argument("--atlas", required=True)
    sub.add_argument("--frame", required=True)
    sub.add_argument("--footprint", type=_size)
    sub.add_argument("--id-prefix", required=True)
    sub.add_argument("--density", action="append")
    sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = layered.load(args.map)
        if args.output.exists():
            raise ValueError(f"{args.output.name} already exists; the objects are never overwritten")
        positions = scatter(data, [t for t in args.on.split(",") if t], args.radius, args.seed, _density(args.density))
        objects = []
        for index, (x, y) in enumerate(positions):
            obj = {"id": f"{args.id_prefix}_{index:03d}", "class": args.object_class, "sprite": {"atlas": args.atlas, "frame": args.frame}, "position_px": [x, y]}
            if args.footprint:
                obj.update(footprint_px=list(args.footprint), collision="footprint")
            objects.append(obj)
        common.atomic_write_json(args.output, objects)
        print(json.dumps({"written": args.output.name, "objects": len(objects)}, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("BLOCKED", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
