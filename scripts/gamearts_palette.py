#!/usr/bin/env python3
"""Single owner of palettes: extract one from an approved picture, load the one a project points at, and compare colours.

  python scripts/gamearts_palette.py extract --game-root GAME --image PICTURE --name NAME [--max-colours 32]
  python scripts/gamearts_palette.py recolour --game-root GAME (--image IN --output OUT | --folder DIR --output-folder DIR)
         (--map MAP.json | --from-palette A.palette.json --to-palette B.palette.json) [--snap] [--allow-merge]

Extraction is deterministic and does not depend on the Pillow version: a picture with no more colours than allowed yields exactly its
colours; a larger one is reduced by a weighted median cut over 5-bit colour buckets. The exact key colour and transparent pixels are
never part of a palette. The palette is saved as project data under .gamearts/palette/ (a .palette.json and a GIMP .gpl) and is
named in `art_style.palette_reference`, which the style-conformance checks and the pixel-grid snapper read.

`recolour` makes a palette variant (a team colour, a season, night) of approved pictures by a fixed colour-for-colour map, never by an
ad hoc filter: every colour of the picture must be in the map (or be snapped to the nearest listed one, and the distance is recorded),
the key colour and transparent pixels are never touched, alpha is kept, two colours are not merged unless asked, and no target may
sit near the key colour. Inputs are never changed and outputs never overwrite. A variant is new art: it is built into a sheet and goes
through the same registration and approval as any other asset; the record it writes ties it to the pictures it came from.
"""
import argparse
import io
import json
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

PALETTE_DIR = Path(".gamearts") / "palette"
SUFFIX = ".palette.json"
RECOLOUR_RECORD = "recolour.record.json"
MASK_LIMIT = 64  # most colours recoloured by mask; beyond this one pass over the pixels is cheaper
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
    """The palette colour closest to `colour` by perceived distance; the first one wins a tie. The squared distance orders colours exactly as the
    distance does, and the colour's own L*a*b* is taken once, so a large palette against a painted picture's many colours stays fast."""
    l, a, b = rgb_to_lab(tuple(colour))
    return min(colours, key=lambda candidate: (lambda lab: (lab[0] - l) ** 2 + (lab[1] - a) ** 2 + (lab[2] - b) ** 2)(rgb_to_lab(tuple(candidate))))


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


def ensure(image_path, name, output_dir, max_colours=32, root=None):
    """`extract`, for a caller that can run more than once on the same answer (the settings are written when the last question is answered and again
    when the owner confirms them). A palette this very picture already produced, with the same limit, is returned untouched; any other existing
    palette is still refused, so a palette is never overwritten."""
    json_path, gpl_path = Path(output_dir) / f"{name}{SUFFIX}", Path(output_dir) / f"{name}.gpl"
    if json_path.is_file() and gpl_path.is_file():
        held = common.read_json(json_path)
        common.validate_schema(held, "gamearts-palette")
        if held["name"] == name and held["max_colours"] == max_colours and held["source"]["sha256"] == common.sha256_file(image_path):
            return held
    return extract(image_path, name, output_dir, max_colours, root)


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


# ------------------------------------------------------------------------------------------------ variants
def _rgb(text):
    return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))


def load_colour_map(path):
    """{source (r, g, b): target (r, g, b)} from a recolour map file; a file that breaks its contract, or lists one colour twice, is refused."""
    data = common.read_json(path)
    common.validate_schema(data, "gamearts-recolour-map")
    mapping = {_rgb(source): _rgb(target) for source, target in data["colours"].items()}
    if len(mapping) != len(data["colours"]):
        raise ValueError("The recolour map lists the same source colour twice (letters may differ in case)")
    return mapping


def pair_palettes(from_path, to_path):
    """Map the colours of one saved palette to the colours of another by position; the two must hold the same number of colours."""
    source, target = load_palette(from_path), load_palette(to_path)
    if len(source) != len(target):
        raise ValueError(f"The palettes must hold the same number of colours to be paired by position ({len(source)} against {len(target)})")
    if len(set(source)) != len(source):
        raise ValueError("The source palette lists a colour twice, so its position pairing is ambiguous")
    return dict(zip(source, target))


def _check_mapping(mapping, allow_merge):
    """Refuse a target at or near the key colour, and (unless allowed) two sources sharing a target; returns the merges, if any."""
    for source, target in mapping.items():
        if max(abs(target[i] - common.KEY_RGB[i]) for i in range(3)) <= common.NEAR_KEY_TOLERANCE:
            raise ValueError(f"{hex_of(source)} would become {hex_of(target)}, which is the key colour or too close to it; choose another target")
    grouped = {}
    for source, target in mapping.items():
        grouped.setdefault(target, []).append(source)
    merged = [{"target": hex_of(target), "sources": sorted(hex_of(s) for s in sources)} for target, sources in sorted(grouped.items()) if len(sources) > 1]
    if merged and not allow_merge:
        first = merged[0]
        raise ValueError(f"{', '.join(first['sources'])} would all become {first['target']} and lose the detail between them "
                         f"({len(merged)} such target(s)); give each its own target, or allow the merge on purpose")
    return merged


def _resolve(counts, mapping, snap, label):
    """The colour-for-colour table for one picture, and the stray colours that had to be snapped (colour, nearest listed colour, distance)."""
    missing = sorted(colour for colour in counts if colour not in mapping)
    if not missing:
        return dict(mapping), []
    if not snap:
        shown = ", ".join(hex_of(c) for c in missing[:8]) + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")
        raise ValueError(f"{label} has {len(missing)} colour(s) the map does not list: {shown}. List them, or snap strays to the nearest listed colour on purpose")
    sources = sorted(mapping)
    table, snapped = dict(mapping), []
    for colour in missing:
        near = nearest(colour, sources)
        table[colour] = mapping[near]
        snapped.append((colour, near, lab_distance(colour, near)))
    return table, snapped


def recolour_image(image, table):
    """A recoloured copy of `image` and the number of pixels changed. The key colour and transparent pixels stay as they are; alpha is kept.
    A colour the table does not list is left as it is (`recolour` has already refused or snapped every such colour). Few colours change in pixel
    art, so each is found with a mask in one pass over the image; many colours (a snapped painted picture) go through a single pixel loop."""
    from PIL import Image, ImageChops
    rgba = image.convert("RGBA")
    changes = {source: target for source, target in table.items() if source != target and source != common.KEY_RGB}
    if len(changes) > MASK_LIMIT:
        return _recolour_pixels(rgba, table)
    red, green, blue, alpha = rgba.split()
    visible = alpha.point(lambda value: 255 if value else 0)
    channels, changed = [red.copy(), green.copy(), blue.copy()], 0
    for source, target in changes.items():
        mask = visible
        for original, wanted in zip((red, green, blue), source):
            mask = ImageChops.multiply(mask, original.point(lambda value, wanted=wanted: 255 if value == wanted else 0))  # always from the original, so a swap cannot chain
        count = mask.histogram()[255]
        changed += count
        if count:
            for channel, value in zip(channels, target):
                channel.paste(value, mask=mask)
    return Image.merge("RGBA", (*channels, alpha)), changed


def _recolour_pixels(rgba, table):
    """The one-pass-per-pixel form of `recolour_image`: slow on a large sheet, but its cost does not grow with the number of colours."""
    from PIL import Image
    key, changed, out = common.KEY_RGB, 0, bytearray()
    data = rgba.tobytes()  # tobytes and frombytes behave the same on every Pillow version this framework supports; getdata does not
    for offset in range(0, len(data), 4):
        pixel = data[offset:offset + 4]
        rgb = (pixel[0], pixel[1], pixel[2])
        if pixel[3] == 0 or rgb == key:
            out += pixel
            continue
        target = table.get(rgb, rgb)
        changed += target != rgb
        out += bytes((*target, pixel[3]))
    return Image.frombytes("RGBA", rgba.size, bytes(out)), changed


def recolour(game_root, mapping, sources, output, folder=False, snap=False, allow_merge=False):
    """Recolour one picture (`sources` = [path], `output` = the new file) or every PNG under a folder (`output` = a new folder).
    Everything is checked before anything is written, outputs never overwrite, and a failure part-way removes what was written."""
    from PIL import Image
    root = common.game_root(game_root)
    output = Path(output)
    if not mapping:
        raise ValueError("The recolour map is empty")
    merged = _check_mapping(mapping, allow_merge)
    base = Path(sources[0]).resolve()
    if folder:
        if not base.is_dir():
            raise ValueError(f"{base.name} is not a folder")
        pairs = [(path, output / path.relative_to(base)) for path in sorted(base.rglob("*.png"))]
        if not pairs:
            raise ValueError(f"{base.name} holds no PNG pictures")
        if output.exists() and any(output.iterdir()):
            raise ValueError(f"{output.name} already holds files; a recolour never overwrites, so choose a new folder")
        record_path = output / RECOLOUR_RECORD
    else:
        pairs = [(base, output)]
        if output.exists():
            raise ValueError(f"{output.name} already exists; a recolour never overwrites, so choose a new name")
        record_path = output.with_name(output.name + ".recolour.json")
    for _, target in pairs:
        if not common.inside(target.resolve(), root):
            raise ValueError(f"{target.name} would be written outside the game folder")
    plans = []
    for source, target in pairs:
        with Image.open(source) as opened:
            image = opened.convert("RGBA")
        table, snapped = _resolve(art_colour_counts(image), mapping, snap, source.name)
        plans.append((source, target, image, table, snapped))
    written, files, strays = [], [], {}
    try:
        for source, target, image, table, snapped in plans:
            result, changed = recolour_image(image, table)
            buffer = io.BytesIO()
            result.save(buffer, format="PNG")
            data = buffer.getvalue()
            common.atomic_write_bytes(target, data)
            written.append(target)
            files.append({"source": source.relative_to(base).as_posix() if folder else source.name, "source_sha256": common.sha256_file(source),
                          "output": target.relative_to(output).as_posix() if folder else target.name,
                          "output_sha256": common.sha256_bytes(data), "pixels_changed": changed})
            for colour, near, distance in snapped:
                strays[colour] = (near, distance)
        record = {"schema_version": "1.0", "mapping": {hex_of(s): hex_of(t) for s, t in sorted(mapping.items())}, "snap": bool(snap), "files": files,
                  "merged": merged, "snapped": [{"colour": hex_of(c), "treated_as": hex_of(n), "distance": round(d, 3)} for c, (n, d) in sorted(strays.items())],
                  "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        common.validate_schema(record, "gamearts-recolour-record")
        common.atomic_write_json(record_path, record)
    except Exception:
        # A half-written variant would look like finished art; take back what this run wrote, then let the failure reach the caller.
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("extract")
    item.add_argument("--game-root", type=Path, required=True)
    item.add_argument("--image", type=Path, required=True, help="Normally the approved style board or another approved mockup")
    item.add_argument("--name", required=True)
    item.add_argument("--max-colours", type=int, default=32)
    swap = sub.add_parser("recolour", help="make a palette variant of approved pictures by a fixed colour map")
    swap.add_argument("--game-root", type=Path, required=True)
    one = swap.add_mutually_exclusive_group(required=True)
    one.add_argument("--image", type=Path)
    one.add_argument("--folder", type=Path, help="recolour every PNG under this folder")
    swap.add_argument("--output", type=Path, help="the new picture (with --image)")
    swap.add_argument("--output-folder", type=Path, help="the new folder (with --folder)")
    how = swap.add_mutually_exclusive_group(required=True)
    how.add_argument("--map", type=Path, help="a recolour map file")
    how.add_argument("--from-palette", type=Path, help="pair this palette's colours, by position, with --to-palette's")
    swap.add_argument("--to-palette", type=Path)
    swap.add_argument("--snap", action="store_true", help="treat a colour the map does not list as its nearest listed colour (recorded)")
    swap.add_argument("--allow-merge", action="store_true", help="allow two source colours to share a target")
    args = parser.parse_args()
    try:
        if args.command == "recolour":
            if bool(args.image) != bool(args.output) or bool(args.folder) != bool(args.output_folder):
                raise ValueError("--image goes with --output, and --folder with --output-folder")
            if bool(args.from_palette) != bool(args.to_palette):
                raise ValueError("--from-palette and --to-palette go together")
            mapping = load_colour_map(args.map) if args.map else pair_palettes(args.from_palette, args.to_palette)
            record = recolour(args.game_root, mapping, [args.image or args.folder], args.output or args.output_folder, folder=bool(args.folder),
                              snap=args.snap, allow_merge=args.allow_merge)
            print(json.dumps({"files": len(record["files"]), "pixels_changed": sum(f["pixels_changed"] for f in record["files"]),
                              "merged": len(record["merged"]), "snapped": len(record["snapped"]),
                              "next_step": "A variant is new art: build its sheet from these pictures, register it as its own asset with the same approved mockup, "
                                           "and show it for review like any other asset."}, indent=2))
            return 0
        root = common.game_root(args.game_root)
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
