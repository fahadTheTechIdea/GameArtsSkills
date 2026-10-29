#!/usr/bin/env python3
"""Put one to six candidate mockups side by side, each with a letter label below it, so a person can compare looks and pick one.

  python scripts/build_contact_sheet.py --game-root GAME --mockup look-a:v001 --mockup look-b:v001 [--name candidates] [--cell-width 480] [--cell-height 320]

This is the style-exploration step: the candidates are ordinary registered mockups (made by the image tool the game's owner chose), the sheet shows
them together under letters A to F, and the person answers with a letter. The pick is then approved as a style board and set as the game's style
anchor. The sheet is a review aid: it is written under .gamearts/system/exploration/, never registered or approved, and never used as a source for
production art. Labels are drawn outside the pictures, so nothing covers the art. Pixel art that is enlarged is enlarged by whole numbers with
nearest-neighbour scaling (no invented pixels); a picture that has to shrink is averaged; other looks are scaled smoothly.
A revoked, unregistered, missing or changed (hash mismatch) mockup is refused. Beside the picture a small .json file records which letter is which mockup.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

EXPLORATION = Path(".gamearts") / "system" / "exploration"
MAX_CANDIDATES = 6
LETTERS = "ABCDEF"
COLUMNS = 3
DEFAULT_CELL = (480, 320)
GAP = 12
LABEL_HEIGHT = 44
BACKGROUND = (48, 48, 48)
TEXT = (240, 240, 240)
MUTED = (170, 170, 170)
NOTE = "Review aid only: this sheet is not game art and is never registered, approved or used as a source."


def parse_spec(text):
    """`mockup-id:revision` -> (id, revision)."""
    match = re.fullmatch(r"([^:\s]+):(v\d{3,})", text.strip())
    if not match:
        raise ValueError(f"{text!r} is not a mockup reference; write it as mockup-id:revision, for example look-a:v001")
    return match.group(1), match.group(2)


def candidates(root, specs):
    """The registered mockup records named by `specs`, in order, each with its verified image path. Refuses anything unusable."""
    if not 1 <= len(specs) <= MAX_CANDIDATES:
        raise ValueError(f"A contact sheet shows 1 to {MAX_CANDIDATES} candidates; {len(specs)} were given")
    records = common.mockup_records(root)
    found = []
    for spec in specs:
        ident, revision = parse_spec(spec)
        record = next((r for r in records if r.get("mockup_id") == ident and r.get("revision") == revision), None)
        if record is None:
            raise ValueError(f"{ident} {revision} is not a registered mockup: register it first")
        if record.get("status") == "revoked":
            raise ValueError(f"{ident} {revision} is revoked and is never shown as a candidate")
        path = (Path(root) / record.get("file", "")).resolve()
        if not common.inside(path, root) or not path.is_file():
            raise ValueError(f"{ident} {revision}: its image file is missing")
        if common.sha256_file(path) != record.get("sha256"):
            raise ValueError(f"{ident} {revision}: its image differs from the registered record (hash mismatch), so it cannot be shown")
        found.append((record, path))
    return found


def scaled(image, cell, pixel_art):
    """The picture fitted inside `cell` keeping its proportions: whole-number nearest enlargement for pixel art, averaging when shrinking,
    smooth scaling for other looks."""
    from PIL import Image
    width, height = image.size
    fit = min(cell[0] / width, cell[1] / height)
    if pixel_art and fit >= 1:
        whole = int(fit)
        return image.resize((width * whole, height * whole), Image.NEAREST)
    size = (max(1, round(width * fit)), max(1, round(height * fit)))
    if fit >= 1:
        return image.resize(size, Image.LANCZOS)
    return image.resize(size, Image.BOX if pixel_art else Image.LANCZOS)


def label_picture(letter, record):
    """The two label lines as a small picture, enlarged by whole numbers so the built-in font stays readable at any Pillow version."""
    from PIL import Image, ImageDraw
    small = Image.new("RGB", (240, 20), BACKGROUND)
    draw = ImageDraw.Draw(small)
    draw.text((0, 0), f"{letter}  {record['mockup_id']} {record['revision']}", fill=TEXT)
    draw.text((0, 10), f"{record.get('scope', '')} - {record.get('status', '')}", fill=MUTED)
    return small.resize((small.width * 2, small.height * 2), Image.NEAREST)


def build(game_root, specs, name="candidates", cell=DEFAULT_CELL, scaling=None):
    """Write the contact sheet and its letter map; returns {"sheet", "map", "candidates", "scaling", "note"}."""
    from PIL import Image
    root = common.game_root(game_root)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("The sheet name may contain only letters, digits, - and _")
    if cell[0] < 64 or cell[1] < 64:
        raise ValueError("Each picture area must be at least 64 x 64 pixels")
    chosen = candidates(root, specs)
    note = None
    if scaling is None:
        try:
            settings, _, _ = common.load_project_settings(root, require_confirmed=False)
            pixel_art = settings["art_style"]["id"] == "pixel_art"
        except ValueError as exc:  # the sheet is still useful without settings; say which scaling was used and why
            pixel_art, note = False, f"The game's settings could not be read, so smooth scaling was used: {exc}"
    else:
        pixel_art = scaling == "nearest"
    columns = min(COLUMNS, len(chosen))
    rows = -(-len(chosen) // columns)
    block_w, block_h = cell[0], cell[1] + LABEL_HEIGHT
    sheet = Image.new("RGB", (columns * block_w + (columns + 1) * GAP, rows * block_h + (rows + 1) * GAP), BACKGROUND)
    described = []
    for index, (record, path) in enumerate(chosen):
        left, top = GAP + (index % columns) * (block_w + GAP), GAP + (index // columns) * (block_h + GAP)
        with Image.open(path) as opened:
            shown = scaled(opened.convert("RGB"), cell, pixel_art)
        sheet.paste(shown, (left + (cell[0] - shown.width) // 2, top + (cell[1] - shown.height) // 2))
        sheet.paste(label_picture(LETTERS[index], record), (left, top + cell[1] + 2))
        described.append({"letter": LETTERS[index], "mockup_id": record["mockup_id"], "revision": record["revision"],
                          "scope": record.get("scope"), "status": record.get("status"), "sha256": record["sha256"]})
    folder = root / EXPLORATION
    folder.mkdir(parents=True, exist_ok=True)
    picture, letters = folder / f"{name}.png", folder / f"{name}.json"
    handle = picture.with_name(picture.name + ".tmp")
    sheet.save(handle, format="PNG")
    common.replace_file(handle, picture)
    result = {"sheet": picture.relative_to(root).as_posix(), "map": letters.relative_to(root).as_posix(), "candidates": described,
              "scaling": "nearest (whole numbers) / averaged when shrinking" if pixel_art else "smooth", "note": NOTE}
    if note:
        result["warning"] = note
    common.atomic_write_json(letters, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--mockup", action="append", required=True, metavar="ID:REVISION", help="A registered mockup; give 1 to %d" % MAX_CANDIDATES)
    parser.add_argument("--name", default="candidates", help="File name for the sheet (replaced when it exists)")
    parser.add_argument("--cell-width", type=int, default=DEFAULT_CELL[0])
    parser.add_argument("--cell-height", type=int, default=DEFAULT_CELL[1])
    parser.add_argument("--scaling", choices=("nearest", "smooth"), help="Overrides the game's art style")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.game_root, args.mockup, args.name, (args.cell_width, args.cell_height), args.scaling), indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
