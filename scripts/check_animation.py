#!/usr/bin/env python3
"""Animation checks measured from a sheet and its atlas: loop seam, pivot drift and clipping.

  python scripts/check_animation.py --image SHEET.png --atlas SHEET.atlas.json [--game-root GAME] [--checks loop_seam,clipping]

Frames are grouped by action and direction in atlas order (frames with no action form one animation). With --game-root the checks and
their limits come from the game's style preset; otherwise all three run with the defaults. These are measurements of pixels, not
judgements of motion: a walk cycle that loops badly is found, an animation that looks lifeless is not. A one-shot action (a jump, an
attack) is not meant to return to its first frame, so a loop-seam failure there is information for the person, not an error in the art.
Exit status: 1 when a check failed, otherwise 0.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_presets as presets  # noqa: E402

CHECK_NAMES = ("loop_seam", "pivot_drift", "clipping")
DEFAULTS = {"loop_seam": {"max_ratio": 1.5}, "pivot_drift": {"max_px": 2}}
NOT_ASSESSED = ("whether the motion looks right or feels good to play",
                "timing and easing as a viewer experiences them",
                "static regions that should not move (that needs a declared moving region)")


def _result(name, status, detail, **measured):
    return {"name": name, "status": status, "detail": detail, "measured": measured}


def overall(results):
    """failed if any check failed, passed if every check passed, untested when something could not be measured and nothing failed."""
    statuses = [item["status"] for item in results]
    if not statuses:
        return "not_applicable"
    return "failed" if "failed" in statuses else "passed" if all(s == "passed" for s in statuses) else "untested"


def aligned(frames):
    """The frames of one animation with every cell redrawn on one canvas so that their pivots coincide. Cells that already share a size and
    a pivot (a grid sheet) are returned unchanged; trimmed cells differ in both, and a frame-to-frame difference only means something
    when the same pixel of two frames is the same place in the world."""
    from PIL import Image
    if len({(frame["cell"].size, tuple(frame["pivot"])) for frame in frames}) == 1:
        return frames
    left = max(round(frame["pivot"][0]) for frame in frames)
    top = max(round(frame["pivot"][1]) for frame in frames)
    right = max(frame["cell"].width - round(frame["pivot"][0]) for frame in frames)
    bottom = max(frame["cell"].height - round(frame["pivot"][1]) for frame in frames)
    result = []
    for frame in frames:
        canvas = Image.new("RGBA", (left + right, top + bottom), common.KEY_RGBA)
        canvas.paste(frame["cell"], (left - round(frame["pivot"][0]), top - round(frame["pivot"][1])))
        result.append({**frame, "cell": canvas, "pivot": [left, top], "ink": common.ink_bbox(canvas)})
    return result


def animation_groups(image, atlas):
    """[(action, direction, [frame, ...]), ...] in atlas order. Each frame carries its name, pivot, duration, source bounds and
    cell image, and `ink` (the art's box inside the cell, or None when the cell is all key colour). Trimmed cells are aligned on their pivots."""
    groups = {}
    for entry in atlas["frames"]:
        x, y, w, h = entry["rect"]
        cell = image.crop((x, y, x + w, y + h))
        frame = {"name": entry["name"], "pivot": entry["pivot"], "duration_ms": entry["duration_ms"], "cell": cell, "ink": common.ink_bbox(cell),
                 "source_ink_bounds": entry.get("source_ink_bounds"), "source_size": entry["source_size"]}
        groups.setdefault((entry.get("action"), entry.get("direction")), []).append(frame)
    return [(action, direction, aligned(frames)) for (action, direction), frames in groups.items()]


def _difference(first, second):
    """Mean absolute difference between two same-size cells, 0 (identical) to 255."""
    from PIL import ImageChops, ImageStat
    stat = ImageStat.Stat(ImageChops.difference(first.convert("RGB"), second.convert("RGB")))
    return sum(stat.mean) / len(stat.mean)


def _loop_seam(frames, limits):
    if len(frames) < 3:
        return _result("loop_seam", "untested", "At least 3 frames are needed to compare the last step with the others", frames=len(frames))
    steps = [_difference(a["cell"], b["cell"]) for a, b in zip(frames, frames[1:])]
    mean_step = sum(steps) / len(steps)
    if mean_step == 0:
        return _result("loop_seam", "untested", "The frames are identical, so there is no motion to compare the seam with", frames=len(frames))
    seam = _difference(frames[-1]["cell"], frames[0]["cell"])
    ratio = round(seam / mean_step, 3)
    status = "passed" if ratio <= limits["max_ratio"] else "failed"
    detail = (f"The step from the last frame back to the first is {ratio} times an ordinary step (limit {limits['max_ratio']})"
              + ("" if status == "passed" else "; the loop jumps at its seam, unless this action is meant to play once"))
    return _result("loop_seam", status, detail, seam=round(seam, 3), mean_step=round(mean_step, 3), ratio=ratio, max_ratio=limits["max_ratio"])


def _pivot_drift(frames, limits):
    feet = [frame["ink"][3] - frame["pivot"][1] for frame in frames if frame["ink"]]
    if len(feet) < 2:
        return _result("pivot_drift", "untested", "At least 2 frames with artwork are needed to compare their feet", frames=len(feet))
    drift = max(feet) - min(feet)
    status = "passed" if drift <= limits["max_px"] else "failed"
    return _result("pivot_drift", status, f"The lowest row of the art moves {drift} px relative to the pivot across the frames (limit {limits['max_px']})",
                   drift_px=drift, max_px=limits["max_px"])


def _clipping(frames, limits):
    clipped = []
    for frame in frames:
        bounds, size = frame["source_ink_bounds"], frame["source_size"]
        if bounds is None:
            continue
        x, y, w, h = bounds
        if x == 0 or y == 0 or x + w == size[0] or y + h == size[1]:
            clipped.append(frame["name"])
    if clipped:
        return _result("clipping", "failed", f"The art touches the edge of its source frame in {len(clipped)} frame(s), so it may have been cut off: "
                       + ", ".join(clipped), frames=clipped)
    return _result("clipping", "passed", "No frame's art touches the edge of its source frame", frames=[])


CHECKS = {"loop_seam": _loop_seam, "pivot_drift": _pivot_drift, "clipping": _clipping}


def check_group(frames, params, names):
    results = []
    for name in names:
        limits = {**DEFAULTS.get(name, {}), **params.get(name, {})}
        results.append(CHECKS[name](frames, limits))
    duplicates = [b["name"] for a, b in zip(frames, frames[1:]) if _difference(a["cell"], b["cell"]) == 0]
    return results, duplicates


def check_sheet(image_path, atlas_path, params, names=None):
    """Run the animation checks over every animation on one sheet."""
    from PIL import Image
    names = list(names) if names is not None else list(CHECK_NAMES)
    unknown = [name for name in names if name not in CHECKS]
    if unknown:
        raise ValueError(f"Unknown animation check {unknown[0]!r}; use {', '.join(CHECK_NAMES)}")
    atlas = common.read_json(atlas_path)
    common.validate_schema(atlas, "gamearts-atlas")
    with Image.open(image_path) as opened:
        image = opened.convert("RGBA")
    animations = []
    for action, direction, frames in animation_groups(image, atlas):
        results, duplicates = check_group(frames, params, names)
        animations.append({"action": action, "direction": direction, "frames": len(frames),
                           "duration_ms": sum(f["duration_ms"] for f in frames), "duplicate_frames": duplicates, "checks": results})
    flat = [item for group in animations for item in group["checks"]]
    return {"status": overall(flat), "animations": animations, "not_assessed": list(NOT_ASSESSED)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, help="Take the checks and limits from the game's style preset")
    parser.add_argument("--checks", help="Comma-separated subset of: " + ", ".join(CHECK_NAMES))
    args = parser.parse_args()
    try:
        params, names = {}, args.checks.split(",") if args.checks else None
        if args.game_root and names is None:
            settings, _, _ = common.load_project_settings(args.game_root, require_confirmed=False)
            preset = presets.resolve_style_preset(settings)
            if preset and preset.get("found"):
                params = preset["check_parameters"]
                names = [n for n in preset["required_checks"] if n in CHECK_NAMES]
        result = check_sheet(args.image, args.atlas, params, names)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["status"] == "failed" else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
