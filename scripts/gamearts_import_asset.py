#!/usr/bin/env python3
"""Adopt art the owner already has: a supplied sprite sheet becomes a measured, registered asset, and optionally the game's style anchor.

Run through the lifecycle: `python scripts/gamearts_asset_lifecycle.py import-asset --game-root GAME --source SHEET.png --id ID --revision v001
(--grid COLSxROWS | --cell WxH | --data FILE.json) --user-approval-ref "<the owner's words>" [--rights owned] [--anchor] [--extract-palette NAME]`.

The sheet's layout is stated by the owner: a grid, a cell size, or the data file Aseprite writes beside a sheet (array or hash form), which also gives
each frame its time and the sheet its tags. Transparency becomes the key colour; a soft (partly transparent) pixel cannot be, so it is refused with its
count unless the owner chooses an alpha threshold that turns each into art or empty. Trimmed frames are put back on a canvas of their source size and rotated
frames are refused. The original file is never changed.

What it records: the keyed picture is imported as a managed mockup and approved on the owner's own words (they are saying this art is theirs and is the
reference), the frames are re-assembled into a measured sheet and atlas by the one sheet builder, and the asset is registered as `generated` with
provenance "supplied by the user" and the rights the owner states. The production asset still needs its own approval. With `anchor`, the same picture is
also imported as an approved style board and offered as `art_style.anchor`; saving that is a change to the look, so the owner confirms it elsewhere.
Everything is checked in a scratch folder before the game is written to; if registration then fails, the new bundle is removed and the message says which
reference stayed.
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_sheet_atlas as sheets  # noqa: E402
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_atlas as atlas_rules  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_palette as palette  # noqa: E402

DEFAULT_DURATION_MS = 125
MAX_COLUMNS = 8


def key_sheet(image, alpha_threshold=None):
    """(opaque RGBA sheet, facts): every fully transparent pixel becomes the key colour. A partly transparent pixel cannot be shown as art or as the key
    colour alone, so without `alpha_threshold` any such pixel is refused; with it, a pixel at or above the threshold keeps its colour as art and one below
    becomes the key colour."""
    from PIL import Image
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    counts = alpha.histogram()
    facts = {"transparent_pixels_keyed": counts[0], "soft_pixels_made_art": 0, "soft_pixels_made_empty": 0, "alpha_threshold": alpha_threshold}
    soft = sum(counts[1:255])
    if soft and alpha_threshold is None:
        raise ValueError(f"{soft} pixel(s) are partly transparent (soft edges). Game Arts sheets hold only art and the key colour, so choose an alpha threshold "
                         "(for example 128: a pixel at least that opaque becomes art, any other becomes empty), or have the art redrawn with hard edges")
    if alpha_threshold is not None:
        facts["soft_pixels_made_art"] = sum(counts[alpha_threshold:255])
        facts["soft_pixels_made_empty"] = sum(counts[1:alpha_threshold])
    cutoff = alpha_threshold if alpha_threshold is not None else 1
    art = alpha.point(lambda value: 255 if value >= cutoff else 0)
    keyed = Image.composite(rgba.convert("RGB"), Image.new("RGB", rgba.size, common.KEY_RGB), art).convert("RGBA")
    return keyed, facts


def grid_rects(size, grid=None, cell=None):
    """The frame rectangles [x, y, w, h], row by row, of a sheet cut by a stated grid (columns, rows) or cell size (w, h)."""
    width, height = size
    if grid:
        columns, rows = grid
        if columns < 1 or rows < 1 or width % columns or height % rows:
            raise ValueError(f"The sheet is {width} x {height}, which does not divide into {columns} columns and {rows} rows of whole pixels")
        cell = (width // columns, height // rows)
    cell_w, cell_h = cell
    if cell_w < 1 or cell_h < 1 or width % cell_w or height % cell_h:
        raise ValueError(f"The sheet is {width} x {height}, which does not divide into cells of {cell_w} x {cell_h}")
    return [[x, y, cell_w, cell_h] for y in range(0, height, cell_h) for x in range(0, width, cell_w)]


def read_frame_data(path, sheet_size):
    """(frames, tags) from the data file Aseprite writes beside a sheet, in its array or hash form. Each frame is
    {name, rect, duration_ms, source_size, offset}; `offset` is where the kept rectangle sat inside the source picture."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"The data file {path.name} could not be read: {exc}") from exc
    listed = data.get("frames") if isinstance(data, dict) else None
    if isinstance(listed, dict):
        entries = [(name, entry) for name, entry in listed.items()]
    elif isinstance(listed, list):
        entries = [(entry.get("filename", f"frame_{index:03d}"), entry) for index, entry in enumerate(listed)]
    else:
        entries = []
    if not entries:
        raise ValueError(f"The data file {path.name} has no frames")
    frames, names = [], set()
    for name, entry in entries:
        if name in names:
            raise ValueError(f"The frame name {name!r} is used more than once in the data file")
        names.add(name)
        if entry.get("rotated"):
            raise ValueError(f"{name}: a rotated frame is not supported; export the sheet again without rotation")
        rect = entry["frame"]
        x, y, w, h = rect["x"], rect["y"], rect["w"], rect["h"]
        if w < 1 or h < 1 or x < 0 or y < 0 or x + w > sheet_size[0] or y + h > sheet_size[1]:
            raise ValueError(f"{name}: its frame {x},{y} {w}x{h} lies outside the sheet ({sheet_size[0]} x {sheet_size[1]})")
        source = entry.get("sourceSize") or {"w": w, "h": h}
        placed = entry.get("spriteSourceSize") or {"x": 0, "y": 0}
        duration = entry.get("duration")
        frames.append({"name": name, "rect": [x, y, w, h], "duration_ms": duration if type(duration) is int and duration >= 1 else None,
                       "source_size": [source["w"], source["h"]], "offset": [placed.get("x", 0), placed.get("y", 0)]})
    tags = []
    for tag in (data.get("meta") or {}).get("frameTags", []):
        shown = {"name": tag.get("name"), "from": tag.get("from"), "to": tag.get("to"), "direction": tag.get("direction", "forward")}
        repeat = tag.get("repeat")
        if repeat is not None:
            shown["repeat"] = int(repeat)
        tags.append(shown)
    problems = atlas_rules.tag_problems(tags, len(frames))
    if problems:
        raise ValueError("The data file's tags: " + "; ".join(problems))
    return frames, tags


def _frame_pictures(keyed, rects, data_frames):
    """[(picture, name_or_None, duration_or_None)]: each frame cut from the keyed sheet, trimmed ones put back on a canvas of their source size."""
    from PIL import Image
    pictures = []
    for index, rect in enumerate(rects):
        x, y, w, h = rect
        piece = keyed.crop((x, y, x + w, y + h))
        if data_frames:
            info = data_frames[index]
            if info["source_size"] != [w, h] or info["offset"] != [0, 0]:
                canvas = Image.new("RGBA", tuple(info["source_size"]), common.KEY_RGBA)
                canvas.paste(piece, tuple(info["offset"]))
                piece = canvas
        pictures.append(piece)
    return pictures


def _check_options(rights, approval_reference, alpha_threshold, layout):
    common.require_rights(rights)
    if not isinstance(approval_reference, str) or not approval_reference.strip():
        raise ValueError("An imported reference needs the owner's own words that this art is theirs and approved as the reference; never an invented approval")
    if alpha_threshold is not None and (type(alpha_threshold) is not int or not 1 <= alpha_threshold <= 255):
        raise ValueError("The alpha threshold must be a whole number from 1 to 255")
    if len([key for key in ("grid", "cell", "data") if key in layout]) != 1:
        raise ValueError("Say how the sheet is laid out with exactly one of: a grid, a cell size, or a data file")


def _palette_check(counts, colours):
    """Whether the imported art keeps to the game's palette. A report, not a refusal: the owner decides whether to widen the palette or change the art."""
    allowed = set(colours)
    off = {colour: n for colour, n in counts.items() if colour not in allowed}
    if not off:
        return {"status": "passed", "message": "Every artwork pixel uses a colour of the game's palette"}
    examples = [palette.hex_of(c) for c, _ in sorted(off.items(), key=lambda item: (-item[1], item[0]))[:3]]
    return {"status": "failed", "off_palette_colours": len(off), "off_palette_pixels": sum(off.values()), "examples": examples,
            "message": f"{sum(off.values())} pixels use {len(off)} colours that are not in the game's palette ({', '.join(examples)}); approving this art will fail the exact-palette check "
                       "until the owner adds them to the palette or changes the art"}


def import_asset(game_root, source, asset_id, revision, layout, rights="user_supplied", rights_notes="", approval_reference=None, duration_ms=None,
                 pivot=None, alpha_threshold=None, anchor=False, palette_name=None):
    """Adopt the sheet at `source`; `layout` is {"grid": (columns, rows)}, {"cell": (w, h)} or {"data": path}. Returns the asset, the reference, the counts
    and, when asked for, the style-anchor offer and the palette. Nothing in the game changes until the sheet, its frames and its data have all checked out."""
    from PIL import Image
    root = common.game_root(game_root)
    _check_options(rights, approval_reference, alpha_threshold, layout)
    if not common.SLUG.fullmatch(asset_id or "") or not common.REVISION.fullmatch(revision or ""):
        raise ValueError("The asset id must be a filename-safe id and the revision must look like v001")
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"The sheet must be a regular file: {source}")
    settings, _, _ = common.load_project_settings(root, require_confirmed=True)  # an import writes to the game exactly as a generated mockup does
    mockup_id, style_id = f"{asset_id}-supplied", f"{asset_id}-style"
    if any(r.get("asset_id") == asset_id and r.get("revision") == revision for r in life.records(root, "assets")):
        raise ValueError(f"Asset {asset_id} {revision} is already registered; use a new revision")
    taken = {(r.get("mockup_id"), r.get("revision")) for r in life.records(root, "mockups")}
    for needed in [mockup_id] + ([style_id] if anchor else []):
        if (needed, revision) in taken:
            raise ValueError(f"Mockup {needed} {revision} already exists; use a new revision")
    with Image.open(source) as opened:
        keyed, alpha = key_sheet(opened, alpha_threshold)
    data_frames, tags = (read_frame_data(layout["data"], keyed.size) if "data" in layout else (None, []))
    rects = [info["rect"] for info in data_frames] if data_frames else grid_rects(keyed.size, layout.get("grid"), layout.get("cell"))
    pictures = _frame_pictures(keyed, rects, data_frames)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", asset_id)
    name = f"{safe}_{revision}"
    items, blank = [], 0
    for index, picture in enumerate(pictures):
        item = {"file": f"f{index:04d}.png", "name": data_frames[index]["name"] if data_frames else f"{safe}_{index:03d}"}
        duration = duration_ms or (data_frames[index]["duration_ms"] if data_frames else None) or DEFAULT_DURATION_MS
        item["duration_ms"] = duration
        if pivot:
            item["pivot"] = list(pivot)
        if common.ink_bbox(picture) is None:
            item["allow_empty"] = True
            blank += 1
        items.append(item)
    job = {"name": name, "asset_id": asset_id, "columns": min(len(items), MAX_COLUMNS), "padding": 2, "frames": items}
    if tags:
        job["tags"] = tags
    with tempfile.TemporaryDirectory(prefix="gamearts-adopt-") as scratch:
        scratch = Path(scratch)
        frames_dir = scratch / "frames"
        frames_dir.mkdir()
        for item, picture in zip(items, pictures):
            picture.save(frames_dir / item["file"])
        job["_input_dir"] = str(frames_dir)
        sheets.build(dict(job), scratch / "dry_run")  # every frame, tag and pivot is checked here, before the game is touched
        keyed_path = scratch / "supplied_keyed.png"
        keyed.save(keyed_path)
        bundle = root / ".gamearts" / "outputs" / "assets" / "generated" / name
        if bundle.exists():
            raise ValueError(f"{bundle.relative_to(root).as_posix()} already exists; use a new revision")
        notes = f"Supplied by the user ({source.name}); frames cut from the sheet and transparency turned into the key colour"
        if alpha_threshold is not None:
            notes += f"; soft edges flattened at alpha threshold {alpha_threshold}"
        life.import_mockup(root, keyed_path, mockup_id, revision, "asset", rights, rights_notes, notes=notes, approval_reference=approval_reference)
        sheets.build(job, bundle)
        extra = {"provenance": {"provider": "supplied by the user", "edit_mode": notes}, "rights": {"status": rights, "notes": rights_notes}}
        try:
            registered = life.register_asset(root, asset_id, revision, bundle.relative_to(root).as_posix(), [(mockup_id, revision)], extra)
        except (ValueError, OSError) as exc:
            shutil.rmtree(bundle)  # nothing half-registered stays behind
            raise ValueError(f"{exc}. The picture was imported as the approved reference {mockup_id} {revision} and that reference stays registered.") from exc
        result = {"asset": registered, "mockup": {"mockup_id": mockup_id, "revision": revision, "scope": "asset", "status": "approved"},
                  "frames": len(items), "blank_frames": blank, "tags": len(tags), "alpha": alpha, "ok": registered["technical_validation"] == "passed"}
        game_palette = palette.project_palette(root, settings)
        if game_palette is not None:  # the owner already chose a palette: say now whether this art keeps to it, not at approval
            result["palette_check"] = _palette_check(palette.art_colour_counts(keyed), game_palette)
        if anchor:
            life.import_mockup(root, keyed_path, style_id, revision, "style", rights, rights_notes, notes=notes, approval_reference=approval_reference)
            result["anchor_offer"] = {"mockup_id": style_id, "revision": revision, "scope": "style", "status": "approved",
                                      "next_step": f"To use this art as the game's look, save art_style.anchor as {{mockup_id: {style_id}, revision: {revision}}} through the project "
                                                   "setup; it changes the look, so the owner confirms it."}
        if palette_name:
            record = palette.extract(keyed_path, palette_name, root / palette.PALETTE_DIR, 32, root)
            reference = (palette.PALETTE_DIR / f"{palette_name}{palette.SUFFIX}").as_posix()
            result["palette"] = {"palette_reference": reference, "colours": len(record["colours"]),
                                 "next_step": f"To check later art against these colours, save art_style.palette_reference as {reference} through the project setup; the owner confirms it."}
    return result
