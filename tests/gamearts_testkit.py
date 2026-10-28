"""Shared fixtures for the Game Arts tests: a schema-valid owner-confirmed game project and small PNG helpers."""
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_sheet_atlas import build as build_sheet  # noqa: E402

PINK = (255, 0, 255, 255)
EIGHT = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def settings(**overrides):
    """A complete project.json body that passes schemas/gamearts-project.schema.json and is owner_confirmed."""
    body = {
        "schema_version": "1.0", "project_id": "test_project",
        "settings_status": "owner_confirmed", "confirmed_at": "2026-10-23T00:00:00+00:00", "confirmed_by": "test owner",
        "art_style": {"id": "illustrated", "outline_policy": "fine charcoal"},
        "world": {"grid": "orthogonal_square", "camera_profile": "orthogonal_3_4_oblique",
                  "object_camera": "elevated orthographic oblique", "logical_tile_m": [16, 16],
                  "ground_tile_px": [256, 256], "pixels_per_meter": 16, "construction_snap_m": 1},
        "directions": list(EIGHT),
        "animation": {"preferred_method": "hybrid", "animated_attachment_anchors": True},
        "workflow": {"mockup_approval_required": True, "detail_decomposition_required": True},
        "export": {"background_hex": "#FF00FF", "background_alpha": 255, "atlas_per_sheet": True, "no_zip": True},
    }
    drop = overrides.pop("drop", ())  # names of settings to remove, for projects that legitimately have no such block
    body.update(copy.deepcopy(overrides))
    for name in drop:
        body.pop(name, None)
    return body


def write_settings(root, **overrides):
    path = Path(root) / ".gamearts" / "project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings(**overrides), indent=2), encoding="utf-8")
    return path


def key_image(size, ink=None):
    """Opaque key-colour image with optional {(x, y): rgba} ink pixels."""
    image = Image.new("RGBA", size, PINK)
    for point, color in (ink or {}).items():
        image.putpixel(point, color)
    return image


def make_sheet(folder, name, asset_id):
    """Build a genuine two-cell sheet + measured atlas in `folder`; the 3 px gutter lies outside every frame."""
    with tempfile.TemporaryDirectory() as frames:
        key_image((12, 10), {(4, 5): (20, 50, 90, 255)}).save(Path(frames) / "frame.png")
        build_sheet({"_input_dir": frames, "name": name, "asset_id": asset_id, "columns": 2, "padding": 2, "spacing": 3,
                     "frames": [{"file": "frame.png", "name": "S0", "direction": "S", "pivot": [4, 9], "duration_ms": 100},
                                {"file": "frame.png", "name": "S1", "direction": "S", "pivot": [4, 9], "duration_ms": 100}]},
                    Path(folder))
    return [f"{name}.png", f"{name}.atlas.json"]


def shaded_picture(size, colour):
    """A picture that is not one flat colour (a lighter patch in one corner), as a real mockup is: the lifecycle audit refuses a blank one."""
    image = Image.new("RGB", size, colour)
    image.paste(tuple(min(255, c + 60) for c in colour), (0, 0, max(1, size[0] // 4), max(1, size[1] // 4)))
    return image


def make_mockup(root, mockup_id="test-scene", revision="v001", scope="world", scene=None, picture_image=None):
    """A generated mockup image with its metadata contract file, ready for register_mockup; returns (image, metadata).

    `picture_image` (a PIL image) replaces the default flat-colour picture."""
    generated = Path(root) / ".gamearts" / "outputs" / "mockups" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    image = generated / f"{mockup_id.replace('-', '_')}_mockup_{revision}.png"
    shade = int(hashlib.sha256(f"{mockup_id}{revision}".encode()).hexdigest()[:2], 16)
    (picture_image or shaded_picture((64, 40), (shade, 30, 40))).save(image)
    body = {"schema_version": "1.0", "mockup_id": mockup_id, "revision": revision, "scope": scope, "status": "generated",
            "file": image.relative_to(root).as_posix(), "sha256": digest(image),
            "prompt": "A test mockup written by the fixture, not by an image tool.", "prompt_origin": "agent_brief",
            "imagegen_prompt_captured": False, "tool_mode": "built_in_image_gen", "created_at_utc": "2026-10-23T12:00:00Z"}
    if scene:
        body["storyboard_scene_id"] = scene
    metadata = image.with_suffix(".metadata.json")
    metadata.write_text(json.dumps(body))
    return image, metadata


def crop_game(root, asset_class="mobile_directional", **overrides):
    """A game with one approved mockup and settings (`overrides` as for write_settings); returns a reference-crop job for it."""
    root = Path(root)
    approved = root / ".gamearts" / "outputs" / "mockups" / "approved"
    source = picture(approved / "scene_v001.png")
    write_settings(root, **overrides)
    manifest = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    body = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    rows = [row for row in body.get("mockups", []) if row.get("mockup_id") != "scene"]
    rows.append({"mockup_id": "scene", "revision": "v001", "status": "approved", "file": str(source.relative_to(root)), "sha256": digest(source)})
    manifest.write_text(json.dumps({**body, "mockups": rows}))
    return {"asset_id": "thing_v001", "asset_class": asset_class,
            "approved_mockup": {"id": "scene", "revision": "v001", "approval_status": "approved",
                                "file": str(source.relative_to(root)), "sha256": digest(source)},
            "region": {"id": "thing", "rect": [10, 6, 22, 14]}}


def crop_prepare(crop_module, root, job, out="out"):
    """Run prepare_reference_crop.prepare for `job`; returns the packet path."""
    job_file = Path(root) / "job.json"
    job_file.write_text(json.dumps(job))
    return crop_module.prepare(root, job_file, Path(root) / out)


def picture(path, size=(48, 32), rect=(10, 6, 32, 20), inside=(95, 71, 54), outside=(114, 171, 57)):
    """A small opaque RGB 'mockup' picture: a coloured block on a plain field."""
    image = Image.new("RGB", size, outside)
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            image.putpixel((x, y), inside)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return Path(path)
