#!/usr/bin/env python3
"""Build and evaluate nested moving-part sprite bundles for Game Arts.

A manifest supplies ACTUAL PNG frames, measured pivots/anchors and optional
time-dependent mount/component tracks. The tool assembles separate sheets with
build_sheet_atlas.py and calculates deterministic composed poses. It does not
infer anchors from image pixels or claim an actual Godot scene test.
"""
import argparse
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from build_sheet_atlas import build as build_sheet

VALID_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def xy(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(
        isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n)
        for n in value
    ):
        raise ValueError(f"{name}: expected two finite numbers")
    return [float(n) for n in value]


def motion(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name}: expected transform object")
    pos = xy(value.get("position", [0, 0]), name + ".position")
    scale = xy(value.get("scale", [1, 1]), name + ".scale")
    angle = value.get("rotation_degrees", 0)
    if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not math.isfinite(angle):
        raise ValueError(f"{name}: invalid rotation")
    if min(abs(scale[0]), abs(scale[1])) < 1e-8:
        raise ValueError(f"{name}: zero component scale not allowed")
    return {"position": pos, "rotation_degrees": float(angle), "scale": scale}


def matrix(tr):
    a = math.radians(tr["rotation_degrees"])
    cs, sn = math.cos(a), math.sin(a)
    sx, sy = tr["scale"]
    x, y = tr["position"]
    return [[cs * sx, -sn * sy, x], [sn * sx, cs * sy, y], [0, 0, 1]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


IDENT = matrix(motion({}, "identity"))


def animate(track, t, name):
    if not track:
        return motion({}, name)
    if not isinstance(track, list):
        raise ValueError(f"{name}: track must be a keyframe list")
    prev = -1.0
    keys = []
    for k in track:
        if not isinstance(k, dict) or isinstance(k.get("time"), bool):
            raise ValueError(f"{name}: invalid keyframe")
        ts = k.get("time")
        if not isinstance(ts, (int, float)) or not math.isfinite(ts) or not (0 <= ts <= 1) or ts <= prev:
            raise ValueError(f"{name}: times must increase in [0,1]")
        prev = ts
        keys.append((ts, motion(k, name)))
    if not keys:
        return motion({}, name)
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    for i in range(1, len(keys)):
        t1, b = keys[i]
        t0, a = keys[i - 1]
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            ang = b["rotation_degrees"] - a["rotation_degrees"]
            ang = (ang + 180) % 360 - 180  # shortest angular interpolation
            return {"position": [a["position"][j] * (1-u) + b["position"][j]*u for j in range(2)],
                    "rotation_degrees": a["rotation_degrees"] + u * ang,
                    "scale": [a["scale"][j]*(1-u) + b["scale"][j]*u for j in range(2)]}
    raise AssertionError("Unreachable")


def select_track(tracks, action, direction):
    if not tracks:
        return []
    if not isinstance(tracks, dict):
        raise ValueError("tracks must map actions to directions")
    per_action = tracks.get(action, {})
    if not isinstance(per_action, dict):
        raise ValueError("action track must map directions to keyframes")
    return per_action.get(direction, per_action.get("*", []))


def validate_structure(config):
    if not isinstance(config, dict):
        raise ValueError("Bundle manifest must be an object")
    name = config.get("name")
    if not isinstance(name, str) or not VALID_ID.fullmatch(name):
        raise ValueError("name must be a descriptive alphanumeric slug")
    directions = config.get("directions")
    if not isinstance(directions, list) or not directions or not all(
        isinstance(d, str) and d for d in directions
    ) or len(set(directions)) != len(directions):
        raise ValueError("directions must be unique nonempty strings")
    parts = config.get("components")
    if not isinstance(parts, list) or not parts:
        raise ValueError("components must be a nonempty list")
    ids = [p.get("id") for p in parts if isinstance(p, dict)]
    if len(ids) != len(parts) or any(not isinstance(x, str) or not VALID_ID.fullmatch(x) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("component IDs must be unique nonempty slugs")
    mapping = {p["id"]: p for p in parts}
    roots = [p for p in parts if p.get("parent") is None]
    if len(roots) != 1:
        raise ValueError("exactly one root component required")
    for part in parts:
        parent = part.get("parent")
        if parent is not None and (parent not in mapping or parent == part["id"]):
            raise ValueError(f"{part['id']}: invalid parent component")
        if parent is not None and not part.get("mount"):
            raise ValueError(f"{part['id']}: child must declare named parent mount")
        views = part.get("views", {})
        if not isinstance(views, dict) or set(views) != set(directions):
            raise ValueError(f"{part['id']}: missing or extra directional views")
        for d in directions:
            v = views[d]
            if not isinstance(v, dict) or not isinstance(v.get("frames"), list) or not v["frames"]:
                raise ValueError(f"{part['id']} {d}: frames required")
        motion(part.get("rest", {}), part["id"] + ".rest")
    seen, visiting, order = set(), set(), []
    def visit(part_id):
        if part_id in visiting:
            raise ValueError("component hierarchy contains a cycle")
        if part_id in seen:
            return
        visiting.add(part_id)
        parent = mapping[part_id].get("parent")
        if parent:
            visit(parent)
        visiting.remove(part_id)
        seen.add(part_id)
        order.append(part_id)
    for part_id in ids:
        visit(part_id)
    return directions, mapping, order


def build(config, output, source_dir):
    directions, parts, order = validate_structure(config)
    if output.exists():
        raise FileExistsError("Bundle output already exists; use a new revision name")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gamearts-build-", dir=str(output.parent)) as temp:
        stage = Path(temp)
        sheets = {}
        for pid in order:
            part = parts[pid]
            sheets[pid] = {}
            for d in directions:
                view = part["views"][d]
                frames = view["frames"]
                job = {
                    "_input_dir": str(source_dir),
                    "name": f"{config['name']}_{pid}_{d}",
                    "asset_id": config["name"],
                    "columns": view.get("columns", len(frames)),
                    "frames": frames,
                    "component": pid,
                    "padding": view.get("padding", 2),
                    "source_mockups": config.get("source_mockups", []),
                    "pixels_per_meter": config.get("pixels_per_meter"),
                }
                png, atlas_file = build_sheet(job, stage)
                atlas = json.loads(atlas_file.read_text(encoding="utf-8"))
                sheets[pid][d] = atlas
        # Validate named parent mounts against each parent directional atlas.
        for pid in order:
            part = parts[pid]
            if not part.get("parent"):
                continue
            parent = part["parent"]
            for d in directions:
                missing = [i for i, frame in enumerate(sheets[parent][d]["frames"])
                           if part["mount"] not in frame["anchors"]]
                if missing:
                    raise ValueError(f"{pid} {d}: mount {part['mount']} missing from parent frames {missing}")

        samples = config.get("sample_times", [0, .25, .5, .75, 1])
        if not isinstance(samples, list) or not samples or any(
            isinstance(t, bool) or not isinstance(t, (float, int)) or not math.isfinite(t) or not 0 <= t <= 1
            for t in samples
        ):
            raise ValueError("sample_times must be normalized numbers in [0,1]")
        poses = []
        for direction in directions:
            for t in samples:
                matrices = {}
                nodes = {}
                for pid in order:
                    part = parts[pid]
                    atlas = sheets[pid][direction]
                    frames = atlas["frames"]
                    action = part.get("action", "default")
                    index = min(int(t * len(frames)), len(frames)-1)
                    frame = frames[index]
                    rest = matrix(motion(part.get("rest", {}), pid+".rest"))
                    own = matrix(animate(select_track(part.get("motion_tracks", {}), action, direction),
                                         t, pid+".motion_tracks"))
                    parent_id = part.get("parent")
                    if parent_id:
                        parent_atlas = sheets[parent_id][direction]["frames"]
                        parent_frame = parent_atlas[min(int(t*len(parent_atlas)),len(parent_atlas)-1)]
                        anchor = parent_frame["anchors"][part["mount"]]
                        origin = parent_frame["pivot"]
                        local_mount = matrix(motion(
                            {"position":[anchor[0]-origin[0], anchor[1]-origin[1]]},
                            pid+".mount_origin"))
                        mount_animation = matrix(animate(
                            select_track(part.get("mount_tracks", {}), part.get("parent_action", parts[parent_id].get("action", "default")), direction),
                            t, pid+".mount_tracks"))
                        combined = mul(mul(mul(mul(matrices[parent_id],local_mount),mount_animation),rest),own)
                    else:
                        combined = mul(rest,own)
                    matrices[pid] = combined
                    nodes[pid] = {"frame_index":index,"image":atlas["image"],
                                  "frame_rect":frame["rect"],"pivot":frame["pivot"],
                                  "world_matrix_2d":combined}
                poses.append({"direction":direction,"normalized_time":t,"nodes":nodes})
        bundle={"schema_version":"1.0","asset_id":config["name"],
                "directions":directions,"component_order":order,
                "components":[{"id":pid,"parent":parts[pid].get("parent"),
                               "mount":parts[pid].get("mount"),"action":parts[pid].get("action","default"),
                               "rest":parts[pid].get("rest",{}),
                               "mount_tracks":parts[pid].get("mount_tracks",{}),"parent_action":parts[pid].get("parent_action"),
                               "motion_tracks":parts[pid].get("motion_tracks",{}),
                               "atlases":{d:sheets[pid][d]["image"].replace(".png",".atlas.json") for d in directions}}
                              for pid in order],
                "source_mockups":config.get("source_mockups",[]),
                "sampled_poses":poses,
                "validation":{"structure":"passed","direction_coverage":"passed",
                              "mount_references":"passed","frame_geometry":"generated",
                              "artistic_alignment":"not_tested","godot_runtime":"not_tested"}}
        (stage/(config["name"]+".bundle.json")).write_text(json.dumps(bundle,indent=2)+"\n",encoding="utf-8")
        # Move as one directory; no partial publication of sheets if validation fails.
        shutil.move(str(stage),str(output))
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest",type=Path)
    p.add_argument("--output-dir",required=True,type=Path)
    args=p.parse_args()
    try:
        inp=args.manifest.resolve()
        data=json.loads(inp.read_text(encoding="utf-8"))
        result=build(data,args.output_dir.resolve(),inp.parent)
        print("BUILT",result)
    except (ValueError,OSError,KeyError,TypeError) as e:
        p.exit(1,"ERROR: "+str(e)+"\n")


if __name__=="__main__":
    main()
