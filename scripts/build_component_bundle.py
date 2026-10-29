#!/usr/bin/env python3
"""Build and evaluate nested moving-part sprite bundles for Game Arts.

A manifest (schemas/gamearts-component-job.schema.json) supplies ACTUAL PNG frames, measured pivots/anchors and optional
time-dependent mount/component tracks. The tool assembles separate sheets with build_sheet_atlas.py and calculates
deterministic composed poses (`sampled_poses`, the numeric reference any runtime can be checked against). It does not infer
anchors from image pixels and does not run any engine.

Conventions: keyframe times are normalized 0..1; rotation keyframes are absolute degrees interpolated linearly (a full turn
needs only its two end keys) unless the job sets `rotation_interpolation: "shortest"`; frames are chosen by cumulative
`duration_ms`; `draw_order` is resolved per direction and higher values draw later (on top).

A keyframe may also say how the segment that STARTS at it is crossed: `interpolation` is `linear` (default), `nearest` (hold this key's value
until the next key, for stepped limited animation) or `cubic` (a Hermite curve through this key and the next whose tangents come from the
neighbouring keys, so a run of evenly spaced straight keys stays straight), and `easing` reshapes the time inside the segment: `linear` (default),
`ease_in` (u*u), `ease_out` (1-(1-u)*(1-u)) or `ease_in_out` (2*u*u below one half, 1-(2-2u)*(2-2u)/2 above). `sampled_poses` honor both, so they stay the
numeric reference. A job without them behaves exactly as before.
"""
import argparse
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
from build_sheet_atlas import build as build_sheet  # noqa: E402
from validate_parent_cleanup import validate as validate_cleanup  # noqa: E402
import validate_settings_fit as settings_fit  # noqa: E402


def xy(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(
        isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) for n in value
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


INTERPOLATIONS = ("linear", "nearest", "cubic")
EASINGS = {"linear": lambda u: u,
           "ease_in": lambda u: u * u,
           "ease_out": lambda u: 1 - (1 - u) * (1 - u),
           "ease_in_out": lambda u: 2 * u * u if u < 0.5 else 1 - (2 - 2 * u) * (2 - 2 * u) / 2}


def curve(key, name):
    """(interpolation, easing) a keyframe asks for the segment that starts at it."""
    interpolation, easing = key.get("interpolation", "linear"), key.get("easing", "linear")
    if interpolation not in INTERPOLATIONS:
        raise ValueError(f"{name}: interpolation {interpolation!r} is not one of {', '.join(INTERPOLATIONS)}")
    if easing not in EASINGS:
        raise ValueError(f"{name}: easing {easing!r} is not one of {', '.join(EASINGS)}")
    if interpolation == "nearest" and easing != "linear":
        raise ValueError(f"{name}: a nearest (stepped) segment holds a value, so it cannot also ease")
    return interpolation, easing


def parse_track(track, name):
    """Validate a keyframe list and return [(time, transform, (interpolation, easing))]; times must strictly increase inside [0, 1]."""
    if not isinstance(track, list):
        raise ValueError(f"{name}: track must be a keyframe list")
    prev, keys = -1.0, []
    for k in track:
        if not isinstance(k, dict) or isinstance(k.get("time"), bool):
            raise ValueError(f"{name}: invalid keyframe")
        ts = k.get("time")
        if not isinstance(ts, (int, float)) or not math.isfinite(ts) or not (0 <= ts <= 1) or ts <= prev:
            raise ValueError(f"{name}: times must increase in [0,1]")
        prev = ts
        keys.append((ts, motion(k, name), curve(k, name)))
    if track and ("interpolation" in track[-1] or "easing" in track[-1]):
        raise ValueError(f"{name}: the last keyframe has no segment after it, so interpolation and easing there would do nothing")
    return keys


def shortest_arc(delta):
    return (delta + 180) % 360 - 180


def hermite(before, start, end, after, u, span):
    """Value at fraction u of a Hermite segment from `start` to `end`. `before` and `after` are (time, value) of the neighbouring keys or None;
    a missing neighbour gives the straight-line tangent. `span` is the time length of the segment."""
    straight = end[1] - start[1]
    tangent_start = (end[1] - before[1]) / (end[0] - before[0]) * span if before else straight
    tangent_end = (after[1] - start[1]) / (after[0] - start[0]) * span if after else straight
    u2, u3 = u * u, u * u * u
    return (2 * u3 - 3 * u2 + 1) * start[1] + (u3 - 2 * u2 + u) * tangent_start + (-2 * u3 + 3 * u2) * end[1] + (u3 - u2) * tangent_end


def cubic_segment(keys, i, u, rotation_mode):
    """The pose at fraction u of the segment between keys[i - 1] and keys[i], on a Hermite curve through all five channels."""
    t0, a, _ = keys[i - 1]
    t1, b, _ = keys[i]
    before = keys[i - 2] if i >= 2 else None
    after = keys[i + 1] if i + 1 < len(keys) else None

    def channel(read):
        def at(key):
            return (key[0], read(key[1]))
        return hermite(at(before) if before else None, (t0, read(a)), (t1, read(b)), at(after) if after else None, u, t1 - t0)

    start_angle, end_angle = a["rotation_degrees"], b["rotation_degrees"]
    before_angle = before[1]["rotation_degrees"] if before else None
    after_angle = after[1]["rotation_degrees"] if after else None
    if rotation_mode == "shortest":  # unwrap the angles around the segment so the curve follows the short way round
        end_angle = start_angle + shortest_arc(end_angle - start_angle)
        before_angle = start_angle - shortest_arc(start_angle - before_angle) if before else None
        after_angle = end_angle + shortest_arc(after_angle - end_angle) if after else None
    angle = hermite((before[0], before_angle) if before else None, (t0, start_angle), (t1, end_angle), (after[0], after_angle) if after else None, u, t1 - t0)
    return {"position": [channel(lambda m: m["position"][0]), channel(lambda m: m["position"][1])],
            "rotation_degrees": angle,
            "scale": [channel(lambda m: m["scale"][0]), channel(lambda m: m["scale"][1])]}


def animate(track, t, name, rotation_mode="linear"):
    if not track:
        return motion({}, name)
    keys = parse_track(track, name)
    if not keys:
        return motion({}, name)
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    for i in range(1, len(keys)):
        t1, b, _ = keys[i]
        t0, a, (interpolation, easing) = keys[i - 1]
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            if interpolation == "nearest":
                return b if u >= 1 else a
            u = EASINGS[easing](u)
            if interpolation == "cubic":
                return cubic_segment(keys, i, u, rotation_mode)
            ang = b["rotation_degrees"] - a["rotation_degrees"]
            if rotation_mode == "shortest":
                ang = (ang + 180) % 360 - 180
            return {"position": [a["position"][j] * (1 - u) + b["position"][j] * u for j in range(2)],
                    "rotation_degrees": a["rotation_degrees"] + u * ang,
                    "scale": [a["scale"][j] * (1 - u) + b["scale"][j] * u for j in range(2)]}
    raise AssertionError("Unreachable")


def frame_index(frames, t):
    """Frame shown at normalized time t, weighting each frame by its duration_ms (t = 1 shows the last frame)."""
    total = sum(f["duration_ms"] for f in frames)
    target, cumulative = t * total, 0
    for index, frame in enumerate(frames):
        cumulative += frame["duration_ms"]
        if target < cumulative:
            return index
    return len(frames) - 1


def select_track(tracks, action, direction):
    if not tracks:
        return []
    per_action = tracks.get(action, {})
    if not isinstance(per_action, dict):
        raise ValueError("action track must map directions to keyframes")
    return per_action.get(direction, per_action.get("*", []))


def check_tracks(tracks, selected_action, directions, label):
    """Every track must be well formed AND reachable: only the selected action's tracks are ever evaluated."""
    if not tracks:
        return
    if not isinstance(tracks, dict):
        raise ValueError(f"{label} must map actions to directions")
    for action, per_direction in tracks.items():
        if action != selected_action:
            raise ValueError(f"{label}['{action}'] is never selected (the selected action is '{selected_action}'); "
                             f"rename it or set the matching action/parent_action")
        if not isinstance(per_direction, dict):
            raise ValueError(f"{label}['{action}'] must map directions to keyframes")
        for direction, keys in per_direction.items():
            if direction != "*" and direction not in directions:
                raise ValueError(f"{label}['{action}']['{direction}'] names a direction the bundle does not have")
            parse_track(keys, f"{label}['{action}']['{direction}']")


def validate_structure(config):
    if not isinstance(config, dict):
        raise ValueError("Bundle manifest must be an object")
    common.validate_schema(config, "gamearts-component-job")
    directions = config["directions"]
    parts = config["components"]
    ids = [p["id"] for p in parts]
    if len(set(ids)) != len(ids):
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
        own_action = part.get("action", "default")
        parent_action = part.get("parent_action", mapping[parent].get("action", "default")) if parent else own_action
        check_tracks(part.get("motion_tracks", {}), own_action, directions, f"{part['id']}.motion_tracks")
        check_tracks(part.get("mount_tracks", {}), parent_action, directions, f"{part['id']}.mount_tracks")
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


def stage_cleanup_evidence(config, source_dir, stage):
    """Package original/clean parent/clean plate + object sprites/masks in the candidate so it stays self-contained."""
    supplied = config.get("parent_cleanup_evidence", [])
    if not isinstance(supplied, list):
        raise ValueError("parent_cleanup_evidence must be a list")
    staged = []
    for row in supplied:
        if not isinstance(row, dict):
            raise ValueError("parent_cleanup_evidence entries must be objects")
        parent, direction, index = row.get("parent_component"), row.get("direction"), row.get("frame_index")
        if not (isinstance(parent, str) and common.SLUG.fullmatch(parent) and isinstance(direction, str)
                and common.SLUG.fullmatch(direction) and type(index) is int and index >= 0):
            raise ValueError("cleanup evidence must name valid parent/direction/frame_index")
        original = common.safe_member(source_dir, row.get("manifest"), "cleanup evidence manifest")
        if not original.is_file():
            raise ValueError(f"Missing cleanup evidence job: {original}")
        spec = common.read_json(original)
        if not isinstance(spec, dict):
            raise ValueError("cleanup evidence manifest must be a JSON object")
        folder = stage / "parent_cleanup" / f"{parent}_{direction}_{index}"
        folder.mkdir(parents=True, exist_ok=False)
        used = set()

        def copy_art(reference, destination, label):
            file = common.safe_member(original.parent, reference, f"{label} cleanup image")
            if file.suffix.lower() != ".png" or not file.is_file():
                raise ValueError(f"Missing PNG cleanup artifact: {file}")
            if destination in used:
                raise ValueError("Duplicate cleanup output path")
            used.add(destination)
            shutil.copy2(file, folder / destination)
            return destination

        for field in ("source_composite", "static_parent", "clean_plate"):
            spec[field] = copy_art(spec.get(field), field + ".png", field)
        for part in spec.get("detached_components", []):
            identifier = part.get("id") if isinstance(part, dict) else None
            if not isinstance(identifier, str) or not common.SLUG.fullmatch(identifier):
                raise ValueError("Invalid detached component ID")
            part["sprite"] = copy_art(part.get("sprite"), identifier + "_sprite.png", "sprite")
            part["removal_mask"] = copy_art(part.get("removal_mask"), identifier + "_mask.png", "mask")
            if part.get("sprite_silhouette_mask"):
                part["sprite_silhouette_mask"] = copy_art(part["sprite_silhouette_mask"], identifier + "_silhouette.png",
                                                          "sprite_silhouette_mask")
        target = folder / "cleanup.json"
        common.atomic_write_json(target, spec)
        validate_cleanup(target, strict_props=True)  # an invalid proof never gets published
        staged.append({"parent_component": parent, "direction": direction, "frame_index": index,
                       "manifest": target.relative_to(stage).as_posix()})
    return staged


def build(config, output, source_dir):
    directions, parts, order = validate_structure(config)
    mode = config.get("rotation_interpolation", "linear")
    source_dir = Path(source_dir).resolve()
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
                job = {"_input_dir": str(source_dir), "name": f"{config['name']}_{pid}_{d}", "asset_id": config["name"],
                       "columns": view.get("columns", len(view["frames"])), "frames": view["frames"], "component": pid,
                       "padding": view.get("padding", 2), "source_mockups": config.get("source_mockups", []),
                       "pixels_per_meter": config.get("pixels_per_meter"),
                       "allow_near_key": bool(view.get("allow_near_key", False))}
                if part.get("parent"):
                    job["parent_attachment"] = {"parent_component": part["parent"], "mount": part["mount"]}
                _, atlas_file = build_sheet(job, stage)
                sheets[pid][d] = common.read_json(atlas_file)
        packaged_cleanup = stage_cleanup_evidence(config, source_dir, stage)
        composite = len(parts) > 1 or bool(config.get("detached_inventory"))  # anything detachable needs cleanup proof and review
        for pid in order:  # named parent mounts must exist on every parent directional frame
            part = parts[pid]
            if not part.get("parent"):
                continue
            for d in directions:
                missing = [i for i, frame in enumerate(sheets[part["parent"]][d]["frames"]) if part["mount"] not in frame["anchors"]]
                if missing:
                    raise ValueError(f"{pid} {d}: mount {part['mount']} missing from parent frames {missing}")
        samples = config.get("sample_times", [0, .25, .5, .75, 1])
        if not samples:
            raise ValueError("sample_times must not be empty")
        poses = []
        for direction in directions:
            for t in samples:
                matrices, nodes = {}, {}
                for pid in order:
                    part = parts[pid]
                    atlas = sheets[pid][direction]
                    index = frame_index(atlas["frames"], t)
                    frame = atlas["frames"][index]
                    rest = matrix(motion(part.get("rest", {}), pid + ".rest"))
                    own = matrix(animate(select_track(part.get("motion_tracks", {}), part.get("action", "default"), direction),
                                         t, pid + ".motion_tracks", mode))
                    parent_id = part.get("parent")
                    if parent_id:
                        parent_frames = sheets[parent_id][direction]["frames"]
                        parent_frame = parent_frames[frame_index(parent_frames, t)]
                        anchor, origin = parent_frame["anchors"][part["mount"]], parent_frame["pivot"]
                        local_mount = matrix(motion({"position": [anchor[0] - origin[0], anchor[1] - origin[1]]}, pid + ".mount_origin"))
                        parent_action = part.get("parent_action", parts[parent_id].get("action", "default"))
                        mount_animation = matrix(animate(select_track(part.get("mount_tracks", {}), parent_action, direction),
                                                         t, pid + ".mount_tracks", mode))
                        combined = mul(mul(mul(mul(matrices[parent_id], local_mount), mount_animation), rest), own)
                    else:
                        combined = mul(rest, own)
                    matrices[pid] = combined
                    nodes[pid] = {"frame_index": index, "image": atlas["image"], "frame_rect": frame["rect"], "pivot": frame["pivot"],
                                  "draw_order": resolved_draw_order(part, direction, order.index(pid)),
                                  "world_matrix_2d": combined}
                poses.append({"direction": direction, "normalized_time": t, "nodes": nodes})
        bundle = {"schema_version": "1.0", "asset_id": config["name"], "directions": directions, "component_order": order,
                  "components": [{"id": pid, "parent": parts[pid].get("parent"), "mount": parts[pid].get("mount"),
                                  "action": parts[pid].get("action", "default"), "rest": parts[pid].get("rest", {}),
                                  "mount_tracks": parts[pid].get("mount_tracks", {}), "parent_action": parts[pid].get("parent_action"),
                                  "motion_tracks": parts[pid].get("motion_tracks", {}),
                                  "draw_order": {d: resolved_draw_order(parts[pid], d, order.index(pid)) for d in directions},
                                  "atlases": {d: sheets[pid][d]["image"].replace(".png", ".atlas.json") for d in directions}}
                                 for pid in order],
                  "rotation_interpolation": mode, "source_mockups": config.get("source_mockups", []),
                  "parent_cleanup_evidence": packaged_cleanup, "detached_inventory": config.get("detached_inventory", {}),
                  # Composite assets always need the exact user visual review before approval.
                  "visual_review_protocol": "review_packet" if composite else None,
                  "sampled_poses": poses,
                  "validation": {"structure": "passed", "direction_coverage": "passed", "mount_references": "passed",
                                 "frame_geometry": "generated", "parent_cleanup": "pending" if composite else "not_applicable",
                                 "artistic_alignment": "not_tested", "engine_validation": "not_tested"}}
        bundle_file = stage / (config["name"] + ".bundle.json")
        common.validate_schema(bundle, "gamearts-bundle")
        common.atomic_write_json(bundle_file, bundle)
        if packaged_cleanup:  # missing evidence may stay generated, but present evidence must pass the approval gate
            from validate_component_bundle import validate as validate_bundle
            problems = validate_bundle(stage, approval_gate=True)
            if problems:
                raise ValueError("Parent-cleanup approval gate: " + "; ".join(problems))
            bundle["validation"]["parent_cleanup"] = "passed_declared_pixel_check"
            common.atomic_write_json(bundle_file, bundle)
        common.move_path(stage, output)  # one directory, so a failed validation never publishes partial sheets
    return output


def resolved_draw_order(part, direction, default):
    table = part.get("draw_order", {})
    return table.get(direction, table.get("*", default))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--game-root", type=Path, help="Say whether the new bundle fits this game's saved settings (facing directions, scale)")
    args = p.parse_args()
    try:
        inp = args.manifest.resolve()
        data = json.loads(inp.read_text(encoding="utf-8"))
        result = build(data, args.output_dir.resolve(), inp.parent)
        print("BUILT", result)
        if args.game_root:
            settings_fit.announce(args.game_root, args.output_dir.resolve())
    except (ValueError, OSError, KeyError, TypeError) as e:  # ValueError covers JSON and contract errors
        p.exit(1, "ERROR: " + str(e) + "\n")


if __name__ == "__main__":
    main()
