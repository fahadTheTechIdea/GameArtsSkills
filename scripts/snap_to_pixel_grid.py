#!/usr/bin/env python3
"""Recover the native picture from pixel art that was drawn large: detect the grid, take each cell's middle colour, write a working copy.

  python scripts/snap_to_pixel_grid.py --image LARGE.png --output NATIVE.snapped.png [--report NATIVE.snapped.json] [--game-root GAME]
  python scripts/snap_to_pixel_grid.py --clean --image SOFT.png --output NATIVE.cleaned.png --report NATIVE.cleaned.json --game-root GAME
         [--target-long-side PX | --target-scale SOURCE_PX_PER_NATIVE_PX] [--margin PX]

Image generators often return 'pixel art' at ten times its real size, with cells that are not quite uniform and a grid whose size is not
a whole number. This finds the regular grid the colour changes sit on (gamearts_pixelgrid), reads the middle half of every cell (the middle of
its spread when the cell is uniform, its median colour when a stray line or speck crosses it), and, when the game has a palette (--game-root with art_style.palette_reference, or --palette), snaps each result to the nearest
palette colour. The original is never changed and an existing output is never overwritten. A picture with no consistent grid (already
native, flat, or not pixel art at all) is refused with the measured reason instead of being guessed at. The result is a working copy for
review: it is registered and approved like any other picture, never silently substituted for the original.

**Clean (`--clean`)** is for the picture an image tool returns when it cannot make a pixel grid at all: a soft, enlarged painting with some
hundred thousand colours, a non-whole enlargement, and a blurred magenta background (#FB03FB, not #FF00FF). It runs one deterministic route and
refuses, with the measured reason, wherever the picture cannot be cleaned safely:
1. The background is found by flooding in from the border with a tolerance measured from the border itself, specks of it are dropped, the blend
   fringe around the art is measured, and the background is written as the exact key with no near-key pixel left (`gamearts_matte.key_background`).
2. The art is cropped to its box and divided into native-size cells, by the size you give (`--target-long-side` is the art's longer side in native
   pixels, `--target-scale` is source pixels per native pixel) or, when you give none, by the grid it can estimate. A picture with neither a size nor
   a grid is refused, and so is a size that would enlarge the art. Each cell is reduced as in the plain snap, from the art pixels in it that are not
   fringe; a cell that is mostly background stays the key.
3. Every colour is snapped to the nearest palette colour by perceived distance (`gamearts_palette`), never to one that sits near the key.
The report gives the colour counts before and after, the scale, the colour error and the style checks the result passes or fails. These are
measurements of pixels; whether the art is good is the owner's to judge.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_matte as matte  # noqa: E402
import gamearts_palette as palette  # noqa: E402
import gamearts_pixelgrid as grid  # noqa: E402
import validate_style_conformance as style  # noqa: E402

MIN_SCORE = 0.6  # a grid must explain the picture's colour changes at least this far above what a random grid would
UNIFORM_SPREAD = 8  # a cell is uniform when no channel varies by more than this across its middle
KEEP_SHARE = 0.5  # a cell is background when more than this share of its source pixels is background
NO_PRESET_CHECKS = ("palette_exact", "palette_near", "pixel_grid", "integer_scale")  # what a result is checked against when the game has no style preset


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


# ------------------------------------------------------------------------------------------------ clean: a soft picture on a soft background
def _cell_colour(reds, greens, blues):
    """(colour, mean) of the source pixels of one cell. The colour is the middle of the spread when the cell is uniform and the per-channel median
    when it is not (a median keeps an edge on one side of it, where a mean would blend two materials into a third colour); the mean is the
    area average, kept to measure the colour error."""
    channels = (reds, greens, blues)
    if all(max(c) - min(c) <= UNIFORM_SPREAD for c in channels):
        colour = tuple((min(c) + max(c)) // 2 for c in channels)
    else:
        colour = tuple(_median(c) for c in channels)
    return colour, tuple(round(sum(c) / len(c)) for c in channels)


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle] + 1) // 2


def _near_key(colour):
    return max(abs(a - b) for a, b in zip(colour, common.KEY_RGB)) <= common.NEAR_KEY_TOLERANCE


def _scale(rgb, box, target_long_side, target_scale):
    """(source px per native px along x, along y, how it was settled, the grid that could be estimated, why none could). An explicit size is the
    owner's and wins; the estimate is still reported beside it, so a size far from what the picture's own grid says shows."""
    try:
        columns, rows = grid.edge_profiles(rgb.crop(box))
        (px, _, cx), (py, _, cy) = _detect(columns, "columns"), _detect(rows, "rows")
        estimate, why = {"cell_px": [px, py], "grid_score": [cx, cy]}, None
    except ValueError as exc:
        estimate, why = None, str(exc)
    if target_long_side is not None:
        factor = max(box[2] - box[0], box[3] - box[1]) / target_long_side
        return factor, factor, f"the target long side, {target_long_side} native pixels", estimate, why
    if target_scale is not None:
        return target_scale, target_scale, f"the target scale, {target_scale} source pixels per native pixel", estimate, why
    if estimate is None:
        raise ValueError(f"{why}. With no grid to estimate, give the native size yourself: --target-long-side (the art's longer side in native pixels) or --target-scale")
    return estimate["cell_px"][0], estimate["cell_px"][1], "the estimated grid", estimate, why


def clean(image, colours=None, target_long_side=None, target_scale=None, margin=0):
    """(native picture, report) for a soft picture on a soft key-coloured background. See the module description for the route and its refusals.
    `colours` (RGB tuples) snaps every art colour to the nearest of them; `margin` is key-coloured native pixels kept round the art."""
    from PIL import Image, ImageChops
    if target_long_side is not None and target_scale is not None:
        raise ValueError("Give the native size once: --target-long-side or --target-scale, not both")
    if target_long_side is not None and (not isinstance(target_long_side, int) or target_long_side < 1):
        raise ValueError("The target long side is a whole number of native pixels, at least 1")
    if target_scale is not None and not target_scale >= 1:
        raise ValueError("The target scale is source pixels per native pixel and must be at least 1; a smaller one would enlarge the picture")
    if not isinstance(margin, int) or margin < 0:
        raise ValueError("The margin is a whole number of key-coloured native pixels, 0 or more")
    rgba = image.convert("RGBA")
    if rgba.getchannel("A").getextrema() != (255, 255):
        raise ValueError("The picture has transparency: cleaning works on opaque pictures with a key-coloured background")
    rgb = rgba.convert("RGB")
    usable = None
    if colours:
        usable = [c for c in colours if not _near_key(c)]
        if not usable:
            raise ValueError("Every colour of the palette is the key colour or too close to it, so no art colour can be taken from it")
    background, fringe, keyed = matte.key_background(rgb)
    box = ImageChops.invert(background).getbbox()
    if box is None:
        raise ValueError("Nothing is left of the picture once its background is removed")
    sx, sy, how, estimate, why = _scale(rgb, box, target_long_side, target_scale)
    if sx < 1 or sy < 1:
        raise ValueError(f"The picture would have to be enlarged ({round(min(sx, sy), 3)} source pixels per native pixel): the art is smaller than the native size asked for")
    width, height = box[2] - box[0], box[3] - box[1]
    columns, rows = max(1, round(width / sx)), max(1, round(height / sy))
    state = Image.new("L", rgb.size, 2)  # 2 art, 1 art within the fringe, 0 background
    state.paste(1, mask=fringe)
    state.paste(0, mask=background)
    data, marks = rgb.crop(box).tobytes(), state.crop(box).tobytes()
    native = Image.new("RGB", (columns, rows), common.KEY_RGB)
    pixels, snapped, errors, enclosed, edge_only = native.load(), {}, [], 0, 0
    for j in range(rows):
        top, bottom = j * height // rows, (j + 1) * height // rows
        for i in range(columns):
            left, right = i * width // columns, (i + 1) * width // columns
            keyed_px, total, art, edge = 0, 0, ([], [], []), ([], [], [])
            for y in range(top, bottom):
                base = y * width
                run = marks[base + left:base + right]
                total += len(run)
                if run.count(0) == len(run):
                    keyed_px += len(run)
                    continue
                row = data[(base + left) * 3:(base + right) * 3]
                for k, flag in enumerate(run):
                    if not flag:
                        keyed_px += 1
                        continue
                    lists = art if flag == 2 else edge
                    lists[0].append(row[3 * k])
                    lists[1].append(row[3 * k + 1])
                    lists[2].append(row[3 * k + 2])
            if keyed_px > KEEP_SHARE * total:
                continue  # mostly background: the cell stays the exact key
            from_edge = not art[0]  # a cell that is all fringe (a thin line) has nothing cleaner to take its colour from
            edge_only += from_edge
            colour, mean = _cell_colour(*(edge if from_edge else art))
            if _near_key(colour):
                enclosed += 1  # art is never within the key's distance (the near-key rule), so this is key-coloured background that art encloses
                continue
            if usable:
                if colour not in snapped:
                    snapped[colour] = palette.nearest(colour, usable)
                colour = snapped[colour]
            errors.append(palette.lab_distance(colour, mean))
            pixels[i, j] = colour
    if not errors:
        raise ValueError("No native pixel is left as art: every cell was background or key-coloured")
    result = Image.new("RGB", (columns + 2 * margin, rows + 2 * margin), common.KEY_RGB)
    result.paste(native, (margin, margin))
    after = palette.art_colour_counts(result)
    palette_note = "none applied"
    if usable:
        palette_note = f"applied: every art cell snapped to the nearest of {len(usable)} palette colours"
        if len(usable) < len(colours):
            palette_note += f" ({len(colours) - len(usable)} near the key left out)"
    report = {"operation": "clean", "source_size": [rgb.width, rgb.height], "colours_before": len(rgb.getcolors(rgb.width * rgb.height)),
              "colours_after": len(after), "output_size": [result.width, result.height], "native_art_size": [columns, rows], "margin_px": margin,
              "background": keyed, "art_box": list(box), "art_size_px": [width, height],
              "scale": {"source_px_per_native_px": [round(width / columns, 4), round(height / rows, 4)], "settled_by": how,
                        "grid_estimate": estimate if estimate else f"none ({why})"},
              "cells": {"art": len(errors), "from_fringe_only": edge_only, "enclosed_background_keyed": enclosed},
              "colour_error": {"mean_delta_e76": round(sum(errors) / len(errors), 3), "max_delta_e76": round(max(errors), 3),
                               "against": "the area average of the cell's art pixels" + (", after the palette snap" if usable else "")},
              "method": "background keyed by flooding in from the border (measured tolerance, specks dropped, fringe kept out of edge colours); the art box is cut into native cells "
                        "(a cell that is mostly background stays the exact key); each cell takes the middle of its spread when uniform and its median colour otherwise",
              "palette": palette_note}
    return result, report


def _checks(native, colours, settings):
    """The key policy and the game's style checks, run on the result itself. A game with no style preset is checked for palette, grid and scale."""
    names, limits = style.checks_for(settings) if settings else ([], {})
    image = native.convert("RGBA")
    results = style.run_checks(image, names or list(NO_PRESET_CHECKS), limits, colours)
    policy = common.key_policy_report(image)
    return {"status": "failed" if policy["issues"] else style.overall(results), "key_policy": policy,
            "style": [{key: item[key] for key in ("name", "status", "detail")} for item in results], "not_assessed": list(style.NOT_ASSESSED)}


# ------------------------------------------------------------------------------------------------ files
def _refuse_existing(output_path, report_path):
    for target in (output_path, Path(report_path) if report_path else None):
        if target is not None and target.exists():
            raise ValueError(f"{target.name} already exists; a working copy never overwrites a file (choose a new name)")


def _shown(image_path, root):
    return image_path.resolve().relative_to(Path(root).resolve()).as_posix() if root and common.inside(image_path, root) else image_path.name


def _write_copy(native, output_path, report, report_path):
    """Write a working copy and its report; the report comes last, so a report always names a picture that exists."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle = output_path.with_name(output_path.name + ".tmp")
    native.save(handle, format="PNG")
    common.replace_file(handle, output_path)
    if report_path:
        common.atomic_write_json(report_path, report)


def snap_file(image_path, output_path, colours=None, report_path=None, root=None):
    """Snap one file into a new file (and an optional report). Nothing is written when the picture is refused."""
    from PIL import Image
    image_path, output_path = Path(image_path), Path(output_path)
    _refuse_existing(output_path, report_path)
    with Image.open(image_path) as opened:
        native, report = snap(opened, colours)
    report = {"kind": "working copy; the original is untouched", "source": {"file": _shown(image_path, root), "sha256": common.sha256_file(image_path)},
              "output": output_path.name, **report}
    _write_copy(native, output_path, report, report_path)
    return report


def clean_file(image_path, output_path, colours=None, report_path=None, root=None, settings=None, **options):
    """Clean one file into a new file (and an optional report), checked after it is made. Nothing is written when the picture is refused."""
    from PIL import Image
    image_path, output_path = Path(image_path), Path(output_path)
    _refuse_existing(output_path, report_path)
    with Image.open(image_path) as opened:
        native, report = clean(opened, colours, **options)
    report = {"kind": "working copy; the original is untouched. Register and approve it like any other picture, the owner still judges it",
              "source": {"file": _shown(image_path, root), "sha256": common.sha256_file(image_path)}, "output": output_path.name, **report,
              "checks": _checks(native, colours, settings)}
    _write_copy(native.convert("RGBA"), output_path, report, report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="A new file; an existing one is never overwritten")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--palette", type=Path, help="A saved .palette.json to snap the colours to")
    parser.add_argument("--game-root", type=Path, help="Use the game's own palette (art_style.palette_reference) when it has one")
    parser.add_argument("--clean", action="store_true", help="Clean a soft picture on a soft key-coloured background (see above) instead of snapping a pixel grid")
    parser.add_argument("--target-long-side", type=int, help="--clean: the art's longer side, in native pixels")
    parser.add_argument("--target-scale", type=float, help="--clean: source pixels per native pixel")
    parser.add_argument("--margin", type=int, default=0, help="--clean: key-coloured native pixels kept round the art")
    args = parser.parse_args()
    try:
        if not args.clean and (args.target_long_side is not None or args.target_scale is not None or args.margin):
            raise ValueError("--target-long-side, --target-scale and --margin belong to --clean")
        colours, settings = None, None
        if args.game_root:
            settings, _, _ = common.load_project_settings(args.game_root, require_confirmed=False)
        if args.palette:
            colours = palette.load_palette(args.palette)
        elif settings:
            colours = palette.project_palette(args.game_root, settings)
        if args.clean:
            report = clean_file(args.image, args.output, colours, args.report, args.game_root, settings, target_long_side=args.target_long_side,
                                target_scale=args.target_scale, margin=args.margin)
        else:
            report = snap_file(args.image, args.output, colours, args.report, args.game_root)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
