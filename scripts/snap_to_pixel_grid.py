#!/usr/bin/env python3
"""Recover the native picture from pixel art that was drawn large: detect the grid, take each cell's middle colour, write a working copy.

  python scripts/snap_to_pixel_grid.py --image LARGE.png --output NATIVE.snapped.png [--report NATIVE.snapped.json] [--game-root GAME]

Image generators often return 'pixel art' at ten times its real size, with cells that are not quite uniform and a grid whose size is not
a whole number. This finds the regular grid the colour changes sit on (gamearts_pixelgrid), reads the middle half of every cell (the middle of
its spread when the cell is uniform, its median colour when a stray line or speck crosses it), and, when the game has a palette (--game-root with art_style.palette_reference, or --palette), snaps each result to the nearest
palette colour. The original is never changed and an existing output is never overwritten. A picture with no consistent grid (already
native, flat, or not pixel art at all) is refused with the measured reason instead of being guessed at. The result is a working copy for
review: it is registered and approved like any other picture, never silently substituted for the original.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_palette as palette  # noqa: E402
import gamearts_pixelgrid as grid  # noqa: E402

MIN_SCORE = 0.6  # a grid must explain the picture's colour changes at least this far above what a random grid would
UNIFORM_SPREAD = 8  # a cell is uniform when no channel varies by more than this across its middle


def _cells(length, period, phase):
    """Start positions (floats) of the cells along one axis; a leading partial cell counts when it is at least a quarter wide."""
    first = phase - period if phase > 0.25 * period else phase
    starts, position = [], first
    while position < length - 0.25 * period:
        starts.append(position)
        position += period
    return starts


def _detect(profile, axis):
    found = grid.detect_period(profile)
    if found is None or found[2] < MIN_SCORE:
        best = "no repeating structure" if found is None else f"the best grid explains only {round(found[2] * 100)}% of the colour changes beyond chance"
        raise ValueError(f"The {axis} has no consistent pixel grid ({best}; at least {round(MIN_SCORE * 100)}% is needed). "
                         "The picture may already be at its native size, may be flat, or may not be pixel art")
    return found


def snap(image, colours=None):
    """(native picture, report) for a picture drawn large. `colours` (a list of RGB tuples) snaps every result to the palette."""
    from PIL import ImageStat
    from PIL import Image
    rgba = image.convert("RGBA")
    if rgba.getchannel("A").getextrema() != (255, 255):
        raise ValueError("The picture has transparency: snapping works on opaque pictures, with the key colour as the background")
    rgb = rgba.convert("RGB")
    columns, rows = grid.edge_profiles(rgb)
    (px, fx, cx), (py, fy, cy) = _detect(columns, "columns"), _detect(rows, "rows")
    xs, ys = _cells(rgb.width, px, fx), _cells(rgb.height, py, fy)
    out = Image.new("RGB", (len(xs), len(ys)))
    pixels, uniform = out.load(), 0
    for j, top in enumerate(ys):
        for i, left in enumerate(xs):
            x0, x1 = max(0, round(left + 0.25 * px)), min(rgb.width, max(round(left + 0.75 * px), round(left + 0.25 * px) + 1))
            y0, y1 = max(0, round(top + 0.25 * py)), min(rgb.height, max(round(top + 0.75 * py), round(top + 0.25 * py) + 1))
            region = rgb.crop((x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)))
            extrema = region.getextrema()
            if all(high - low <= UNIFORM_SPREAD for low, high in extrema):
                uniform += 1
                colour = tuple((low + high) // 2 for low, high in extrema)  # a uniform cell: the middle of its spread, within the noise of the true colour
            else:
                colour = tuple(int(c) for c in ImageStat.Stat(region).median)  # a cell with real variation: its median colour
            if max(abs(a - b) for a, b in zip(colour, common.KEY_RGB)) <= common.NEAR_KEY_TOLERANCE:
                colour = common.KEY_RGB  # the background stays the exact key colour, whatever the palette holds
            elif colours:
                colour = palette.nearest(colour, colours)
            pixels[i, j] = colour
    report = {"cell_px": [px, py], "phase_px": [fx, fy], "grid_score": [cx, cy], "output_size": [out.width, out.height],
              "uniform_cells_share": round(uniform / (out.width * out.height), 3), "method": "middle of the spread of the middle half of each cell when it is uniform, its median colour otherwise",
              "palette": f"applied: every cell snapped to the nearest of {len(colours)} palette colours" if colours else "none applied"}
    return out, report


def snap_file(image_path, output_path, colours=None, report_path=None, root=None):
    """Snap one file into a new file (and an optional report). Nothing is written when the picture is refused."""
    from PIL import Image
    image_path, output_path = Path(image_path), Path(output_path)
    for target in (output_path, Path(report_path) if report_path else None):
        if target is not None and target.exists():
            raise ValueError(f"{target.name} already exists; a snapped copy never overwrites a file (choose a new name)")
    with Image.open(image_path) as opened:
        native, report = snap(opened, colours)
    shown = image_path.resolve().relative_to(Path(root).resolve()).as_posix() if root and common.inside(image_path, root) else image_path.name
    report = {"kind": "working copy; the original is untouched", "source": {"file": shown, "sha256": common.sha256_file(image_path)},
              "output": output_path.name, **report}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle = output_path.with_name(output_path.name + ".tmp")
    native.save(handle, format="PNG")
    common.replace_file(handle, output_path)
    if report_path:
        common.atomic_write_json(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="A new file; an existing one is never overwritten")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--palette", type=Path, help="A saved .palette.json to snap the colours to")
    parser.add_argument("--game-root", type=Path, help="Use the game's own palette (art_style.palette_reference) when it has one")
    args = parser.parse_args()
    try:
        colours = None
        if args.palette:
            colours = palette.load_palette(args.palette)
        elif args.game_root:
            settings, _, _ = common.load_project_settings(args.game_root, require_confirmed=False)
            colours = palette.project_palette(args.game_root, settings)
        print(json.dumps(snap_file(args.image, args.output, colours, args.report, args.game_root), indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
