#!/usr/bin/env python3
"""Build a chroma-pink PNG sprite sheet AND its measured JSON atlas.

Usage (normally invoked automatically by Claude/Codex):
  python scripts/build_sheet_atlas.py path/to/frames.json --output-dir path/to/generated

See docs/ATLAS_GENERATION.md for the input contract. Requires Pillow.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

PINK = (255, 0, 255, 255)


def integer_pair(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(
        type(x) is not int for x in value
    ):
        raise ValueError(f"{name}: expected two integer coordinates")
    return list(value)


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ink_bounds(image):
    # Exclusive right/bottom bounds; no alpha transparency.
    mask = image.convert("RGB").point(
        lambda v: 0 if v == 255 else 255
    ) if False else None  # Do not use RGB thresholding: artwork can include magenta-like colors.
    px = image.load()
    xmin, ymin, xmax, ymax = image.width, image.height, -1, -1
    for y in range(image.height):
        for x in range(image.width):
            if px[x, y] != PINK:
                xmin, ymin = min(xmin, x), min(ymin, y)
                xmax, ymax = max(xmax, x), max(ymax, y)
    if xmax < xmin:
        return None
    return [xmin, ymin, xmax + 1 - xmin, ymax + 1 - ymin]


def load_frame(item, base):
    if not isinstance(item, dict) or not item.get("file"):
        raise ValueError("Each frame must include a file path")
    path = (base / item["file"]).resolve()
    if not path.is_file():
        raise ValueError(f"Missing source frame: {path}")
    with Image.open(path) as src:
        image = src.convert("RGBA")
    if image.getchannel("A").getextrema() != (255, 255):
        raise ValueError(f"{path}: source must be fully opaque; no alpha pixels allowed")
    return path, image, ink_bounds(image)


def build(manifest, output_dir):
    if not isinstance(manifest, dict):
        raise ValueError("Input manifest must be a JSON object")
    base = Path(manifest["_input_dir"])
    name = manifest.get("name")
    if not isinstance(name, str) or not name or any(c not in
          "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise ValueError("name must be a simple descriptive file slug (letters/numbers/_/-)")
    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("frames must be a nonempty list")
    cols = manifest.get("columns", len(frames))
    if type(cols) is not int or not (1 <= cols <= len(frames)):
        raise ValueError("columns must be 1..frame count")
    padding = manifest.get("padding", 2)
    if type(padding) is not int or not (0 <= padding <= 2048):
        raise ValueError("padding must be an integer >= 0 and <= 2048")
    spacing = manifest.get("spacing", 0)
    if type(spacing) is not int or not (0 <= spacing <= 2048):
        raise ValueError("spacing must be an integer >= 0 and <= 2048")
    rest = []
    for i, item in enumerate(frames):
        path, image, bounds = load_frame(item, base)
        pivot = integer_pair(item.get("pivot", [image.width // 2, image.height - 1]), f"frame {i}.pivot")
        anchors = item.get("anchors", {})
        if not isinstance(anchors, dict):
            raise ValueError(f"frame {i}.anchors must be a mapping")
        for key, v in anchors.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"frame {i}: invalid anchor name")
            integer_pair(v, f"frame {i} anchor {key}")
        if "duration_ms" in item and (type(item["duration_ms"]) is not int or item["duration_ms"] <= 0):
            raise ValueError(f"frame {i}: duration_ms must be a positive integer")
        rest.append((item, path, image, bounds, pivot, anchors))

    # One canonical pivot location per cell; never change the physical pixel scale.
    left = max(p[4][0] for p in rest) + padding
    top = max(p[4][1] for p in rest) + padding
    right = max(p[2].width - p[4][0] for p in rest) + padding
    bottom = max(p[2].height - p[4][1] for p in rest) + padding
    cell_w, cell_h = left + right, top + bottom
    rows = (len(rest) + cols - 1) // cols
    sheet_w = cols * cell_w + max(0, cols - 1) * spacing
    sheet_h = rows * cell_h + max(0, rows - 1) * spacing
    sheet = Image.new("RGBA", (sheet_w, sheet_h), PINK)
    result_frames = []
    for i, (item, source, image, bounds, pivot, anchors) in enumerate(rest):
        col, row = i % cols, i // cols
        cell_x, cell_y = col * (cell_w + spacing), row * (cell_h + spacing)
        dx, dy = cell_x + left - pivot[0], cell_y + top - pivot[1]
        # Frames have opaque pink mask; paste only non-key colored pixels.
        # Avoid overwriting another layer with pink; no compositing is performed here.
        sheet.paste(image, (dx, dy))
        anchor_positions = {key: [dx - cell_x + v[0], dy - cell_y + v[1]]
                            for key, v in anchors.items()}
        frame = {
            "index": i,
            "name": item.get("name", f"frame_{i:03d}"),
            "direction": item.get("direction"),
            "action": item.get("action"),
            "rect": [cell_x, cell_y, cell_w, cell_h],
            "source_size": [image.width, image.height],
            "source_ink_bounds": bounds,
            "source_offset_in_cell": [dx - cell_x, dy - cell_y],
            "pivot": [left, top],
            "anchors": anchor_positions,
            "duration_ms": item.get("duration_ms", manifest.get("duration_ms", 125)),
            "source_file": item["file"],
            "source_sha256": hash_file(source)
        }
        result_frames.append(frame)
    atlas = {
        "schema_version": "1.0",
        "generator": "GameArtsSkills/build_sheet_atlas.py",
        "asset_id": manifest.get("asset_id", name),
        "name": name,
        "image": name + ".png",
        "image_size": [sheet_w, sheet_h],
        "cell_size": [cell_w, cell_h],
        "columns": cols,
        "rows": rows,
        "mask_color": "#FF00FF",
        "background_alpha": 255,
        "coordinate_system": "top_left_pixels_exclusive_bounds",
        "pivot_coordinate_space": "frame_cell_local",
        "pixels_per_meter": manifest.get("pixels_per_meter"),
        "component": manifest.get("component"),
        "parent_attachment": manifest.get("parent_attachment"),
        "attachment_tracks": manifest.get("attachment_tracks", {}),
        "source_mockups": manifest.get("source_mockups", []),
        "frames": result_frames,
        "validation": {"geometry": "generated_from_source_pixels",
                       "visual_review": "not_performed",
                       "godot_runtime": "not_tested"}
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / (name + ".png")
    atlas_path = output_dir / (name + ".atlas.json")
    if image_path.exists() or atlas_path.exists():
        raise FileExistsError("Output version already exists; choose a new descriptive revision/name")
    # Atomic-ish pair: write temporary files, then rename; clean up on any failure.
    tmp_png = output_dir / (name + ".build-tmp.png")
    tmp_json = output_dir / (name + ".atlas.build-tmp.json")
    try:
        sheet.save(tmp_png)
        tmp_json.write_text(json.dumps(atlas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp_png.replace(image_path)
        tmp_json.replace(atlas_path)
    except Exception:
        tmp_png.unlink(missing_ok=True)
        tmp_json.unlink(missing_ok=True)
        image_path.unlink(missing_ok=True)
        atlas_path.unlink(missing_ok=True)
        raise
    return image_path, atlas_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        manifest["_input_dir"] = str(args.manifest.resolve().parent)
        png, atlas = build(manifest, args.output_dir.resolve())
        print(f"BUILT {png} and {atlas}")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
