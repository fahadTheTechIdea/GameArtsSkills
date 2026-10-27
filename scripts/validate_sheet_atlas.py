#!/usr/bin/env python3
"""Pixel-level sheet/atlas contract check: geometry, exact #FF00FF outside the frames, no near-key contamination.

Usage: validate_sheet_atlas.py image.png atlas.json [--tolerance N]
It proves the mechanical contract only; visual correctness and engine behavior are separate gates.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

import gamearts_atlas as atlas_rules  # noqa: E402
import gamearts_common as common  # noqa: E402


def validate(image_path, atlas_path, tolerance=common.NEAR_KEY_TOLERANCE):
    """Return a list of contract violations for one sheet and its atlas (empty means the contract holds)."""
    image_path, atlas_path = Path(image_path), Path(atlas_path)
    issues = []
    try:
        atlas = common.read_json(atlas_path)
        common.validate_schema(atlas, "gamearts-atlas")
    except ValueError as exc:  # unreadable JSON, schema violation or a missing validator all block the check
        return [f"atlas contract: {exc}"]
    if not image_path.is_file():
        return [f"sheet image is missing: {image_path}"]
    with Image.open(image_path) as source:
        if source.format != "PNG":
            issues.append(f"sheet is {source.format}, not PNG")
        sheet = source.convert("RGBA")
    if Path(atlas["image"]).name != image_path.name:
        issues.append(f"atlas names image {atlas['image']!r} but the checked file is {image_path.name!r}")
    if tuple(atlas["image_size"]) != sheet.size:
        issues.append(f"atlas image_size {atlas['image_size']} != actual {list(sheet.size)}")
    rects = []
    for i, frame in enumerate(atlas["frames"]):
        x, y, w, h = frame["rect"]
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > sheet.width or y + h > sheet.height:
            issues.append(f"frame {i}: rectangle {frame['rect']} is out of bounds")
            continue
        px, py = frame["pivot"]
        if not (0 <= px <= w and 0 <= py <= h):
            issues.append(f"frame {i}: pivot {frame['pivot']} lies outside its cell {w}x{h}")
        rects.append((x, y, w, h))
    for i, a in enumerate(rects):
        for j in range(i + 1, len(rects)):
            b = rects[j]
            if a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]:
                issues.append(f"frames {i} and {j} overlap")
    issues += [f"ui: {problem}" for problem in atlas_rules.ui_problems(atlas)]
    issues += [f"tags: {problem}" for problem in atlas_rules.tag_problems(atlas.get("tags", []), len(atlas["frames"]))]
    report = common.key_policy_report(sheet, rects, tolerance, bool(atlas.get("allow_near_key")), bool(atlas.get("full_bleed")))
    issues += report["issues"]
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("atlas")
    parser.add_argument("--tolerance", type=int, default=common.NEAR_KEY_TOLERANCE,
                        help="largest per-channel distance from #FF00FF treated as key contamination")
    args = parser.parse_args(argv)
    try:
        issues = validate(args.image, args.atlas, args.tolerance)
    except (OSError, ValueError) as exc:
        print("FAIL", exc)
        return 1
    if issues:
        for issue in issues:
            print("FAIL", issue)
        return 1
    print("PASS geometry, exact-key and contamination checks. Visual correctness and engine behavior NOT assessed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
