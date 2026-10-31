#!/usr/bin/env python3
"""The matte: soft-edge coverage that rides beside a delivered sheet (plan P12.4, decision D-8).

A delivered sheet keeps every unused pixel at the exact key colour #FF00FF, and a pixel is either key or art, so it cannot carry a soft edge. When the
image tool can return true alpha (checked once, plan P12.0) a soft-edged look keeps its softness in a companion `<name>.matte.png`: an 8-bit coverage
picture of the same size, 0 exactly where the sheet is the key colour and 1 to 255 wherever it is art. The key sheet stays the canonical delivery and
every check on it is unchanged; the matte is additive, recorded in the atlas with its hash, and used only by the runtime export, which turns the
coverage into real alpha. This module is the one owner of what a matte is: how true alpha is split into the pair, and when a pair is consistent.

  python scripts/gamearts_matte.py split --image RGBA.png --output-dir DIR --name NAME     # true alpha -> NAME.png (key) + NAME.matte.png
  python scripts/gamearts_matte.py check --sheet S.png --matte S.matte.png                  # is the pair consistent

The same module owns the other way a picture comes to have a background that is not art: a picture that an image tool painted on a *soft* key-coloured
background (a blurred magenta such as #FB03FB, never the exact key). `key_background` finds that background by flooding in from the picture's border
with a tolerance measured from the border itself, and measures how wide the blend fringe around the art is; it changes nothing, and refuses with the
measured reason when the border is not key-coloured or the fringe is too wide to treat safely. The snapper (`snap_to_pixel_grid.py --clean`) uses it.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

SUFFIX = ".matte.png"
NUDGED_RED = 254  # a visible pixel whose colour is exactly the key is moved one step so artwork is never mistaken for background

MAX_KEY_TOLERANCE = 64  # a border further than this from the key is not a key-coloured background at all
BORDER_MIN_SHARE = 0.9  # at least this share of the border must lie within MAX_KEY_TOLERANCE of the key
PERCENTILE = 0.99  # the tolerance is taken from this percentile of the border's own distances, and the art's own tint from this percentile of its interior
TOLERANCE_HEADROOM = 4  # the tolerance is that percentile plus this much, so the background's own noise is inside it
MAX_FRINGE = 4  # source pixels: a blend fringe wider than this is refused
INTERIOR_DEPTH = MAX_FRINGE + 4  # art deeper than this from the background is where the art's own magenta tint is measured
TINT_HEADROOM = 12  # a pixel is tinted when its magenta tint exceeds the interior's percentile by this much
FRINGE_SHARE = 0.05  # a ring of pixels around the background is contaminated when at least this share of it is tinted
SPECK_SHARE = 0.0005  # a piece of art smaller than this share of the largest piece is a speck of the soft background, not art
MIN_GAP = 16  # source pixels: an enclosed key-coloured piece at least this big is a gap in the art (background), a smaller one is noise


def matte_name(sheet_name):
    """`hero.png` -> `hero.matte.png`."""
    if not sheet_name.endswith(".png"):
        raise ValueError(f"{sheet_name!r} is not a PNG sheet")
    return sheet_name[:-len(".png")] + SUFFIX


def split(rgba):
    """True alpha into the pair (key sheet, matte). Every pixel with any coverage becomes art at its own colour; every pixel with none becomes the exact key
    colour. The matte is the alpha channel unchanged, so what the tool drew soft stays soft."""
    from PIL import Image, ImageChops
    rgba = rgba.convert("RGBA")
    alpha = rgba.getchannel("A")
    visible = alpha.point(lambda v: 255 if v else 0)
    colour = rgba.convert("RGB")
    collides = ImageChops.multiply(ImageChops.invert(common.nonkey_mask(colour.convert("RGBA"))), visible)
    red, green, blue = colour.split()
    colour = Image.merge("RGB", (Image.composite(Image.new("L", rgba.size, NUDGED_RED), red, collides), green, blue))
    key = Image.composite(colour, Image.new("RGB", rgba.size, common.KEY_RGB), visible).convert("RGBA")
    return key, alpha


def problems(sheet, matte):
    """What is wrong with a (key sheet, matte) pair, in words; an empty list means they agree."""
    from PIL import ImageChops
    if matte.mode != "L":
        return [f"the matte must be an 8-bit coverage picture (mode L), not {matte.mode}"]
    if matte.size != sheet.size:
        return [f"the matte is {matte.width} x {matte.height} and the sheet is {sheet.width} x {sheet.height}; they must be the same size"]
    art = common.nonkey_mask(sheet.convert("RGBA"))
    covered = matte.point(lambda v: 255 if v else 0)
    found = []
    invisible_art = ImageChops.multiply(art, ImageChops.invert(covered)).histogram()[255]
    if invisible_art:
        found.append(f"{invisible_art} art pixels have no coverage in the matte (coverage 0 would make them vanish)")
    stray = ImageChops.multiply(ImageChops.invert(art), covered).histogram()[255]
    if stray:
        found.append(f"{stray} key-colour pixels have coverage in the matte (coverage must be 0 exactly where the sheet is the key colour)")
    return found


def check_files(sheet_path, matte_path):
    from PIL import Image
    with Image.open(sheet_path) as sheet, Image.open(matte_path) as matte:
        return problems(sheet.copy(), matte.copy())


def record(matte_path):
    """The atlas entry that ties a sheet to its matte."""
    matte_path = Path(matte_path)
    return {"file": matte_path.name, "sha256": common.sha256_file(matte_path)}


def atlas_problems(sheet_path, atlas):
    """Problems with the matte an atlas names: the file is there, it is the file the atlas recorded, and it agrees with the sheet. An atlas with no matte has none."""
    entry = atlas.get("matte")
    if entry is None:
        return []
    matte_path = Path(sheet_path).parent / entry["file"]
    if not matte_path.is_file():
        return [f"the atlas names the matte {entry['file']} and it is missing"]
    if common.sha256_file(matte_path) != entry["sha256"]:
        return [f"{entry['file']} is not the matte the atlas recorded (its hash differs)"]
    return [f"matte: {issue}" for issue in check_files(sheet_path, matte_path)]


def _border(distance):
    """The distances of every pixel on the picture's outermost rows and columns."""
    width, _ = distance.size
    raw = distance.tobytes()
    return list(raw[:width] + raw[-width:] + raw[0::width] + raw[width - 1::width])


def measure_tolerance(distance):
    """(tolerance, measurements) for flooding in from the border: the largest per-channel distance from the key a background pixel may have.

    The background of a picture an image tool returned is not the exact key but a soft magenta, and how soft is a property of that picture, so
    the tolerance is read from the picture's own border: the 99th percentile of the border pixels that are plausibly background, plus a little
    headroom, never below the framework's near-key distance and never above MAX_KEY_TOLERANCE. A border that is mostly not key-coloured is
    refused: flooding it would key art."""
    values = _border(distance)
    near = sorted(v for v in values if v <= MAX_KEY_TOLERANCE)
    share = len(near) / len(values)
    if share < BORDER_MIN_SHARE:
        raise ValueError(f"Only {round(share * 100)}% of the picture's border is within {MAX_KEY_TOLERANCE} of {common.KEY_HEX} (at least "
                         f"{round(BORDER_MIN_SHARE * 100)}% is needed), so the background is not key-coloured and flooding it from the border would key art")
    percentile = near[int(PERCENTILE * (len(near) - 1))]
    tolerance = min(MAX_KEY_TOLERANCE, max(common.NEAR_KEY_TOLERANCE, percentile + TOLERANCE_HEADROOM))
    return tolerance, {"border_pixels": len(values), "border_within_cap_share": round(share, 4), "border_percentile_distance": percentile, "tolerance": tolerance}


def _fill(work, width, height, seeds):
    """Clear, in `work` (a bytearray, 1 = a pixel still to visit), every pixel 4-connected to a seed through pixels that are 1 (a diagonal gap
    does not connect); returns the filled runs as (row, first column, last column). A seed that is 0 fills nothing."""
    runs, stack = [], list(seeds)
    while stack:
        x, y = stack.pop()
        base = y * width
        if not work[base + x]:
            continue
        left = x
        while left > 0 and work[base + left - 1]:
            left -= 1
        right = x
        while right < width - 1 and work[base + right + 1]:
            right += 1
        work[base + left:base + right + 1] = bytes(right - left + 1)
        runs.append((y, left, right))
        for ny in (y - 1, y + 1):
            if 0 <= ny < height:
                row, previous = ny * width, False
                for k in range(left, right + 1):
                    here = bool(work[row + k])
                    if here and not previous:
                        stack.append((k, ny))
                    previous = here
    return runs


def _border_seeds(width, height):
    return [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)] + [(0, y) for y in range(height)] + [(width - 1, y) for y in range(height)]


def _pieces(mask, width, height):
    """[(area, runs)] for every 4-connected piece of the 1 pixels of `mask` (bytes)."""
    work, pieces, start = bytearray(mask), [], 0
    while True:
        index = work.find(1, start)
        if index < 0:
            return pieces
        start = index
        runs = _fill(work, width, height, [(index % width, index // width)])
        pieces.append((sum(right - left + 1 for _, left, right in runs), runs))


def measure_fringe(rgb, background):
    """(fringe width in pixels, rings, measurements): how many pixels of art next to the background still carry its colour.

    Where the tool blurred art into the background, the pixels just inside the keyed region are a blend of art and key, and a blend is
    magenta-tinted: min(red, blue) - green is high. The tint the art itself has is measured on its interior (further from the background than any
    fringe can reach); each ring of pixels around the background is contaminated when a share of it is tinted beyond that. The width is the number
    of contaminated rings before the first clean one; a fringe still contaminated at MAX_FRINGE is refused, because averaging it into the art
    would put the key colour into every edge. `rings[d]` is the background grown by d pixels."""
    from PIL import ImageChops, ImageFilter
    red, green, blue = rgb.split()
    tint = ImageChops.subtract(ImageChops.darker(red, blue), green)
    rings = [background]
    for _ in range(INTERIOR_DEPTH):
        rings.append(rings[-1].filter(ImageFilter.MaxFilter(3)))
    held = tint.histogram(mask=ImageChops.invert(rings[-1]))
    interior = sum(held)
    if not interior:
        raise ValueError(f"No art lies more than {INTERIOR_DEPTH} pixels from the background, so the picture's own colour cannot be told from the key's blend")
    running, baseline = 0, 0
    for value, count in enumerate(held):
        running += count
        if running >= PERCENTILE * interior:
            baseline = value
            break
    limit = min(255, baseline + TINT_HEADROOM)
    shares = []
    for ring in range(1, MAX_FRINGE + 1):
        counts = tint.histogram(mask=ImageChops.subtract(rings[ring], rings[ring - 1]))
        total = sum(counts)
        shares.append(round(sum(counts[limit + 1:]) / total, 4) if total else 0.0)
    width = next((ring for ring, share in enumerate(shares) if share < FRINGE_SHARE), None)
    if width is None:
        raise ValueError(f"The art is still magenta-tinted {MAX_FRINGE} pixels in from the background ({round(shares[-1] * 100)}% of that ring), so its "
                         "edge cannot be cleaned without keeping the key colour in it; the picture needs to be generated again on a cleaner background")
    return width, rings, {"fringe_px": width, "ring_tinted_share": shares, "interior_tint_percentile": baseline, "tint_limit": limit}


def key_background(image):
    """(background mask, fringe mask, measurements) of a picture painted on a soft key-coloured background. Changes nothing.

    The background is every pixel within the measured tolerance of the key that is connected to the border through such pixels, plus every
    enclosed key-coloured gap of at least MIN_GAP pixels: art is never within the key's distance (the near-key rule), so a gap that size is
    background that the art happens to surround, and left in it would be averaged into the art's edges as pink. Smaller key-coloured pieces are
    counted and left to the caller. Specks (pieces of what is left that are smaller than SPECK_SHARE of the largest) are background too. The fringe
    mask is 255 on the art pixels within the measured fringe width of the background; the caller keeps them out of the colour it takes for an edge."""
    from PIL import Image, ImageChops
    rgb = image.convert("RGB")
    distance = common.key_distance(rgb)
    tolerance, measured = measure_tolerance(distance)
    width, height = rgb.size
    candidates = distance.point(lambda v, t=tolerance: 1 if v <= t else 0)
    work = bytearray(candidates.tobytes())
    _fill(work, width, height, _border_seeds(width, height))
    reached = ImageChops.subtract(candidates, Image.frombytes("L", rgb.size, bytes(work)))  # 1 where a candidate was reached from the border
    if not reached.histogram()[1]:
        raise ValueError("Flooding in from the border found no background")
    flooded = reached.histogram()[1]
    gaps = [(area, runs) for area, runs in _pieces(bytes(work), width, height) if area >= MIN_GAP]
    gap_runs = [run for _, runs in gaps for run in runs]
    background = reached.point(lambda v: 255 if v else 0)
    for y, left, right in gap_runs:
        background.paste(255, (left, y, right + 1, y + 1))
    pieces = _pieces(ImageChops.invert(background).point(lambda v: 1 if v else 0).tobytes(), width, height)
    largest = max((area for area, _ in pieces), default=0)
    specks = [(area, runs) for area, runs in pieces if area < SPECK_SHARE * largest]
    for y, left, right in (run for _, runs in specks for run in runs):
        background.paste(255, (left, y, right + 1, y + 1))
    gap_pixels, speck_pixels = sum(area for area, _ in gaps), sum(area for area, _ in specks)
    fringe_px, rings, fringe = measure_fringe(rgb, background)
    measured.update(background_pixels=flooded, gap_pieces=len(gaps), gap_pixels=gap_pixels, speck_pieces=len(specks), speck_pixels=speck_pixels,
                    enclosed_key_like_pixels=candidates.histogram()[1] - flooded - gap_pixels, **fringe)
    return background, ImageChops.subtract(rings[fringe_px], background), measured


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("split")
    one.add_argument("--image", type=Path, required=True)
    one.add_argument("--output-dir", type=Path, required=True)
    one.add_argument("--name", required=True)
    two = ops.add_parser("check")
    two.add_argument("--sheet", type=Path, required=True)
    two.add_argument("--matte", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "split":
            from PIL import Image
            if not common.SLUG.fullmatch(args.name):
                raise ValueError("The name must be filename-safe")
            sheet_path, matte_path = args.output_dir / f"{args.name}.png", args.output_dir / matte_name(f"{args.name}.png")
            if sheet_path.exists() or matte_path.exists():
                raise ValueError("The output files already exist; choose a new name")
            with Image.open(args.image) as opened:
                key, matte = split(opened)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            key.save(sheet_path)
            matte.save(matte_path)
            print(json.dumps({"sheet": sheet_path.name, "matte": matte_path.name, "problems": problems(key, matte)}, indent=2))
        else:
            found = check_files(args.sheet, args.matte)
            print(json.dumps({"status": "failed" if found else "passed", "problems": found}, indent=2))
            return 1 if found else 0
        return 0
    except (OSError, ValueError) as exc:
        print("BLOCKED", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
