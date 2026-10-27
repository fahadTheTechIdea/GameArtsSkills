#!/usr/bin/env python3
"""The matte: soft-edge coverage that rides beside a delivered sheet (plan P12.4, decision D-8).

A delivered sheet keeps every unused pixel at the exact key colour #FF00FF, and a pixel is either key or art, so it cannot carry a soft edge. When the
image tool can return true alpha (checked once, plan P12.0) a soft-edged look keeps its softness in a companion `<name>.matte.png`: an 8-bit coverage
picture of the same size, 0 exactly where the sheet is the key colour and 1 to 255 wherever it is art. The key sheet stays the canonical delivery and
every check on it is unchanged; the matte is additive, recorded in the atlas with its hash, and used only by the runtime export, which turns the
coverage into real alpha. This module is the one owner of what a matte is: how true alpha is split into the pair, and when a pair is consistent.

  python scripts/gamearts_matte.py split --image RGBA.png --output-dir DIR --name NAME     # true alpha -> NAME.png (key) + NAME.matte.png
  python scripts/gamearts_matte.py check --sheet S.png --matte S.matte.png                  # is the pair consistent
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

SUFFIX = ".matte.png"
NUDGED_RED = 254  # a visible pixel whose colour is exactly the key is moved one step so artwork is never mistaken for background


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
