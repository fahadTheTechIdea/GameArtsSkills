#!/usr/bin/env python3
"""Build an exact-key PNG sprite sheet AND its measured JSON atlas.

Usage (normally invoked automatically by Claude/Codex):
  python scripts/build_sheet_atlas.py path/to/frames.json --output-dir path/to/generated

Input contract: schemas/gamearts-frames-job.schema.json (see docs/ATLAS_GENERATION.md). Requires Pillow and jsonschema.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

import gamearts_atlas as atlas_rules  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_matte as matte_rules  # noqa: E402
import validate_settings_fit as settings_fit  # noqa: E402

DEFAULT_MAX_WIDTH = 2048
MAX_SHEET_SIDE = 16384  # the largest side of a sheet: the common graphics-card texture limit, and the schema's own ceiling for max_width


def check_sheet_size(width, height):
    """Refuse a sheet no engine could load as one texture (and that picture libraries treat as a decompression bomb) before a pixel of it is made."""
    if width > MAX_SHEET_SIDE or height > MAX_SHEET_SIDE:
        raise ValueError(f"the sheet would be {width} x {height} px, past the {MAX_SHEET_SIDE} px limit on a side; use fewer or smaller frames, less padding or spacing, "
                         "pack 'shelf' with 'trim', or split the animation across several sheets")


def integer_pair(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(x) is not int for x in value):
        raise ValueError(f"{name}: expected two integer coordinates")
    return list(value)


def ink_bounds(image):
    """[x, y, width, height] of all non-key pixels, or None when the frame is entirely key colour."""
    box = common.ink_bbox(image)
    return None if box is None else [box[0], box[1], box[2] - box[0], box[3] - box[1]]


def load_frame(item, base, allow_near_key, soft_alpha=False):
    """(path, key-colour image, ink bounds, matte); the matte is None unless the job's frames carry true alpha, which is split into art and coverage."""
    path = common.safe_member(base, item["file"], "frame file")
    if not path.is_file():
        raise ValueError(f"Missing source frame: {path}")
    matte = None
    if soft_alpha:
        from PIL import Image
        with Image.open(path) as opened:
            image, matte = matte_rules.split(opened)
    else:
        image = common.load_rgba(path, str(path))
    report = common.key_policy_report(image, allow_near_key=allow_near_key)
    if report["issues"]:
        raise ValueError(f"{path.name}: " + "; ".join(report["issues"]))
    bounds = ink_bounds(image)
    if bounds is None and not item.get("allow_empty"):
        raise ValueError(f"{path.name}: frame contains no artwork (set allow_empty for a deliberately blank frame)")
    return path, image, bounds, matte


UI_FIELDS = ("nine_slice", "state", "control", "set")


def with_ui_fields(entry, item):
    """The atlas entry with the UI fields the job gave this frame (a frame without them gets none, so older jobs build as before)."""
    for key in UI_FIELDS:
        if key in item:
            entry[key] = item[key]
    return entry


def trimmed_cell(image, bounds, pivot, padding):
    """For one frame: the box of the source frame to keep (its art joined with its pivot, so the pivot stays inside the cell), the cell size,
    the pivot in cell coordinates and where the source frame's top-left corner falls in the cell (negative when pixels were cut away)."""
    width, height = image.size
    if bounds is None:  # a deliberately blank frame keeps one pixel at its pivot
        x0, y0 = min(pivot[0], width - 1), min(pivot[1], height - 1)
        x1, y1 = x0 + 1, y0 + 1
    else:
        x0, y0 = min(bounds[0], pivot[0]), min(bounds[1], pivot[1])
        x1, y1 = max(bounds[0] + bounds[2], pivot[0]), max(bounds[1] + bounds[3], pivot[1])
    box = (x0, y0, x1 - x0, y1 - y0)
    offset = [padding - x0, padding - y0]
    return box, (box[2] + 2 * padding, box[3] + 2 * padding), [pivot[0] + offset[0], pivot[1] + offset[1]], offset


def shelf_positions(sizes, spacing, max_width):
    """Top-left corner of every cell when cells are placed left to right in rows ('shelves'), tallest first, wrapping at `max_width`.
    Deterministic: ties keep job order. Returns (positions by index, sheet width, sheet height)."""
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][1], -sizes[i][0], i))
    positions, x, y, shelf_height, used = {}, 0, 0, 0, 0
    for i in order:
        width, height = sizes[i]
        if x and x + width > max_width:
            y += shelf_height + spacing
            x = shelf_height = 0
        positions[i] = (x, y)
        x += width + spacing
        shelf_height = max(shelf_height, height)
        used = max(used, x - spacing)
    return positions, used, y + shelf_height


def build(manifest, output_dir):
    if not isinstance(manifest, dict):
        raise ValueError("Input manifest must be a JSON object")
    common.validate_schema(manifest, "gamearts-frames-job")
    base = Path(manifest["_input_dir"])
    name = manifest["name"]
    frames = manifest["frames"]
    cols = manifest.get("columns", len(frames))
    if not 1 <= cols <= len(frames):
        raise ValueError("columns must be 1..frame count")
    padding, spacing = manifest.get("padding", 2), manifest.get("spacing", 0)
    allow_near_key = bool(manifest.get("allow_near_key", False))
    full_bleed = bool(manifest.get("full_bleed", False))
    pack, trim = manifest.get("pack", "grid"), bool(manifest.get("trim", False))
    soft_alpha, mattes = bool(manifest.get("soft_alpha", False)), []
    if pack == "shelf" and "columns" in manifest:
        raise ValueError("columns applies to the grid layout only; a shelf layout is limited by max_width instead")
    if trim and pack != "shelf":
        raise ValueError("trim needs pack 'shelf': trimmed cells differ in size, and a grid has equal cells")
    max_width = manifest.get("max_width", DEFAULT_MAX_WIDTH)
    tags = manifest.get("tags")
    if tags is not None:
        tag_problems = atlas_rules.tag_problems(tags, len(frames))
        if tag_problems:
            raise ValueError("tags: " + "; ".join(tag_problems))
    seen_names = set()
    rest = []
    for i, item in enumerate(frames):
        frame_name = item.get("name", f"frame_{i:03d}")
        if frame_name in seen_names:
            raise ValueError(f"duplicate frame name: {frame_name}")
        seen_names.add(frame_name)
        path, image, bounds, frame_matte = load_frame(item, base, allow_near_key, soft_alpha)
        mattes.append(frame_matte)
        pivot = integer_pair(item.get("pivot", [image.width // 2, image.height - 1]), f"frame {i}.pivot")
        if not (0 <= pivot[0] <= image.width and 0 <= pivot[1] <= image.height):
            raise ValueError(f"frame {i}: pivot {pivot} lies outside its {image.width}x{image.height} image")
        anchors = item.get("anchors", {})
        for key, v in anchors.items():
            integer_pair(v, f"frame {i} anchor {key}")
        rest.append((item, frame_name, path, image, bounds, pivot, anchors))

    if pack == "shelf":
        cells = [trimmed_cell(p[3], p[4], p[5], padding) if trim and not p[0].get("nine_slice") else None for p in rest]  # a nine-slice frame keeps every pixel
        for i, (item, frame_name, source, image, bounds, pivot, anchors) in enumerate(rest):
            if cells[i] is None:  # untrimmed shelf: every cell holds its whole frame
                cells[i] = ((0, 0, image.width, image.height), (image.width + 2 * padding, image.height + 2 * padding),
                            [pivot[0] + padding, pivot[1] + padding], [padding, padding])
            if cells[i][1][0] > max_width:
                raise ValueError(f"frame {frame_name}: its cell is {cells[i][1][0]} px wide, wider than max_width {max_width}")
        positions, sheet_w, sheet_h = shelf_positions([c[1] for c in cells], spacing, max_width)
        check_sheet_size(sheet_w, sheet_h)
        sheet = Image.new("RGBA", (sheet_w, sheet_h), common.KEY_RGBA)
        matte_sheet = Image.new("L", (sheet_w, sheet_h), 0) if soft_alpha else None
        result_frames, rects = [], []
        for i, (item, frame_name, source, image, bounds, pivot, anchors) in enumerate(rest):
            box, (cell_w, cell_h), cell_pivot, offset = cells[i]
            cell_x, cell_y = positions[i]
            crop = (box[0], box[1], box[0] + box[2], box[1] + box[3])
            sheet.paste(image.crop(crop), (cell_x + padding, cell_y + padding))
            if soft_alpha:
                matte_sheet.paste(mattes[i].crop(crop), (cell_x + padding, cell_y + padding))
            rects.append((cell_x, cell_y, cell_w, cell_h))
            entry = {"index": i, "name": frame_name, "direction": item.get("direction"), "action": item.get("action"),
                     "rect": [cell_x, cell_y, cell_w, cell_h], "source_size": [image.width, image.height],
                     "source_ink_bounds": bounds, "source_offset_in_cell": offset, "pivot": cell_pivot,
                     "anchors": {key: [offset[0] + v[0], offset[1] + v[1]] for key, v in anchors.items()},
                     "duration_ms": item.get("duration_ms", manifest.get("duration_ms", 125)),
                     "source_file": item["file"], "source_sha256": common.sha256_file(source)}
            if trim:
                entry["trim"] = list(box)
                entry["trimmed"] = list(box) != [0, 0, image.width, image.height]
            result_frames.append(with_ui_fields(entry, item))
        cell_w = cell_h = rows = None
    else:
        # One canonical pivot location per cell; never change the physical pixel scale.
        left = max(p[5][0] for p in rest) + padding
        top = max(p[5][1] for p in rest) + padding
        right = max(p[3].width - p[5][0] for p in rest) + padding
        bottom = max(p[3].height - p[5][1] for p in rest) + padding
        cell_w, cell_h = left + right, top + bottom
        rows = (len(rest) + cols - 1) // cols
        sheet_w = cols * cell_w + max(0, cols - 1) * spacing
        sheet_h = rows * cell_h + max(0, rows - 1) * spacing
        check_sheet_size(sheet_w, sheet_h)
        sheet = Image.new("RGBA", (sheet_w, sheet_h), common.KEY_RGBA)
        matte_sheet = Image.new("L", (sheet_w, sheet_h), 0) if soft_alpha else None
        result_frames, rects = [], []
        for i, (item, frame_name, source, image, bounds, pivot, anchors) in enumerate(rest):
            col, row = i % cols, i // cols
            cell_x, cell_y = col * (cell_w + spacing), row * (cell_h + spacing)
            dx, dy = cell_x + left - pivot[0], cell_y + top - pivot[1]
            sheet.paste(image, (dx, dy))
            if soft_alpha:
                matte_sheet.paste(mattes[i], (dx, dy))
            rects.append((cell_x, cell_y, cell_w, cell_h))
            result_frames.append(with_ui_fields({
                "index": i, "name": frame_name, "direction": item.get("direction"), "action": item.get("action"),
                "rect": [cell_x, cell_y, cell_w, cell_h], "source_size": [image.width, image.height],
                "source_ink_bounds": bounds, "source_offset_in_cell": [dx - cell_x, dy - cell_y],
                "pivot": [left, top],
                "anchors": {key: [dx - cell_x + v[0], dy - cell_y + v[1]] for key, v in anchors.items()},
                "duration_ms": item.get("duration_ms", manifest.get("duration_ms", 125)),
                "source_file": item["file"], "source_sha256": common.sha256_file(source)}, item))
    report = common.key_policy_report(sheet, rects, allow_near_key=allow_near_key, full_bleed=full_bleed)
    if report["issues"]:
        raise ValueError("Assembled sheet violates the exact-key contract: " + "; ".join(report["issues"]))
    atlas = {
        "schema_version": "1.0", "generator": "GameArtsSkills/build_sheet_atlas.py",
        "asset_id": manifest.get("asset_id", name), "name": name, "image": name + ".png",
        "image_size": [sheet_w, sheet_h], "cell_size": [cell_w, cell_h], "columns": cols, "rows": rows,
        "mask_color": common.KEY_HEX, "background_alpha": 255,
        "coordinate_system": "top_left_pixels_exclusive_bounds", "pivot_coordinate_space": "frame_cell_local",
        "pixels_per_meter": manifest.get("pixels_per_meter"), "component": manifest.get("component"),
        "parent_attachment": manifest.get("parent_attachment"), "attachment_tracks": manifest.get("attachment_tracks", {}),
        "source_mockups": manifest.get("source_mockups", []), "frames": result_frames,
        "validation": {"geometry": "generated_from_source_pixels", "key_policy": "passed",
                       "visual_review": "not_performed", "engine_validation": "not_tested"}}
    if pack == "shelf":  # a shelf has no equal cells, so no cell size, columns or rows
        for key in ("cell_size", "columns", "rows"):
            del atlas[key]
        atlas["layout"] = "shelf"
    if tags is not None:
        atlas["tags"] = tags
    if manifest.get("controls") is not None:
        atlas["controls"] = manifest["controls"]
    if "blend_mode" in manifest:
        atlas["blend_mode"] = manifest["blend_mode"]
    common.validate_schema(atlas, "gamearts-atlas")  # the shape first, so the cross-checks below can rely on it
    ui = atlas_rules.ui_problems(atlas)
    if ui:
        raise ValueError("ui: " + "; ".join(ui))
    if allow_near_key:
        atlas["allow_near_key"] = True
    if full_bleed:
        atlas["full_bleed"] = True
    common.validate_schema(atlas, "gamearts-atlas")
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / (name + ".png")
    atlas_path = output_dir / (name + ".atlas.json")
    if image_path.exists() or atlas_path.exists():
        raise FileExistsError("Output revision already exists; choose a new descriptive revision/name")
    tmp_png = output_dir / (name + ".build-tmp.png")
    matte_path = output_dir / matte_rules.matte_name(name + ".png")
    try:
        sheet.save(tmp_png)
        common.replace_file(tmp_png, image_path)
        if soft_alpha:
            matte_sheet.save(tmp_png)
            common.replace_file(tmp_png, matte_path)
            atlas["matte"] = matte_rules.record(matte_path)
            common.validate_schema(atlas, "gamearts-atlas")
        common.atomic_write_json(atlas_path, atlas)
    except BaseException:
        for leftover in (tmp_png, image_path, atlas_path, matte_path):
            leftover.unlink(missing_ok=True)
        raise
    return image_path, atlas_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, help="Say whether the new sheet fits this game's saved settings (scale)")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Input manifest must be a JSON object")
        manifest["_input_dir"] = str(args.manifest.resolve().parent)
        png, atlas = build(manifest, args.output_dir.resolve())
        print(f"BUILT {png} and {atlas}")
        if args.game_root:
            settings_fit.announce(args.game_root, args.output_dir.resolve())
    except (OSError, ValueError, KeyError, TypeError) as exc:  # ValueError covers JSON and contract errors
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
