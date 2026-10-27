#!/usr/bin/env python3
"""Single owner of palettes: extract one from an approved picture, load the one a project points at, and compare colours.

  python scripts/gamearts_palette.py extract --game-root GAME --image PICTURE --name NAME [--max-colours 32]

Extraction is deterministic and does not depend on the Pillow version: a picture with no more colours than allowed yields exactly its
colours; a larger one is reduced by a weighted median cut over 5-bit colour buckets. The exact key colour and transparent pixels are
never part of a palette. The palette is saved as project data under .gamearts/palette/ (a .palette.json and a GIMP .gpl) and is
named in `art_style.palette_reference`, which the style-conformance checks and the pixel-grid snapper read.
"""
import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

PALETTE_DIR = Path(".gamearts") / "palette"
SUFFIX = ".palette.json"
BUCKET_SHIFT = 3  # 5 bits per channel: at most 32768 points for the median cut, whatever the picture


def hex_of(rgb):
    return "#%02X%02X%02X" % tuple(rgb)


# ------------------------------------------------------------------------------------------------ colour maths
def _linear(channel):
    value = channel / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


@lru_cache(maxsize=None)
def rgb_to_lab(rgb):
    """CIE L*a*b* (D65) of an sRGB colour, rounded to six places so equal colours compare equal."""
    r, g, b = (_linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (round(116 * fy - 16, 6), round(500 * (fx - fy), 6), round(200 * (fy - fz), 6))


def lab_distance(first, second):
    """CIE76 colour difference: the straight distance in L*a*b*. About 2.3 is the smallest difference an eye can see."""
    a, b = rgb_to_lab(tuple(first)), rgb_to_lab(tuple(second))
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


def nearest(colour, colours):
    """The palette colour closest to `colour` by perceived distance; the first one wins a tie."""
    return min(colours, key=lambda candidate: lab_distance(colour, candidate))


# ------------------------------------------------------------------------------------------------ extraction
def art_colour_counts(image):
    """{(r, g, b): pixels} for the artwork only: the exact key colour and transparent pixels are left out."""
    from PIL import Image, ImageChops
    rgba = image.convert("RGBA")
    visible = rgba.getchannel("A").point(lambda v: 255 if v else 0)
    art = ImageChops.multiply(common.nonkey_mask(rgba), visible)
    masked = Image.new("RGB", rgba.size, common.KEY_RGB)
    masked.paste(rgba.convert("RGB"), mask=art)
    counts = {colour: count for count, colour in masked.getcolors(rgba.width * rgba.height)}
    counts.pop(common.KEY_RGB, None)
    return counts


def _median_cut(counts, limit):
    """Reduce `counts` to at most `limit` colours: bucket to 5 bits per channel, then weighted median cut. Deterministic."""
    buckets = {}
    for (r, g, b), n in counts.items():
        key = (r >> BUCKET_SHIFT, g >> BUCKET_SHIFT, b >> BUCKET_SHIFT)
        total = buckets.setdefault(key, [0, 0, 0, 0])
        total[0] += n
        total[1] += r * n
        total[2] += g * n
        total[3] += b * n
    points = [(t[1] / t[0], t[2] / t[0], t[3] / t[0], t[0]) for _, t in sorted(buckets.items())]
    boxes = [points]

    def spread(box):
        return max(max(p[i] for p in box) - min(p[i] for p in box) for i in range(3))
    while len(boxes) < limit:
        splittable = [(spread(box), sum(p[3] for p in box), -index) for index, box in enumerate(boxes) if len(box) > 1]
        if not splittable:
            break
        index = -max(splittable)[2]
        box = boxes.pop(index)
        ranges = [max(p[i] for p in box) - min(p[i] for p in box) for i in range(3)]
        channel = ranges.index(max(ranges))
        box.sort(key=lambda p: (p[channel], p[0], p[1], p[2]))
        half, running, cut = sum(p[3] for p in box) / 2, 0, 1
        for position, point in enumerate(box):
            running += point[3]
            if running >= half:
                cut = min(max(position + 1, 1), len(box) - 1)
                break
        boxes[index:index] = [box[:cut], box[cut:]]
    result = {}
    for box in boxes:
        weight = sum(p[3] for p in box)
        rgb = tuple(int(sum(p[i] * p[3] for p in box) / weight + 0.5) for i in range(3))
        result[rgb] = result.get(rgb, 0) + weight
    return result


def extract(image_path, name, output_dir, max_colours=32, root=None):
    """Write <name>.palette.json and <name>.gpl into `output_dir`; returns the palette record. Never overwrites an existing palette."""
    from PIL import Image
    if not common.SLUG.fullmatch(name or ""):
        raise ValueError("A palette name may use letters, digits, hyphens and underscores only")
    if not isinstance(max_colours, int) or max_colours < 1:
        raise ValueError("A palette needs room for at least 1 colour")
    image_path, output_dir = Path(image_path), Path(output_dir)
    json_path, gpl_path = output_dir / f"{name}{SUFFIX}", output_dir / f"{name}.gpl"
    if json_path.exists() or gpl_path.exists():
        raise ValueError(f"A palette named {name!r} already exists; choose another name (a palette is never overwritten)")
    with Image.open(image_path) as opened:
        counts = art_colour_counts(opened)
    if not counts:
        raise ValueError(f"{image_path.name} has no artwork pixels (everything is the key colour or transparent), so there is no palette to take")
    if len(counts) <= max_colours:
        method, chosen = "exact", counts
    else:
        method, chosen = "median_cut", _median_cut(counts, max_colours)
    total = sum(chosen.values())
    ordered = sorted(chosen.items(), key=lambda item: (-item[1], hex_of(item[0])))
    shown = image_path.resolve().relative_to(Path(root).resolve()).as_posix() if root and common.inside(image_path, root) else image_path.name
    record = {"schema_version": "1.0", "name": name, "method": method, "max_colours": max_colours,
              "colours": [{"hex": hex_of(rgb), "share": round(n / total, 6)} for rgb, n in ordered],
              "source": {"file": shown, "sha256": common.sha256_file(image_path)}}
    common.validate_schema(record, "gamearts-palette")
    gimp = ["GIMP Palette", f"Name: {name}", "Columns: 8", "#"] + [f"{r:3d} {g:3d} {b:3d}  {hex_of((r, g, b))}" for (r, g, b), _ in ordered]
    common.atomic_write_json(json_path, record)
    common.atomic_write_bytes(gpl_path, ("\n".join(gimp) + "\n").encode("utf-8"))
    return record


# ------------------------------------------------------------------------------------------------ use
def load_palette(path):
    """The colours of a saved palette as (r, g, b) tuples, in the file's order; a file that breaks its contract is refused."""
    data = common.read_json(path)
    common.validate_schema(data, "gamearts-palette")
    return [tuple(int(item["hex"][i:i + 2], 16) for i in (1, 3, 5)) for item in data["colours"]]


def project_palette(root, settings):
    """The palette a project points at through `art_style.palette_reference`, or None when it holds plain words (or nothing).
    A file reference must stay inside the game and exist."""
    reference = settings["art_style"].get("palette_reference")
    if not reference or not reference.endswith(SUFFIX):
        return None
    path = (Path(root) / reference).resolve()
    if not common.inside(path, root):
        raise ValueError(f"palette_reference {reference!r} must stay inside the game folder")
    if not path.is_file():
        raise ValueError(f"palette_reference {reference!r} names a palette file that does not exist")
    return load_palette(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("extract")
    item.add_argument("--game-root", type=Path, required=True)
    item.add_argument("--image", type=Path, required=True, help="Normally the approved style board or another approved mockup")
    item.add_argument("--name", required=True)
    item.add_argument("--max-colours", type=int, default=32)
    args = parser.parse_args()
    try:
        root = args.game_root.resolve()
        record = extract(args.image, args.name, root / PALETTE_DIR, args.max_colours, root)
        reference = (PALETTE_DIR / f"{args.name}{SUFFIX}").as_posix()
        print(json.dumps({"palette_reference": reference, "method": record["method"], "colours": len(record["colours"]),
                          "files": [reference, (PALETTE_DIR / f"{args.name}.gpl").as_posix()],
                          "next_step": f"Set art_style.palette_reference to {reference} (a palette is part of the look, so the owner confirms the change)."},
                         indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
