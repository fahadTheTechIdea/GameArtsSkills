#!/usr/bin/env python3
"""Style-conformance checks: measure whether a picture keeps the promises of the look the game chose.

  python scripts/validate_style_conformance.py --game-root GAME --image SHEET.png [--checks palette_exact,pixel_grid]

The checks and their limits come from the game's style preset (`required_checks`, `check_parameters`); the palette comes from
`art_style.palette_reference`. Each check reports `passed`, `failed` or `untested` (it could not be measured, and says why); the overall
status is failed if any failed, otherwise untested if any could not be measured, otherwise passed. These are measurements of pixels:
they find an off-palette colour, a picture drawn large and shrunk, a blurred upscale. They cannot tell whether the art is good.
The technical artwork gate runs the same checks on every sheet of a bundle (see `bundle_report`); exit status 1 means a check failed.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_animation as animation  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_palette as palette  # noqa: E402
import gamearts_pixelgrid as grid  # noqa: E402
import gamearts_presets as presets  # noqa: E402

STILL_CHECKS = ("palette_exact", "palette_near", "colour_count_max", "pixel_grid", "integer_scale")
CHECKS = STILL_CHECKS + animation.CHECK_NAMES  # the presets' schema lists exactly these (a test keeps them equal)
MAX_NEAR_COLOURS = 20000  # more distinct colours than this are not compared one by one
MIN_EDGES = 16  # fewer colour changes than this on an axis cannot show a grid
EDGE_SHARE = 0.1  # a column or row counts as an edge when this share of the strongest one changes colour across it
MAX_BLOCK = 32
MIN_RUNS = 200
NO_PALETTE = "no palette is recorded for this game: extract one from the approved style board and set art_style.palette_reference"
NOT_ASSESSED = ("whether the art is good, or matches the approved look to the eye",
                "a deliberate exception (a soft effect inside pixel art)",
                "colour harmony and readability at the size the game shows it")

overall = animation.overall


def _result(name, status, detail, **measured):
    return {"name": name, "status": status, "detail": detail, "measured": measured}


def _hex(colour):
    return palette.hex_of(colour)


# ------------------------------------------------------------------------------------------------ colour checks
def check_colour_count_max(counts, params):
    limit = params.get("max_colours")
    if limit is None:
        return _result("colour_count_max", "untested", "The game's look sets no colour limit")
    used = len(counts)
    return _result("colour_count_max", "passed" if used <= limit else "failed",
                   f"The artwork uses {used} colours (limit {limit})", colours=used, max_colours=limit)


def check_palette_exact(counts, colours, note):
    if colours is None:
        return _result("palette_exact", "untested", note)
    allowed = set(colours)
    off = {colour: n for colour, n in counts.items() if colour not in allowed}
    pixels = sum(off.values())
    examples = [_hex(c) for c, _ in sorted(off.items(), key=lambda item: (-item[1], item[0]))[:3]]
    return _result("palette_exact", "passed" if not off else "failed",
                   "Every artwork pixel uses a palette colour" if not off else f"{pixels} pixels use {len(off)} colours that are not in the palette",
                   off_palette_pixels=pixels, off_palette_colours=len(off), examples=examples)


def check_palette_near(counts, colours, note, params):
    if colours is None:
        return _result("palette_near", "untested", note)
    if len(counts) > MAX_NEAR_COLOURS:
        return _result("palette_near", "untested", f"The artwork has {len(counts)} distinct colours, too many to compare one by one; "
                       "reduce them first or use the colour-count check", colours=len(counts))
    limit, allowed_share = params.get("max_lab_distance", 10), params.get("max_off_share", 0.02)
    total = sum(counts.values())
    off = worst = 0
    for colour, n in counts.items():
        distance = min(palette.lab_distance(colour, candidate) for candidate in colours)
        worst = max(worst, distance)
        if distance > limit:
            off += n
    share = round(off / total, 4) if total else 0.0
    status = "passed" if share <= allowed_share else "failed"
    return _result("palette_near", status, f"{round(share * 100, 2)}% of the artwork is further than {limit} from every palette colour "
                   f"(allowed {round(allowed_share * 100, 2)}%)", off_share=share, worst_distance=round(worst, 2), max_lab_distance=limit)


# ------------------------------------------------------------------------------------------------ grid checks
def check_pixel_grid(image, params):
    min_aligned = params.get("min_aligned_share", 0.98)
    columns, rows = (grid.strong_positions(profile, EDGE_SHARE) for profile in grid.edge_profiles(image))
    block_x = grid.block_size(columns, min_aligned, MIN_EDGES, MAX_BLOCK)
    block_y = grid.block_size(rows, min_aligned, MIN_EDGES, MAX_BLOCK)
    if block_x is None and block_y is None:
        return _result("pixel_grid", "untested", "There are too few colour changes to tell whether the picture is built on a pixel grid")
    sizes = [b for b in (block_x, block_y) if b is not None]
    if max(sizes) >= 2:
        return _result("pixel_grid", "failed", f"The picture is built from {block_x} x {block_y} pixel blocks, so it was drawn larger than its native "
                       "size; deliver it at native size (the snap tool can recover it)", block_x=block_x, block_y=block_y)
    return _result("pixel_grid", "passed", "No block structure above one pixel: the picture is at its native pixel size", block_x=block_x, block_y=block_y)


def _runs(image, key):
    """Lengths of same-colour runs along a sample of rows and columns, ignoring the key colour and runs shorter than 3."""
    rgb = image.convert("RGB")
    width, height = rgb.size

    def pixels(strip):
        raw = strip.tobytes()
        return list(zip(raw[0::3], raw[1::3], raw[2::3]))
    lines = []
    for y in sorted({round(i * (height - 1) / 63) for i in range(64)}) if height > 1 else [0]:
        lines.append(pixels(rgb.crop((0, y, width, y + 1))))
    for x in sorted({round(i * (width - 1) / 63) for i in range(64)}) if width > 1 else [0]:
        lines.append(pixels(rgb.crop((x, 0, x + 1, height))))
    lengths = {}
    for line in lines:
        start = 0
        for i in range(1, len(line) + 1):
            if i == len(line) or line[i] != line[start]:
                length = i - start
                if line[start] != common.KEY_RGB and length >= 3:
                    lengths[length] = lengths.get(length, 0) + 1
                start = i
    return lengths


def check_integer_scale(image):
    lengths = _runs(image, common.KEY_RGB)
    total = sum(lengths.values())
    if total < MIN_RUNS:
        return _result("integer_scale", "untested", f"Only {total} runs of 3 or more identical pixels were found, too few to tell how the picture was scaled", runs=total)
    pair = max(((lengths.get(k, 0) + lengths.get(k + 1, 0), k) for k in lengths if k >= 3), default=(0, 0))
    best, length = pair
    share = best / total
    both = min(lengths.get(length, 0), lengths.get(length + 1, 0)) / total
    if share >= 0.75 and both >= 0.15:
        return _result("integer_scale", "failed", f"Runs of identical pixels are {length} or {length + 1} long ({round(share * 100)}% of them): the picture was "
                       "enlarged by a non-whole number, which smears the pixel grid", pair=[length, length + 1], pair_share=round(share, 3), runs=total)
    return _result("integer_scale", "passed", "No sign of an enlargement by a non-whole number", runs=total)


CHECK_FUNCTIONS = {"palette_exact": lambda image, counts, params, colours, note: check_palette_exact(counts, colours, note),
                   "palette_near": lambda image, counts, params, colours, note: check_palette_near(counts, colours, note, params),
                   "colour_count_max": lambda image, counts, params, colours, note: check_colour_count_max(counts, params),
                   "pixel_grid": lambda image, counts, params, colours, note: check_pixel_grid(image, params),
                   "integer_scale": lambda image, counts, params, colours, note: check_integer_scale(image)}


def run_checks(image, names, params, colours, palette_note=None):
    """Run the named still-image checks on one picture; `params` maps a check name to its limits, `colours` is the game's palette or None."""
    for name in names:
        if name in animation.CHECK_NAMES:
            raise ValueError(f"{name} is an animation check; run it with check_animation.py on a sheet and its atlas")
        if name not in CHECK_FUNCTIONS:
            raise ValueError(f"Unknown style check {name!r}; use {', '.join(STILL_CHECKS)}")
    counts = palette.art_colour_counts(image)
    return [CHECK_FUNCTIONS[name](image, counts, params.get(name, {}), colours, palette_note or NO_PALETTE) for name in names]


# ------------------------------------------------------------------------------------------------ a game's checks
def checks_for(settings):
    """(check names, their limits) the game's style preset requires of a still picture; nothing when it has no usable preset."""
    chosen = presets.resolve_style_preset(settings)
    if not chosen or not chosen.get("found"):
        return [], {}
    return [name for name in chosen["required_checks"] if name in STILL_CHECKS], chosen["check_parameters"]


def _game_palette(root, settings):
    """(colours, note): the game's palette, or None with the sentence that says why there is none."""
    try:
        colours = palette.project_palette(root, settings)
    except ValueError as exc:
        return None, str(exc)
    return colours, None if colours is not None else NO_PALETTE


def check_file(root, image_path, names=None):
    """The report for one picture of a game: its preset's checks (or `names`), its palette, and what was not assessed."""
    from PIL import Image
    settings, _, _ = common.load_project_settings(root, require_confirmed=False)
    chosen, limits = checks_for(settings)
    names = list(names) if names is not None else chosen
    colours, note = _game_palette(root, settings)
    with Image.open(image_path) as opened:
        results = run_checks(opened.convert("RGBA"), names, limits, colours, note)
    return {"status": overall(results), "image": Path(image_path).name, "checks": results, "not_assessed": list(NOT_ASSESSED)}


def bundle_report(folder, atlas_paths, settings, root, problem=None):
    """The style part of the technical artwork gate for one bundle: every sheet checked against the game's preset.

    `issues` lists the checks that failed (they block approval); an unreadable setting or a check that could not be measured is
    reported as untested and never blocks."""
    from PIL import Image
    if settings is None:
        return {"status": "untested" if problem else "not_applicable", "reason": problem or "no settings were supplied", "issues": []}
    names, limits = checks_for(settings)
    if not names:
        return {"status": "not_applicable", "reason": "the game has no style preset with checks for still pictures", "issues": []}
    chosen = presets.resolve_style_preset(settings)
    colours, note = _game_palette(root, settings)
    sheets, issues, every = [], [], []
    for atlas_path in atlas_paths:
        image_path = Path(folder) / common.read_json(atlas_path)["image"]
        with Image.open(image_path) as opened:
            results = run_checks(opened.convert("RGBA"), names, limits, colours, note)
        every += results
        sheets.append({"sheet": image_path.name, "checks": [{key: item[key] for key in ("name", "status", "detail")} for item in results]})
        issues += [f"{image_path.name}: style check {item['name']} failed: {item['detail']}" for item in results if item["status"] == "failed"]
    return {"status": overall(every), "preset": chosen["preset"], "sheets": sheets, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--checks", help="Comma-separated subset of: " + ", ".join(STILL_CHECKS))
    args = parser.parse_args()
    try:
        report = check_file(args.game_root, args.image, args.checks.split(",") if args.checks else None)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if report["status"] == "failed" else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
