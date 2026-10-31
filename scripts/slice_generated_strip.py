#!/usr/bin/env python3
"""Cut one generated animation strip (or grid) into individual frames, measured, and write the job that build_sheet_atlas.py takes.

  python scripts/slice_generated_strip.py --source STRIP.png --frames 8 --out FOLDER --name hero_clap_e [--columns 8]
         [--direction E --action clap] [--reference ONE_APPROVED_POSE.png] [--planted] [--tolerance 0.05] [--neutral-ends] [--crown 30]

An image tool returns every action as ONE picture holding all its figures. Cutting that into equal slices cuts through limbs, and eyeballing the
cuts is how frames end up with a neighbour's hand in them. The cut here is measured, as the football project that gets this right does it:
- Each cut is the transparent (or exact-key) gutter nearest the expected boundary, searched within a fifth of a cell either way. A gutter that
  holds a few stray specks (8 pixels or fewer) is cut at its emptiest column and reported as a warning; where there is no gutter at all the
  strip is refused, with the place and the count, because a cut there would go through a limb.
- A figure that touches the picture's edge was clipped by the tool and is refused; so is an empty cell. The source is never changed.
- Every figure is placed on one frame size with the same pivot (the centre of the planted sole, on one baseline), so a frame never jumps.
- With --reference (one approved pose of the same figure) one scale must bring every frame within --tolerance (5% by default) of the
  reference's height. When no single scale does, the strip is refused: frames are never rescaled one by one. The scale is reported, not applied.
- With --planted (an action that keeps its feet down) the feet must stay on one baseline (within 2% of the figure's height) and the figure's
  height must not drift by more than the tolerance across the frames.
The strip is either exact #FF00FF key (no transparent pixel) or true alpha (art where alpha > 153); alpha frames are written as alpha and the job
sets soft_alpha. Frames are numbered in reading order. An existing output folder with files in it is never written into.
- With --neutral-ends (an action that returns to the neutral pose) the first and last figure of every row must stand at the same height and on the
  same baseline within the tolerance, and in a grid the neutral pose's height must agree across rows; widths that differ by more than 10% are
  reported. The football project measured exactly this (neutral stature within about 2%) and found endpoints that were not identical copies.
- With --crown PERCENT (a subject with a head: a human or an animal; not a vehicle, building, structure or plant) the widest run of art in the top PERCENT of every figure, its head width, must stay within
  --crown-tolerance (10%) of the reference's, or of the first frame's: a posed height changes when the figure crouches or jumps, a head does not.
- With --reference the strip is also compared with it as rough stand-ins for "the same figure": the mean colour of every figure, and, with --neutral-ends
  (frame 0 is the neutral pose), the proportions and the top lighting of frame 0. A difference beyond the limit is a `match_flags` entry that sends the
  picture to review; it never refuses a strip and never proves a match or a mismatch.
Mechanical measurements only: whether the facing, the camera elevation and the figure are right is judged by a reviewer looking at the picture
(gamearts_candidates.py review), and the owner approves.
"""
import argparse
import json
import sys
from pathlib import Path

import gamearts_common as common

ALPHA_INK = 153           # an alpha above 60% is art; fainter pixels are antialias haze or stray specks
GUTTER_MIN_PX = 3         # a clear gutter is at least this wide
SPARSE_GUTTER_MAX = 8     # specks in the emptiest column that are reported, not refused
SEARCH_FRACTION = 0.2     # how far from the expected boundary to look, as a fraction of a cell
BASELINE_DRIFT = 0.02
WIDTH_REPORT = 0.10       # neutral endpoints whose widths differ by more than this are reported
CROWN_TOLERANCE = 0.10
COLOUR_FLAG = 0.12        # mean colour of the art farther than this share of the RGB range from the reference's: probably another figure or another palette
SHAPE_FLAG = 0.25         # neutral figure whose proportions differ from the reference's by more than this share
TOP_BAND = 0.25           # the top share of a figure read as its upper surface / head when comparing how it is lit
SOLE_FRACTION = 0.15      # the bottom of the figure that holds the planted sole
PADDING = 2
MIN_KEY_FRACTION = 0.05   # an opaque strip must be at least this much exact key, or its background was not keyed


def ink_mask(image):
    """(mask, is_alpha): 'L' mask, 255 where there is art. True alpha when any pixel is not opaque, otherwise everything that is not the exact key."""
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return alpha.point(lambda v: 255 if v > ALPHA_INK else 0), True
    return common.nonkey_mask(image), False


def _occupied(mask, horizontal, at, lo, hi):
    """Art pixels on the row (horizontal) or column at `at`, between lo and hi along it."""
    box = (lo, at, hi, at + 1) if horizontal else (at, lo, at + 1, hi)
    return mask.crop(box).histogram()[255]


def find_cut(mask, horizontal, expected, radius, lo, hi, label):
    """(position, warning or None): the clear gutter nearest `expected`; the emptiest position when it holds only specks; ValueError when it holds a limb."""
    start, best, distance = None, None, None
    least, least_at = None, expected
    top = expected + radius
    for at in range(max(1, expected - radius), min(top, (mask.height if horizontal else mask.width) - 1) + 1):
        count = _occupied(mask, horizontal, at, lo, hi)
        if least is None or count < least:
            least, least_at = count, at
        clear = count == 0
        if clear and start is None:
            start = at
        if start is not None and (not clear or at == top):
            end = at if clear else at - 1
            if end - start + 1 >= GUTTER_MIN_PX:
                middle = (start + end) // 2
                if distance is None or abs(middle - expected) < distance:
                    best, distance = middle, abs(middle - expected)
            start = None
    if best is not None:
        return best, None
    if least is not None and least <= SPARSE_GUTTER_MAX:
        return least_at, f"{label}: no clear gutter near {expected}; cut at {least_at}, where {least} stray pixel(s) remain"
    raise ValueError(f"{label}: no transparent gutter near {expected} (the emptiest place, {least_at}, holds {least} art pixels). A cut there would go through a figure; "
                     "ask the tool again with wider gaps between the figures")


def cells(mask, columns, rows):
    """([(x0, y0, x1, y1)] in reading order, warnings): the cell of every figure, cut at measured gutters."""
    width, height = mask.size
    warnings, row_edges = [], [0]
    for row in range(1, rows):
        at, warning = find_cut(mask, True, round(height * row / rows), max(1, int(height / rows * SEARCH_FRACTION)), 0, width, f"row cut {row}")
        row_edges.append(at)
        warnings += [warning] if warning else []
    row_edges.append(height)
    found = []
    for row in range(rows):
        top, bottom = row_edges[row], row_edges[row + 1]
        edges = [0]
        for column in range(1, columns):
            at, warning = find_cut(mask, False, round(width * column / columns), max(1, int(width / columns * SEARCH_FRACTION)), top, bottom, f"row {row + 1} column cut {column}")
            edges.append(at)
            warnings += [warning] if warning else []
        edges.append(width)
        found += [(edges[column], top, edges[column + 1], bottom) for column in range(columns)]
    return found, warnings


def root_x(mask, bounds):
    """Centre of the planted sole: the span of the art in the bottom 15% of the figure's box."""
    left, top, right, bottom = bounds
    sole = mask.crop((left, max(top, bottom - max(2, round((bottom - top) * SOLE_FRACTION))), right, bottom)).getbbox()
    return left + (sole[0] + sole[2]) / 2.0


def crown_width(mask, bounds, percent):
    """The widest unbroken run of art in the top `percent` of the figure's box: its head width, which a crouch or a jump does not change."""
    import re
    left, top, right, bottom = bounds
    rows = max(1, round((bottom - top) * percent / 100))
    best = 0
    for y in range(top, min(bottom, top + rows)):
        data = mask.crop((left, y, right, y + 1)).tobytes()
        best = max([best] + [len(run.group()) for run in re.finditer(b"\xff+", data)])
    return best


def _art_stats(picture, mask, bounds):
    """(mean RGB, aspect, fill, top light) of one figure: its mean colour, width over height, share of its box that is art, and the brightness of its top band over its whole."""
    from PIL import ImageStat
    left, top, right, bottom = bounds
    art = mask.crop(bounds)
    rgb = picture.crop(bounds).convert("RGB")
    mean = ImageStat.Stat(rgb, mask=art).mean
    band = max(1, round((bottom - top) * TOP_BAND))
    grey = rgb.convert("L")
    whole = ImageStat.Stat(grey, mask=art).mean[0] or 1.0
    upper_mask = art.crop((0, 0, right - left, band))
    upper = ImageStat.Stat(grey.crop((0, 0, right - left, band)), mask=upper_mask).mean[0] if upper_mask.getbbox() else whole
    ink = (art.histogram()[255]) / float(max(1, (right - left) * (bottom - top)))
    return mean, (right - left) / float(bottom - top), ink, upper / whole


def match_reference(figures, picture, mask, ref_image, ref_mask, ref_box, neutral_first):
    """Rough, measured stand-ins for 'is this the same figure, lit and proportioned alike': the colour of every figure against the reference, and (when frame 0 is
    the neutral pose) its proportions and top lighting. Returns (per-figure numbers, flags). A flag asks a reviewer to look; it never proves a mismatch or a match."""
    ref_mean, ref_aspect, ref_fill, ref_light = _art_stats(ref_image, ref_mask, ref_box)
    numbers, flags = [], []
    for figure in figures:
        mean = _art_stats(picture, mask, tuple(figure["bounds"]))[0]
        distance = round(sum((a - b) ** 2 for a, b in zip(mean, ref_mean)) ** 0.5 / (3 * 255 * 255) ** 0.5, 4)
        numbers.append({"index": figure["index"], "colour_distance": distance})
        if distance > COLOUR_FLAG:
            flags.append(f"frame {figure['index']}: the mean colour of the art is {distance:.0%} of the colour range from the reference's, so this may be another figure or another palette")
    if neutral_first:
        _, aspect, fill, light = _art_stats(picture, mask, tuple(figures[0]["bounds"]))
        numbers[0].update({"aspect": round(aspect, 3), "reference_aspect": round(ref_aspect, 3), "fill": round(fill, 3), "reference_fill": round(ref_fill, 3), "top_light": round(light, 3), "reference_top_light": round(ref_light, 3)})
        for label, got, wanted in (("width over height", aspect, ref_aspect), ("share of its box that is art", fill, ref_fill), ("brightness of its top band over the whole", light, ref_light)):
            if abs(got - wanted) / wanted > SHAPE_FLAG:
                flags.append(f"frame 0: the {label} is {got:.2f} against {wanted:.2f} in the reference, more than {SHAPE_FLAG:.0%} apart, so the proportions or the camera angle may differ")
    return numbers, flags


def single_scale(heights, reference_height, tolerance):
    """The one scale that brings every figure within `tolerance` of the reference's height, as (lower, upper); lower > upper means none does."""
    lower = max(reference_height * (1 - tolerance) / height for height in heights)
    upper = min(reference_height * (1 + tolerance) / height for height in heights)
    return lower, upper


def slice_strip(source, frames, columns=None, reference=None, planted=False, tolerance=0.05, neutral_ends=False, crown=None, crown_tolerance=CROWN_TOLERANCE):
    """The measurements and the cut figures of one strip: {frames: [...], warnings: [...], scale, alpha, images}. Raises ValueError, naming the measurement, when the strip is not safe to cut."""
    from PIL import Image
    if frames < 1:
        raise ValueError("--frames must be at least 1")
    columns = columns or frames
    if frames % columns:
        raise ValueError(f"{frames} frames do not fit {columns} columns")
    rows = frames // columns
    with Image.open(source) as opened:
        picture = opened.convert("RGBA")
    mask, alpha = ink_mask(picture)
    width, height = picture.size
    keyed = width * height - mask.histogram()[255]
    if not alpha and keyed < width * height * MIN_KEY_FRACTION:  # an opaque picture whose background is not the exact key (a tool's blurred magenta, a photo-like fill)
        raise ValueError(f"the picture is neither on an exact {common.KEY_HEX} background ({keyed} exact-key pixels of {width * height}) nor true alpha, so figures cannot be told from background; "
                         "key the background first (snap_to_pixel_grid.py --clean writes it as the exact key) or ask the tool for a transparent picture")
    grid, warnings = cells(mask, columns, rows)
    figures = []
    for number, (x0, y0, x1, y1) in enumerate(grid):
        box = mask.crop((x0, y0, x1, y1)).getbbox()
        if box is None:
            raise ValueError(f"frame {number}: its cell holds no artwork")
        bounds = (x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3])
        if bounds[0] <= 0 or bounds[1] <= 0 or bounds[2] >= width or bounds[3] >= height:
            raise ValueError(f"frame {number}: the figure touches the picture's edge, so the tool clipped it; ask for the strip again with more empty space around the figures")
        figures.append({"index": number, "cell": [x0, y0, x1, y1], "bounds": list(bounds), "root_x": root_x(mask, bounds), "size": [bounds[2] - bounds[0], bounds[3] - bounds[1]]})
    heights = [figure["size"][1] for figure in figures]
    if crown is not None and not 5 <= crown <= 60:
        raise ValueError("--crown must be a percentage from 5 to 60 of the figure's height")
    scale = None
    ref_box = ref_image = None
    if reference:
        with Image.open(reference) as opened:
            ref_image = opened.convert("RGBA")
        ref_mask = ink_mask(ref_image)[0]
        ref_box = ref_mask.getbbox()
        if ref_box is None:
            raise ValueError("the reference picture holds no artwork")
        lower, upper = single_scale(heights, ref_box[3] - ref_box[1], tolerance)
        if lower > upper:
            raise ValueError(f"no single scale brings every frame within {tolerance:.0%} of the reference's height ({lower:.3f} needed at least, {upper:.3f} at most); "
                             "the figure changes size across the strip, and frames are not rescaled one by one")
        scale = round((lower + upper) / 2, 4)
    if crown is not None:
        for figure in figures:
            figure["crown"] = crown_width(mask, figure["bounds"], crown)
        wanted = crown_width(ref_mask, ref_box, crown) if ref_box else figures[0]["crown"]
        for figure in figures:
            if abs(figure["crown"] - wanted) / wanted > crown_tolerance:
                raise ValueError(f"frame {figure['index']}: the head (crown) is {figure['crown']} px wide against {wanted} px {'in the reference' if ref_box else 'in frame 0'}, more than {crown_tolerance:.0%} apart; "
                                 "the figure's head changed size, so this is not the same figure at one scale")
    if neutral_ends:
        for row in range(rows):
            first, last = figures[row * columns], figures[row * columns + columns - 1]
            label = f"row {row + 1}" if rows > 1 else "the strip"
            if abs(first["size"][1] - last["size"][1]) / first["size"][1] > tolerance:
                raise ValueError(f"{label}: the first and last figures are asked to be the same neutral pose, but are {first['size'][1]} and {last['size'][1]} px tall (more than {tolerance:.0%} apart)")
            if abs(first["bounds"][3] - last["bounds"][3]) / first["size"][1] > BASELINE_DRIFT:
                raise ValueError(f"{label}: the first and last figures stand on different baselines ({first['bounds'][3]} and {last['bounds'][3]})")
            if abs(first["size"][0] - last["size"][0]) / first["size"][0] > WIDTH_REPORT:
                warnings.append(f"{label}: the first and last figures differ in width ({first['size'][0]} and {last['size'][0]} px), so they are not identical copies of the neutral pose")
        if rows > 1:
            neutral = [figures[row * columns]["size"][1] for row in range(rows)]
            if (max(neutral) - min(neutral)) / min(neutral) > tolerance:
                raise ValueError(f"the neutral pose is {min(neutral)} to {max(neutral)} px tall across the rows (more than {tolerance:.0%} apart): the rows are not drawn at one scale")
    if planted:
        feet = [figure["bounds"][3] for figure in figures]
        stand = sorted(heights)[len(heights) // 2]
        for figure, foot in zip(figures, feet):
            if abs(foot - feet[0]) / stand > BASELINE_DRIFT:
                raise ValueError(f"frame {figure['index']}: the planted feet move {abs(foot - feet[0])} px from frame 0 (limit {BASELINE_DRIFT:.0%} of the figure's height)")
            if abs(figure["size"][1] - heights[0]) / heights[0] > tolerance:
                raise ValueError(f"frame {figure['index']}: the figure's height changes by more than {tolerance:.0%} from frame 0")
    match = flags = None
    if reference:
        match, flags = match_reference(figures, picture, mask, ref_image, ref_mask, ref_box, neutral_ends)
    return {"frames": figures, "warnings": warnings, "scale": scale, "alpha": alpha, "mask": mask, "picture": picture, "match": match, "match_flags": flags}


def write_frames(result, out, name, direction=None, action=None):
    """Put every figure on one frame size, root centred and feet on one baseline; write the frames and the build_sheet_atlas job. Returns the job."""
    from PIL import Image
    figures, picture = result["frames"], result["picture"]
    left_reach = max(figure["root_x"] - figure["bounds"][0] for figure in figures)
    right_reach = max(figure["bounds"][2] - figure["root_x"] for figure in figures)
    half = int(max(left_reach, right_reach)) + 1 + PADDING
    frame_w = half * 2
    frame_h = max(figure["size"][1] for figure in figures) + PADDING * 2
    background = (0, 0, 0, 0) if result["alpha"] else common.KEY_RGBA
    folder = Path(out)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError(f"{folder} already holds files; use a new folder (existing outputs are never overwritten)")
    folder.mkdir(parents=True, exist_ok=True)
    job_frames = []
    for figure in figures:
        x0, y0, x1, y1 = figure["bounds"]
        frame = Image.new("RGBA", (frame_w, frame_h), background)
        frame.paste(picture.crop((x0, y0, x1, y1)), (round(half - (figure["root_x"] - x0)), frame_h - PADDING - figure["size"][1]))  # copied as it is: the pixels are never edited
        file = f"{name}_{figure['index']:02d}.png"
        frame.save(folder / file)
        entry = {"file": file, "name": f"{name}_{figure['index']:02d}", "pivot": [half, frame_h - PADDING]}
        if direction:
            entry["direction"] = direction
        if action:
            entry["action"] = action
        job_frames.append(entry)
    job = {"name": name, "frames": job_frames}
    if result["alpha"]:
        job["soft_alpha"] = True
    common.validate_schema(job, "gamearts-frames-job")
    common.atomic_write_json(folder / f"{name}.job.json", job)
    return job, [frame_w, frame_h]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source", type=Path, required=True, help="The strip or grid the image tool returned (exact #FF00FF key, or true alpha)")
    parser.add_argument("--frames", type=int, required=True, help="How many figures the picture holds")
    parser.add_argument("--columns", type=int, help="Figures per row (default: all in one row)")
    parser.add_argument("--out", type=Path, help="A new folder for the frames and the job (not needed with --check-only)")
    parser.add_argument("--name", help="The sheet's name; frames are NAME_00.png, NAME_01.png ... (not needed with --check-only)")
    parser.add_argument("--check-only", action="store_true", help="Measure the picture and report; write nothing. Run it on every generated picture as soon as the tool returns it, before showing it to anyone")
    parser.add_argument("--direction")
    parser.add_argument("--action")
    parser.add_argument("--reference", type=Path, help="One approved pose of the same figure, to measure the scale")
    parser.add_argument("--planted", action="store_true", help="The action keeps its feet down: check the baseline and the height")
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--neutral-ends", action="store_true", help="The action returns to the neutral pose: the first and last figure of every row must match, and the rows must agree")
    parser.add_argument("--crown", type=int, help="Measure the head: the widest run of art in the top PERCENT of every figure must stay the same width")
    parser.add_argument("--crown-tolerance", type=float, default=CROWN_TOLERANCE)
    args = parser.parse_args(argv)
    if not args.check_only and not (args.out and args.name):
        parser.error("--out and --name are needed unless --check-only")
    try:
        result = slice_strip(args.source, args.frames, args.columns, args.reference, args.planted, args.tolerance, args.neutral_ends, args.crown, args.crown_tolerance)
        if args.check_only:
            print(json.dumps({"status": "checked", "frames": len(result["frames"]), "alpha": result["alpha"], "scale": result["scale"], "warnings": result["warnings"],
                              "match": result["match"], "match_flags": result["match_flags"],
                              "measured": [{key: f[key] for key in ("index", "size", "root_x", "crown") if key in f} for f in result["frames"]],
                              "not_assessed": ["whether the poses are the right ones", "whether every frame is the same figure", "whether each figure shows its facing: compare it with the turnaround"]}, indent=2))
            return 0
        job, frame_size = write_frames(result, args.out, args.name, args.direction, args.action)
    except (ValueError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    report = {"status": "cut", "frames": len(job["frames"]), "frame_size": frame_size, "pivot": job["frames"][0]["pivot"], "alpha": result["alpha"], "scale": result["scale"],
              "warnings": result["warnings"], "match": result["match"], "match_flags": result["match_flags"], "job": (args.out / f"{args.name}.job.json").as_posix(),
              "measured": [{key: f[key] for key in ("index", "size", "root_x", "crown") if key in f} for f in result["frames"]],
              "not_assessed": ["whether the poses are the right ones", "whether every frame is the same figure"]}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
