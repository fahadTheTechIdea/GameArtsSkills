#!/usr/bin/env python3
"""Measure what the new picture analysis costs at 2048 px and 4096 px (plan P11.7). Measured, not asserted.

  python plans/enhancements/evidence/timing_p11.py [--repeat 3] [--out timing_p11.json]

Every input is synthetic and generated here from a fixed seed: pixel art drawn at 1/8 of the size and enlarged 8x with nearest neighbour (so
the pixel-grid check and the snapper have a real grid to find), and a smooth gradient picture (many colours, no grid). Each timing is the best of
`--repeat` runs, in seconds, on this machine; the machine and versions are recorded with the numbers.
"""
import argparse
import itertools
import json
import platform
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from PIL import Image, __version__ as PILLOW  # noqa: E402

import check_animation  # noqa: E402
import gamearts_palette as palette  # noqa: E402
import gamearts_pixelgrid as grid  # noqa: E402
import render_preview as preview  # noqa: E402
import snap_to_pixel_grid as snapper  # noqa: E402
import validate_style_conformance as conformance  # noqa: E402

INKS = [(20, 24, 46), (92, 64, 51), (201, 138, 74), (233, 213, 168), (74, 124, 89), (160, 60, 60), (60, 90, 160), (240, 240, 230)]


def pixel_art(side, block=8, seed=3):
    rng = random.Random(seed)
    small = Image.new("RGB", (side // block, side // block), (255, 0, 255))
    pixels = small.load()
    for y in range(2, small.height - 2):
        for x in range(2, small.width - 2):
            pixels[x, y] = rng.choice(INKS)
    return small.resize((side, side), Image.NEAREST)


def gradient(side):
    ramp = Image.linear_gradient("L").resize((side, side))
    return Image.merge("RGB", (ramp, ramp.transpose(Image.Transpose.ROTATE_90), ramp.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))


def best(function, repeat):
    times = []
    for _ in range(repeat):
        started = time.perf_counter()
        result = function()
        times.append(time.perf_counter() - started)
    return round(min(times), 3), result


def real_sheet(folder, frames, cell=48):
    """A real sheet and atlas from the framework's own builder: `frames` frames of one walking block, 16 to a row."""
    from build_sheet_atlas import build as build_sheet
    source = Path(folder) / f"frames_{frames}"
    source.mkdir()
    items = []
    for index in range(frames):
        image = Image.new("RGBA", (cell, cell), (255, 0, 255, 255))
        image.paste(Image.new("RGBA", (16, 16), (40, 90, 160, 255)), (8 + index % 9, 20))
        image.save(source / f"f{index}.png")
        items.append({"file": f"f{index}.png", "name": f"walk_{index}", "direction": "E", "action": "walk", "pivot": [24, 40], "duration_ms": 100})
    build_sheet({"_input_dir": str(source), "name": f"sheet_{frames}", "asset_id": "timing", "columns": min(16, frames), "padding": 2, "frames": items}, Path(folder))
    return Path(folder) / f"sheet_{frames}.png", Path(folder) / f"sheet_{frames}.atlas.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("timing_p11.json"))
    args = parser.parse_args()
    results = {"machine": {"python": platform.python_version(), "pillow": PILLOW, "system": platform.platform(), "processor": platform.processor()},
               "repeat": args.repeat, "seconds": {}}
    for side in (2048, 4096):
        art, smooth = pixel_art(side), gradient(side)
        names = itertools.count()  # a palette is never overwritten, so each repeat saves under a new name
        art_rgba = art.convert("RGBA")
        row = {}
        row["colour_counts_pixel_art"], counts = best(lambda: palette.art_colour_counts(art_rgba), args.repeat)
        row["colour_counts_gradient"], _ = best(lambda: palette.art_colour_counts(smooth.convert("RGBA")), args.repeat)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "art.png"
            art.save(source)
            row["palette_extract_pixel_art"], _ = best(lambda: palette.extract(source, f"timing{next(names)}", Path(folder) / "palette", 32, Path(folder)), args.repeat)
            smooth_source = Path(folder) / "smooth.png"
            smooth.save(smooth_source)
            row["palette_extract_gradient"], _ = best(lambda: palette.extract(smooth_source, f"smooth{next(names)}", Path(folder) / "palette", 32, Path(folder)), args.repeat)
        colours = list(counts)[:32]
        row["still_checks_pixel_art_with_palette"], report = best(
            lambda: conformance.run_checks(art_rgba, list(conformance.STILL_CHECKS), {"colour_count_max": {"max_colours": 32}}, colours), args.repeat)
        row["still_checks_gradient"], _ = best(
            lambda: conformance.run_checks(smooth.convert("RGBA"), list(conformance.STILL_CHECKS), {"colour_count_max": {"max_colours": 32}}, colours), args.repeat)
        row["edge_profiles"], _ = best(lambda: grid.edge_profiles(art), args.repeat)
        row["snap_to_pixel_grid"], snapped = best(lambda: snapper.snap(art), args.repeat)
        row["snap_output_size"] = list(snapped[0].size)
        row["still_check_statuses"] = {item["name"]: item["status"] for item in report}
        results["seconds"][str(side)] = row
    with tempfile.TemporaryDirectory() as folder:
        for frames in (16, 64, 256):
            sheet, atlas = real_sheet(folder, frames)
            results["seconds"][f"animation_{frames}_frames"] = {
                "sheet_size": list(Image.open(sheet).size),
                "check_animation": best(lambda: check_animation.check_sheet(sheet, atlas, {}), args.repeat)[0],
                "render_preview_strip_and_gif": best(lambda: preview.render(sheet, atlas, Path(folder) / "out"), args.repeat)[0]}
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
