#!/usr/bin/env python3
"""Single owner of the low-level helpers every Game Arts script shares.

Hashing, safe relative paths, atomic writes, the cross-process lock, JSON-schema validation, the exact-key (#FF00FF)
pixel policy and the project-settings gate live here and nowhere else. Image functions import Pillow lazily so the
updater can use the lock and atomic-write helpers on a machine without it.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

KEY_RGB = (255, 0, 255)
KEY_RGBA = (255, 0, 255, 255)
KEY_HEX = "#FF00FF"
NEAR_KEY_TOLERANCE = 24  # largest per-channel distance still considered key contamination
MOCKUP_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")
REVISION = re.compile(r"v[0-9]{3,}")
SLUG = re.compile(r"[A-Za-z0-9_-]+")
ENGINE_STATUSES = ("not_tested", "passed", "failed")
RIGHTS = ("owned", "licensed", "user_supplied", "unknown")  # what the owner says about the right to use art they supply; the manifest schemas list the same four
MATERIAL_SETTINGS = ("art_style", "world", "directions", "animation", "export")
# Material only when a project sets them, so every project saved before they existed keeps the hash its approved art was made under.
OPTIONAL_MATERIAL_SETTINGS = ("world_kind", "screen")
WORLD_KINDS = ("grid_world", "free_world", "layered_scene", "screen_space")
DEFAULT_WORLD_KIND = "grid_world"
# Named facing-direction sets a project may choose instead of listing directions. The project schema enumerates the same names.
DIRECTION_SETS = {
    "dirs_8": ["S", "SW", "W", "NW", "N", "NE", "E", "SE"],
    "dirs_4": ["S", "W", "N", "E"],
    "dirs_2_side": ["E", "W"],
    "dirs_1_side": ["E"],
    "dirs_1_front": ["S"],
}
SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


class DependencyMissing(ValueError):
    """A required third-party package is not installed; the check cannot run and must not be reported as passed."""


class LockBusy(ValueError):
    """Another Game Arts process holds the lock."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


REPLACE_ATTEMPTS = 12
RETRY_SHARING_VIOLATIONS = os.name == "nt"  # only Windows reports a briefly held file as PermissionError


def _retry_sharing_violation(action, unchanged=lambda: True, explain=None):
    """Run `action`, retrying a PermissionError a bounded number of times with growing pauses. On Windows a replace or move fails with a sharing
    violation while another process (an indexer, an antivirus scan, a sync tool, another thread) briefly holds a file or folder that was just
    written; that clears within milliseconds. Other platforms, other errors, a violation that persists, and a violation after which `unchanged()`
    is no longer true (something half-happened, so repeating would be blind) are raised: unchanged, or as PermissionError(`explain`) when
    `explain` is given."""
    delay = 0.01
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            return action()
        except PermissionError as failure:
            if not RETRY_SHARING_VIOLATIONS or attempt == REPLACE_ATTEMPTS - 1 or not unchanged():
                if explain and RETRY_SHARING_VIOLATIONS:
                    raise PermissionError(explain) from failure
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.25)


def replace_file(temp, path):
    """os.replace with the bounded retry of `_retry_sharing_violation`."""
    _retry_sharing_violation(lambda: os.replace(temp, path))


def move_path(source, destination):
    """shutil.move (a file or a whole folder, such as a bundle being approved) with the same bounded retry as `replace_file`. A retry happens only
    while the source is still in place and the destination is still absent. A violation that persists is explained: it names the likely cause and
    says the move can simply be asked for again. Every script moves and replaces paths through this module, so no step is left without the retry."""
    source, destination = Path(source), Path(destination)
    _retry_sharing_violation(
        lambda: shutil.move(str(source), str(destination)),
        lambda: source.exists() and not destination.exists(),
        f"{source.name} could not be moved to {destination.parent.name}/{destination.name}: another program on this computer (a virus scanner, a file "
        "indexer or a sync tool) is keeping it open. Nothing was changed; wait a moment and ask again.")


def atomic_write_bytes(path, data):
    """Replace `path` with `data` through a uniquely named temp file, so concurrent writers never share one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        replace_file(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def atomic_write_json(path, value):
    atomic_write_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def inside(path, directory):
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False


def safe_member(base, relative, label="path"):
    """Resolve `relative` (forward-slash, may be nested) strictly inside `base`; refuse anything else."""
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError(f"{label} must be a nonempty relative path")
    if relative.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", relative) or ".." in Path(relative.replace("\\", "/")).parts:
        raise ValueError(f"{label} must stay inside its folder: {relative!r}")
    target = (Path(base) / relative).resolve()
    if not inside(target, base):
        raise ValueError(f"{label} escapes its folder: {relative!r}")
    return target


if os.name == "nt":
    import msvcrt

    def _try_lock(handle):
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:  # the byte is locked by another handle
            return False

    def _unlock(handle):
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(handle):
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:  # held through another open file description
            return False

    def _unlock(handle):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def file_lock(path, wait_seconds=0.0, name="Game Arts operation"):
    """Exclusive cross-process lock held through the operating system (msvcrt byte lock / flock).

    The OS releases it when its owner exits or is killed, so there is no stale lock to detect or recover and no lock file
    to delete (deleting a lock file is what makes PID/TTL schemes racy). The file stays, empty, beside the state it guards.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    with open(path, "ab") as handle:
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                raise LockBusy(f"Another {name} is running; try again shortly")
            time.sleep(0.05)
        try:
            yield
        finally:
            _unlock(handle)


def validate_schema(instance, schema_name, path=()):
    """Validate against schemas/<schema_name>.schema.json (or the sub-schema reached by `path`, e.g. a manifest's record
    definition). A missing validator is a failure, never a skip."""
    try:
        import jsonschema
    except ImportError as exc:
        raise DependencyMissing("jsonschema is required for contract validation (pip install jsonschema)") from exc
    schema_file = SCHEMAS / f"{schema_name}.schema.json"
    if not schema_file.is_file():
        raise ValueError(f"Contract schema is missing: {schema_file.name}")
    schema = read_json(schema_file)
    for key in path:
        schema = schema[key]
    try:
        jsonschema.validate(instance, schema)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path) or "(root)"
        raise ValueError(f"{schema_name} contract violation at {where}: {exc.message}") from exc
    return instance


def canonical_settings_hash(settings):
    """Hash of the material project settings only, so formatting or unrelated edits never flag approved art."""
    material = {key: settings.get(key) for key in MATERIAL_SETTINGS}
    material.update({key: settings[key] for key in OPTIONAL_MATERIAL_SETTINGS if key in settings})
    return sha256_bytes(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def require_rights(rights):
    """Refuse a rights value the owner cannot state. The one check, so a command, an import and a registration all give the same answer."""
    if rights not in RIGHTS:
        raise ValueError(f"rights must be {', '.join(RIGHTS[:-1])} or {RIGHTS[-1]}")


def world_kind(settings):
    """The kind of world a project describes; a project saved before world kinds existed is a grid world."""
    return settings.get("world_kind", DEFAULT_WORLD_KIND)


def resolve_directions(settings):
    """The project's facing directions as a list: a named set is expanded, an explicit list is returned as written, and a
    project that declares none (a screen-space game) has none. An unknown set name fails; it is never replaced by a default."""
    value = settings.get("directions")
    if value is None:
        return []
    if isinstance(value, str):
        if value not in DIRECTION_SETS:
            raise ValueError(f"Unknown direction set {value!r}; use one of {', '.join(DIRECTION_SETS)} or list the directions")
        return list(DIRECTION_SETS[value])
    return list(value)


def load_project_settings(root, require_confirmed=True):
    """Return (settings, canonical_hash, raw_hash) after validating `.gamearts/project.json` against its schema."""
    path = Path(root) / ".gamearts" / "project.json"
    if not path.is_file():
        raise ValueError("Missing .gamearts/project.json")
    settings = read_json(path)
    validate_schema(settings, "gamearts-project")
    if require_confirmed:
        if settings.get("settings_status") != "owner_confirmed":
            raise ValueError("Game Arts settings must be owner_confirmed before mockup registration or approval; "
                             "run the project setup confirmation first")
        if not settings.get("confirmed_at") or not settings.get("confirmed_by"):
            raise ValueError("owner_confirmed Game Arts settings require confirmed_at and confirmed_by")
    return settings, canonical_settings_hash(settings), sha256_file(path)


def mockup_records(root):
    """Every record of the game's mockups manifest; a game that has registered nothing has none."""
    path = Path(root) / ".gamearts" / "outputs" / "manifests" / "mockups.json"
    if not path.is_file():
        return []
    data = read_json(path)
    rows = data.get("mockups") if isinstance(data, dict) else None
    return [row for row in (rows or []) if isinstance(row, dict)]


def resolve_style_anchor(root, settings):
    """The style board a project points at (`art_style.anchor`), or None when it names none.

    Returns id, revision, status (`approved`, `generated`, `revoked` or `missing`), scope, the image path and hash when usable, and a
    `problem` sentence when it cannot be used. The one rule for crop packets and check-settings: only an approved `style` board whose
    image still matches its recorded hash is an anchor.
    """
    anchor = settings["art_style"].get("anchor")
    if not anchor:
        return None
    ident, revision = anchor["mockup_id"], anchor["revision"]
    label = f"The saved style anchor {ident} {revision}"
    record = next((r for r in mockup_records(root) if r.get("mockup_id") == ident and r.get("revision") == revision), None)
    result = {"id": ident, "revision": revision, "status": "missing", "scope": None, "path": None, "sha256": None, "problem": None}
    if record is None:
        result["problem"] = f"{label} is not registered: register and approve a style board, or clear art_style.anchor"
        return result
    result.update(status=record.get("status", "missing"), scope=record.get("scope"))
    if result["status"] != "approved":
        result["problem"] = f"{label} is {result['status']}, not approved: approve it, or clear art_style.anchor"
    elif record.get("scope") != "style":
        result["problem"] = f"{label} was registered as a {record.get('scope')} mockup; a style anchor must be a style board (scope style)"
    else:
        path = (Path(root) / record.get("file", "")).resolve()
        approved = (Path(root) / ".gamearts" / "outputs" / "mockups" / "approved").resolve()
        if not inside(path, approved) or not path.is_file():
            result["problem"] = f"{label} has no approved image file in its place"
        elif sha256_file(path) != record.get("sha256"):
            result["problem"] = f"{label}: its image bytes differ from the approved record, so it cannot be used"
        else:
            result.update(path=path, sha256=record["sha256"])
    return result


# ----------------------------------------------------------------------------------------------- pixel policy
def load_rgba(path, label="image"):
    """Open an image as fully opaque RGBA; a transparent pixel anywhere is a contract violation."""
    from PIL import Image
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if image.getchannel("A").getextrema() != (255, 255):
        raise ValueError(f"{label} must be fully opaque; use a separate mask")
    return image


def _channel_distance(image):
    """Per-pixel Chebyshev distance from the exact key colour, as an 'L' image."""
    from PIL import Image, ImageChops
    rgb = image.convert("RGB")
    r, g, b = ImageChops.difference(rgb, Image.new("RGB", rgb.size, KEY_RGB)).split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


def nonkey_mask(image):
    """'L' mask, 255 wherever a pixel is not exactly #FF00FF."""
    return _channel_distance(image).point(lambda v: 255 if v else 0)


def near_key_mask(image, tolerance=NEAR_KEY_TOLERANCE):
    """'L' mask, 255 where a pixel is close to, but not exactly, the key colour (blend fringe or contamination)."""
    return _channel_distance(image).point(lambda v, t=tolerance: 255 if 0 < v <= t else 0)


def diff_mask(a, b, tolerance=0):
    """'L' mask, 255 wherever two same-size images differ by more than `tolerance` in any RGBA channel."""
    from PIL import ImageChops
    r, g, b_, a_ = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).split()
    worst = ImageChops.lighter(ImageChops.lighter(r, g), ImageChops.lighter(b_, a_))
    return worst.point(lambda v, t=tolerance: 255 if v > t else 0)


def ink_bbox(image):
    """Bounding box (left, top, right, bottom; exclusive) of every non-key pixel, or None when all key."""
    return nonkey_mask(image).getbbox()


def mask_count(mask):
    return mask.histogram()[255]


def rect_union_mask(size, rects):
    from PIL import Image
    mask = Image.new("L", size, 0)
    for x, y, w, h in rects:
        mask.paste(255, (x, y, x + w, y + h))
    return mask


def key_policy_report(image, frame_rects=None, tolerance=NEAR_KEY_TOLERANCE, allow_near_key=False, full_bleed=False):
    """Measure the exact-key contract. Frame rectangles bound the allowed art; everything outside must be exact key.

    `full_bleed` (terrain tiles, full-panel UI) allows art to fill the canvas, so only opacity and contamination apply.
    Returns counts plus an `issues` list; an empty list means the contract holds.
    """
    from PIL import ImageChops
    image = image.convert("RGBA")
    issues = []
    alpha = image.getchannel("A").getextrema()
    if alpha != (255, 255):
        issues.append(f"alpha not fully opaque: {alpha}")
    total = image.width * image.height
    nonkey = nonkey_mask(image)
    key_pixels = total - mask_count(nonkey)
    outside = 0
    if frame_rects is not None and not full_bleed:
        outside = mask_count(ImageChops.multiply(nonkey, ImageChops.invert(rect_union_mask(image.size, frame_rects))))
        if outside:
            issues.append(f"{outside} pixel(s) outside the declared frames are not exact {KEY_HEX}")
    near = 0 if allow_near_key else mask_count(near_key_mask(image, tolerance))
    if near:
        issues.append(f"{near} near-{KEY_HEX} pixel(s) within {tolerance} of the key (blend fringe or contamination)")
    return {"opaque": alpha == (255, 255), "key_pixels": key_pixels, "total_pixels": total,
            "outside_frames_non_key": outside, "near_key_pixels": near, "tolerance": tolerance, "issues": issues}
