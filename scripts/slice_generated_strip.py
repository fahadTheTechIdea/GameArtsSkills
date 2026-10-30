#!/usr/bin/env python3
"""Cut one generated animation strip (or grid) into individual frames, measured, and write the job that build_sheet_atlas.py takes.

  python scripts/slice_generated_strip.py --source STRIP.png --frames 8 --out FOLDER --name hero_clap_e [--columns 8]
         [--direction E --action clap] [--reference ONE_APPROVED_POSE.png] [--planted] [--tolerance 0.05]

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
Mechanical measurements only: whether the poses are the right ones, and the same figure, is the owner's judgement.
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


def single_scale(heights, reference_height, tolerance):
    """The one scale that brings every figure within `tolerance` of the reference's height, as (lower, upper); lower > upper means none does."""
    lower = max(reference_height * (1 - tolerance) / height for height in heights)
    upper = min(reference_height * (1 + tolerance) / height for height in heights)
    return lower, upper


def slice_strip(source, frames, columns=None, reference=None, planted=False, tolerance=0.05):
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
    scale = None
    if reference:
        with Image.open(reference) as opened:
            ref_image = opened.convert("RGBA")
        ref_box = ink_mask(ref_image)[0].getbbox()
        if ref_box is None:
            raise ValueError("the reference picture holds no artwork")
        lower, upper = single_scale(heights, ref_box[3] - ref_box[1], tolerance)
        if lower > upper:
            raise ValueError(f"no single scale brings every frame within {tolerance:.0%} of the reference's height ({lower:.3f} needed at least, {upper:.3f} at most); "
                             "the figure changes size across the strip, and frames are not rescaled one by one")
        scale = round((lower + upper) / 2, 4)
    if planted:
        feet = [figure["bounds"][3] for figure in figures]
        stand = sorted(heights)[len(heights) // 2]
        for figure, foot in zip(figures, feet):
            if abs(foot - feet[0]) / stand > BASELINE_DRIFT:
                raise ValueError(f"frame {figure['index']}: the planted feet move {abs(foot - feet[0])} px from frame 0 (limit {BASELINE_DRIFT:.0%} of the figure's height)")
            if abs(figure["size"][1] - heights[0]) / heights[0] > tolerance:
                raise ValueError(f"frame {figure['index']}: the figure's height changes by more than {tolerance:.0%} from frame 0")
    return {"frames": figures, "warnings": warnings, "scale": scale, "alpha": alpha, "mask": mask, "picture": picture}


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
    parser.add_argument("--out", type=Path, required=True, help="A new folder for the frames and the job")
    parser.add_argument("--name", required=True, help="The sheet's name; frames are NAME_00.png, NAME_01.png ...")
    parser.add_argument("--direction")
    parser.add_argument("--action")
    parser.add_argument("--reference", type=Path, help="One approved pose of the same figure, to measure the scale")
    parser.add_argument("--planted", action="store_true", help="The action keeps its feet down: check the baseline and the height")
    parser.add_argument("--tolerance", type=float, default=0.05)
    args = parser.parse_args(argv)
    try:
        result = slice_strip(args.source, args.frames, args.columns, args.reference, args.planted, args.tolerance)
        job, frame_size = write_frames(result, args.out, args.name, args.direction, args.action)
    except (ValueError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    report = {"status": "cut", "frames": len(job["frames"]), "frame_size": frame_size, "pivot": job["frames"][0]["pivot"], "alpha": result["alpha"], "scale": result["scale"],
              "warnings": result["warnings"], "job": (args.out / f"{args.name}.job.json").as_posix(),
              "measured": [{"index": f["index"], "size": f["size"], "root_x": f["root_x"]} for f in result["frames"]],
              "not_assessed": ["whether the poses are the right ones", "whether every frame is the same figure"]}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
