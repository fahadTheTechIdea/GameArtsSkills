#!/usr/bin/env python3
"""Review previews of a delivered sheet: each animation as a strip PNG and a looping GIF, with the key colour shown as a checkerboard.

  python scripts/render_preview.py --image SHEET.png --atlas SHEET.atlas.json --output-dir DIR [--game-root GAME] [--scaling nearest|smooth]
                                   [--scale N] [--show-key] [--action A] [--direction D]

A preview is a review aid for people: it shows how an animation reads and how long it takes, so a bad loop or a wobbling pivot is seen before it is
approved. It is never game art and is never registered, approved or shipped. Pixel art is enlarged by whole numbers with nearest-neighbour scaling
(no invented pixels); other looks are enlarged smoothly. The GIF format stores timing in hundredths of a second and browsers slow frames shorter than
20 ms, so the report says when a frame's time was changed. Existing previews are replaced, since they are derived from the sheet.
This module also owns the checkerboard drawing the offline report uses for its sheet pictures.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_animation as animation  # noqa: E402
import gamearts_common as common  # noqa: E402

TARGET_HEIGHT = 192  # pixels: the automatic scale makes the largest cell about this tall, up to MAX_AUTO_SCALE
MAX_AUTO_SCALE = 8
MAX_PICTURE_PIXELS = 16_000_000  # a preview larger than this is refused rather than allowed to exhaust memory
STRIP_WIDTH = 2048  # frames wrap onto a new row beyond this width
GAP = 6
MIN_GIF_MS = 20
BACKGROUND = (60, 60, 60)


# ------------------------------------------------------------------------------------------------ drawing
def checkerboard(size, tile=8):
    """A light/dark grey checkerboard, built from row strips so a large sheet costs a few hundred pastes."""
    from PIL import Image
    width, height = size
    light, dark = (205, 205, 205), (170, 170, 170)
    strips = []
    for first, second in ((light, dark), (dark, light)):
        cell = Image.new("RGB", (tile * 2, tile * 2))
        cell.paste(first, (0, 0, tile, tile))
        cell.paste(second, (tile, 0, tile * 2, tile))
        cell.paste(second, (0, tile, tile, tile * 2))
        cell.paste(first, (tile, tile, tile * 2, tile * 2))
        strips.append(cell)
    board = Image.new("RGB", (width, height))
    for y in range(0, height, tile * 2):
        for x in range(0, width, tile * 2):
            board.paste(strips[0], (x, y))
    return board


def show_key_as_checkerboard(image):
    """The picture with every key-colour pixel replaced by a checkerboard, so empty space reads as empty."""
    from PIL import Image
    rgba = image.convert("RGBA")
    return Image.composite(rgba.convert("RGB"), checkerboard(rgba.size), common.nonkey_mask(rgba))


def enlarge(image, scale, pixel_art):
    """Whole-number enlargement; nearest-neighbour for pixel art (no invented pixels), smooth for every other look."""
    from PIL import Image
    if scale == 1:
        return image
    return image.resize((image.width * scale, image.height * scale), Image.NEAREST if pixel_art else Image.LANCZOS)


def automatic_scale(frames):
    tallest = max(max(frame["cell"].size) for frame in frames)
    return max(1, min(MAX_AUTO_SCALE, TARGET_HEIGHT // tallest))


def strip_picture(pictures):
    """The frames side by side on a dark ground with a small gap, wrapped onto rows beyond STRIP_WIDTH."""
    from PIL import Image
    cell_w, cell_h = max(p.width for p in pictures), max(p.height for p in pictures)
    per_row = max(1, (STRIP_WIDTH + GAP) // (cell_w + GAP))
    rows = -(-len(pictures) // per_row)
    columns = min(per_row, len(pictures))
    sheet = Image.new("RGB", (columns * cell_w + (columns + 1) * GAP, rows * cell_h + (rows + 1) * GAP), BACKGROUND)
    for index, picture in enumerate(pictures):
        sheet.paste(picture, (GAP + (index % per_row) * (cell_w + GAP), GAP + (index // per_row) * (cell_h + GAP)))
    return sheet


def gif_timing(frames):
    """(durations in ms for the GIF, the names of frames whose time had to change). GIF keeps hundredths of a second and browsers slow
    frames shorter than MIN_GIF_MS."""
    durations, changed = [], []
    for frame in frames:
        wanted = frame["duration_ms"]
        shown = max(MIN_GIF_MS, int(round(wanted / 10.0)) * 10)
        durations.append(shown)
        if shown != wanted:
            changed.append(frame["name"])
    return durations, changed


def write_gif(path, pictures, durations):
    from PIL import Image
    quantized = [p.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for p in pictures]
    handle = path.with_name(path.name + ".tmp")
    quantized[0].save(handle, format="GIF", save_all=True, append_images=quantized[1:], duration=durations, loop=0, disposal=2)
    common.replace_file(handle, path)


def write_png(path, picture):
    handle = path.with_name(path.name + ".tmp")
    picture.save(handle, format="PNG")
    common.replace_file(handle, path)


# ------------------------------------------------------------------------------------------------ one sheet
def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_") or "none"


def render(image_path, atlas_path, output_dir, pixel_art=True, scale=None, show_key=False, action=None, direction=None, stem=None, min_frames=1):
    """Write a strip PNG and a GIF for every animation of one sheet (or the one named); returns one summary per animation.
    Files are named `<stem>.<action>.<direction>`; the stem is the sheet's file name unless a caller (the report) gives its own.
    Animations with fewer than `min_frames` frames are left out (a single frame has nothing to play)."""
    from PIL import Image
    atlas = common.read_json(atlas_path)
    common.validate_schema(atlas, "gamearts-atlas")
    with Image.open(image_path) as opened:
        image = opened.convert("RGBA")
    groups = [g for g in animation.animation_groups(image, atlas)
              if (action is None or g[0] == action) and (direction is None or g[1] == direction)]
    if not groups:
        raise ValueError("No animation on this sheet matches" + (f" action {action!r}" if action else "") + (f" direction {direction!r}" if direction else ""))
    groups = [g for g in groups if len(g[2]) >= min_frames]
    output_dir = Path(output_dir)
    if groups:
        output_dir.mkdir(parents=True, exist_ok=True)
    stem = _slug(stem or Path(image_path).stem)
    summaries = []
    for group_action, group_direction, frames in groups:
        chosen = scale if scale is not None else automatic_scale(frames)
        if chosen < 1:
            raise ValueError("The scale must be a whole number of at least 1")
        cell_w, cell_h = max(f["cell"].width for f in frames) * chosen, max(f["cell"].height for f in frames) * chosen
        if cell_w * cell_h * len(frames) > MAX_PICTURE_PIXELS:
            raise ValueError(f"The preview of {group_action or 'the frames'} would be {cell_w * cell_h * len(frames):,} pixels; lower --scale (the limit is {MAX_PICTURE_PIXELS:,})")
        pictures = [enlarge(f["cell"].convert("RGB") if show_key else show_key_as_checkerboard(f["cell"]), chosen, pixel_art) for f in frames]
        durations, changed = gif_timing(frames)
        name = f"{stem}.{_slug(group_action)}.{_slug(group_direction)}"
        strip, gif = output_dir / f"{name}.strip.png", output_dir / f"{name}.gif"
        write_png(strip, strip_picture(pictures))
        write_gif(gif, pictures, durations)
        summaries.append({"action": group_action, "direction": group_direction, "frames": len(frames), "scale": chosen,
                          "duration_ms": sum(f["duration_ms"] for f in frames), "strip": strip.name, "gif": gif.name,
                          "gif_timing_changed": changed, "scaling": "nearest" if pixel_art else "smooth",
                          "key_colour": "shown as magenta" if show_key else "shown as a checkerboard"})
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, help="Pick nearest or smooth scaling from the game's art style")
    parser.add_argument("--scaling", choices=("nearest", "smooth"), help="Overrides the game's style; with neither, nearest (no invented pixels)")
    parser.add_argument("--scale", type=int, help="Whole-number enlargement; by default the largest frame is made about %d px tall" % TARGET_HEIGHT)
    parser.add_argument("--show-key", action="store_true", help="Show the key colour as it is instead of as a checkerboard")
    parser.add_argument("--action")
    parser.add_argument("--direction")
    args = parser.parse_args()
    try:
        if args.scaling:
            pixel_art = args.scaling == "nearest"
        elif args.game_root:
            settings, _, _ = common.load_project_settings(args.game_root, require_confirmed=False)
            pixel_art = settings["art_style"]["id"] == "pixel_art"
        else:
            pixel_art = True
        summaries = render(args.image, args.atlas, args.output_dir, pixel_art, args.scale, args.show_key, args.action, args.direction)
        print(json.dumps({"previews": summaries, "note": "Review aids only: not game art, never registered or approved."}, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
