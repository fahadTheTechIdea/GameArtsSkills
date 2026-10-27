#!/usr/bin/env python3
"""Game Arts reference-image gate: prepare a real approved-mockup crop and check image-tool receipts.

Agent workflow (run internally, not user-facing):
  python scripts/prepare_reference_crop.py prepare --game-root GAME --job JOB.json --output-dir CANDIDATE
  python scripts/prepare_reference_crop.py verify --packet CANDIDATE/reference.packet.json --receipt RECEIPT.json [--game-root GAME]

Packet paths are relative (the crop to the packet folder, project files to the game root), so a candidate keeps verifying
after it moves from generated to approved or to another machine. A file-based receipt documents an agent-observed
image-tool invocation; it is NOT cryptographic proof of what the image provider saw. A human visual comparison against the
approved crop remains mandatory.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

import gamearts_common as common  # noqa: E402
import gamearts_presets as presets  # noqa: E402

# Asset classes by the camera they follow. The reference-job and reference-packet schemas list exactly their union (a test keeps them equal).
SCREEN_CLASSES = {"ui_presentation", "icon_set", "card_layer_set", "portrait_set"}  # screen space: the UI camera
GROUND_CLASSES = {"terrain", "tileset"}  # the ground grid: the ground camera
OBJECT_CLASSES = {"static_structure", "fixed_machinery", "mobile_directional", "prop", "parallax_layer"}  # the world object camera
EITHER_CLASSES = {"effect"}  # the object camera where the game has a ground world, otherwise the UI camera
CLASSES = SCREEN_CLASSES | GROUND_CLASSES | OBJECT_CLASSES | EITHER_CLASSES
FULL_BLEED = {"terrain", "ui_presentation", "tileset", "parallax_layer", "card_layer_set"}  # art may fill the canvas (no key background required)
ANCHOR_COPY = "style_anchor.png"  # the approved style board, copied beside the crop
MIN_KEY_FRACTION = 0.01  # a key-background candidate must contain at least this share of exact #FF00FF pixels


def fail(message):
    raise ValueError(message)


def rel(root, path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def resolve_under(game_root, filename):
    path = Path(filename)
    return (game_root / path).resolve() if not path.is_absolute() else path.resolve()


def required_id(value, label, pattern):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        fail(f"{label} must be a nonempty filename-safe ID")
    return value


def find_game_root(start):
    for folder in [Path(start).resolve(), *Path(start).resolve().parents]:
        if (folder / ".gamearts").is_dir():
            return folder
    fail("Cannot locate the game root (no .gamearts folder above the packet); pass --game-root")


def validate_approval_record(root, mockup_id, revision, source, source_hash):
    """Cross-check the explicit approved lifecycle record, not just a job assertion."""
    manifest_path = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
    if not manifest_path.is_file():
        fail("Missing mockups.json lifecycle manifest; first register the explicitly approved mockup")
    manifest = common.read_json(manifest_path)
    entries = manifest if isinstance(manifest, list) else manifest.get("mockups", manifest.get("entries", [])) if isinstance(manifest, dict) else []
    if not isinstance(entries, list):
        fail("Approved mockup manifest must contain a list of records")
    for record in entries:
        if not isinstance(record, dict):
            continue
        rid = record.get("mockup_id", record.get("id"))
        rev = record.get("revision", record.get("mockup_revision"))
        state = record.get("status", record.get("approval_status"))
        loc = record.get("file", record.get("path", record.get("approved_reference_file")))
        expected = record.get("sha256", record.get("source_sha256"))
        if rid == mockup_id and rev == revision and state == "approved":
            if not loc or resolve_under(root, loc) != source:
                fail("Approved lifecycle record points to a different source image")
            if not expected:
                fail("Approved lifecycle record lacks source SHA256; compute it from the actual approved image before cropping")
            if str(expected).lower() != source_hash.lower():
                fail("Approved lifecycle record hash disagrees with actual image")
            return manifest_path
    fail("No matching explicitly approved mockup ID and revision in lifecycle manifest")


def scale_sentence(world, screen):
    """The scale line of the prompt: world pixels per metre where the game has a ground world, and the screen's base resolution when stated."""
    if world:
        text = f"GAME SCALE: {world.get('pixels_per_meter', 'unspecified')} world pixels/meter when applicable; UI is in screen pixels."
    else:
        text = "GAME SCALE: this game has no ground world; art is in screen pixels."
    if screen:
        width, height = screen["base_resolution_px"]
        text += f" Screen base resolution: {width}x{height} px."
    return text


def export_sentence(cls):
    if cls in FULL_BLEED:
        return ("FINAL ART EXPORT: opaque PNG, no transparency. This class fills its canvas, so painted art may cover it "
                f"entirely; any unused pixels must still be exactly {common.KEY_HEX}.")
    return f"FINAL ART EXPORT: solid opaque {common.KEY_HEX} background, no transparency; real PNG output."


def prepare(game_root, job_file, out):
    root = Path(game_root).resolve()
    job = common.read_json(job_file)
    if not isinstance(job, dict):
        fail("Reference job must be an object")
    common.validate_schema(job, "gamearts-reference-job")
    asset = required_id(job["asset_id"], "asset_id", common.SLUG)
    cls = job["asset_class"]
    mockup = job["approved_mockup"]
    mockup_id = required_id(mockup.get("id"), "mockup ID", common.MOCKUP_ID)
    revision = required_id(mockup.get("revision"), "mockup revision", common.REVISION)
    source = resolve_under(root, mockup.get("file", ""))
    approved_root = root / ".gamearts" / "outputs" / "mockups" / "approved"
    if not common.inside(source, approved_root) or not source.is_file():
        fail("Approved source must be an existing managed file inside mockups/approved")
    source_hash = common.sha256_file(source)
    if source_hash.lower() != str(mockup["sha256"]).lower():
        fail("Approved mockup image SHA256 differs from registered expected value")
    approval_manifest = validate_approval_record(root, mockup_id, revision, source, source_hash)
    settings, _, _ = common.load_project_settings(root)
    style, world, kind = settings["art_style"], settings.get("world") or {}, common.world_kind(settings)
    # Screen-space art follows the UI camera and terrain follows the ground grid: neither inherits the world object camera.
    # A game with no ground world has no object or ground camera at all, so it can only make screen-space art.
    if cls in SCREEN_CLASSES or (cls in EITHER_CLASSES and kind == "screen_space"):
        configured_camera = style.get("ui_camera")
        camera = configured_camera or job.get("approved_camera") or "approved_ui_reference"
    elif kind == "screen_space":
        fail(f"This game is screen_space (it has no ground world), so {cls} art does not apply; "
             f"make {', '.join(sorted(SCREEN_CLASSES | EITHER_CLASSES))} art, or change the game's world kind first")
    elif cls == "tileset" and kind != "grid_world":
        fail(f"A tileset needs a tile grid and this game is {kind}; use terrain or prop art, or change the game's world kind first")
    elif cls in GROUND_CLASSES:
        configured_camera = world.get("ground_camera")
        camera = configured_camera or job.get("approved_camera") or "orthogonal_ground_grid"
    else:
        configured_camera = world.get("object_camera")
        camera = configured_camera or job.get("approved_camera")
        if not camera:
            fail("Selected world camera missing; confirm project camera or approved asset view")
    if job.get("approved_camera") and configured_camera and job["approved_camera"] != configured_camera:
        fail("Approved camera conflicts with project settings; resolve before generation")
    region = job["region"]
    region_id = required_id(region["id"], "region.id", common.SLUG)
    rect = region["rect"]
    x, y, w, h = rect
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        fail("Crop region must have positive bounds")
    padding = region.get("padding_px", 0)
    project_directions = common.resolve_directions(settings)
    directions = job.get("directions")
    if directions is None:
        directions = project_directions if cls == "mobile_directional" else ["ui"] if cls in SCREEN_CLASSES \
            else ["tile"] if cls in GROUND_CLASSES else ["layer"] if cls == "parallax_layer" else ["fixed"]
    if not directions or not all(isinstance(v, str) and v for v in directions) or len(set(directions)) != len(directions):
        fail("Resolved directions must be nonempty and unique")
    if cls in {"static_structure", "fixed_machinery"} and len(directions) != 1 and job.get("rotation_policy") != "explicit_limited":
        fail("Fixed structures require ONE approved view unless placement rotation is explicitly approved")
    if cls == "mobile_directional" and job.get("rotation_policy") != "explicit_limited" \
            and (len(directions) != len(project_directions) or set(directions) != set(project_directions)):
        fail(f"Free-facing mobile assets require {len(project_directions)} directions ({', '.join(project_directions)}) "
             "unless an approved limited profile applies")
    with Image.open(source) as image:
        sw, sh = image.size
        if x + w > sw or y + h > sh:
            fail(f"Crop {rect} exceeds approved source dimensions {sw}x{sh}")
        box = [max(0, x - padding), max(0, y - padding), min(sw, x + w + padding), min(sh, y + h + padding)]
        crop = image.convert("RGB").crop(tuple(box))
    detail = job.get("identity_lock", [])
    rules = job.get("applicable_custom_instructions", [])
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        fail("Output folder is not empty; use a new descriptive candidate revision")
    out.mkdir(parents=True, exist_ok=True)
    crop_path, packet_path, prompt_path = out / (asset + "_reference_crop.png"), out / "reference.packet.json", out / "reference.prompt.txt"
    crop.save(crop_path)  # the ORIGINAL crop: never chroma-masked; only generated game-art PNGs use the key background
    style_desc = "; ".join(f"{key}={style[key]}" for key in (
        "id", "reference", "palette_reference", "outline_policy", "shading_policy", "texture_policy", "pixel_density") if style.get(key))
    anchor = common.resolve_style_anchor(root, settings)
    if anchor is not None and anchor["problem"]:
        fail(anchor["problem"])
    anchor_lines = []
    if anchor is not None:
        anchor_copy = out / ANCHOR_COPY
        shutil.copyfile(anchor["path"], anchor_copy)  # a byte-for-byte copy, so the image tool receives both references from one folder
        anchor_lines = [f"STYLE ANCHOR (second reference image): also attach {ANCHOR_COPY}, the approved style board of this game "
                        f"(mockup {anchor['id']} {anchor['revision']}). Match its palette, outline weight, shading and rendering; "
                        "never copy its subjects or composition."]
    preset = presets.resolve_style_preset(settings)
    avoid = []
    if preset and preset["found"]:
        avoid = [f"AVOID (from the saved style preset {preset['preset']}): " + " ".join(preset["avoid"])]
    elif preset and preset.get("problem"):
        fail(f"The saved style preset cannot be read: {preset['problem']}")
    prompt = "\n".join([
        f"TASK: Produce exactly ONE {cls} master candidate for {asset}; not a sprite sheet.",
        f"MANDATORY IMAGE INPUT: Attach the actual image file {crop_path.name} that sits beside this prompt file.",
        f"APPROVED SOURCE: mockup {mockup_id}, revision {revision}; region {region_id}; sha256 {source_hash}.",
        f"STYLE FROM SAVED GAME SETTINGS: {style_desc}.",
        *avoid,
        *anchor_lines,
        f"RESOLVED CAMERA FROM SELECTED GAME SETTINGS / APPROVED REFERENCE: {camera}.",
        f"ALLOWED VIEWS/DIRECTIONS: {', '.join(directions)}.",
        scale_sentence(world, settings.get("screen")),
        "IDENTITY LOCK — observed visible features: " + ("; ".join(detail) or "preserve all visible details from the image"),
        "CUSTOM INSTRUCTIONS: " + ("; ".join(rules) or "none applicable"),
        "Use the ATTACHED crop as the authority, not a generic style description.",
        "Do not alter viewpoint, object identity, proportions or previously approved features.",
        "Do not invent hidden wall details without design approval.",
        "No multi-view contact sheets, alternate camera, labels, UI, frames, or printed JSON.",
        export_sentence(cls),
        "If the image tool cannot accept the reference image as input, STOP: reference fidelity cannot be verified.",
    ]) + "\n"
    packet = {
        "schema_version": "1.0", "asset_id": asset, "asset_class": cls,
        "approved_mockup": {"id": mockup_id, "revision": revision, "image": rel(root, source), "sha256": source_hash,
                            "lifecycle_manifest": rel(root, approval_manifest),
                            "lifecycle_manifest_sha256": common.sha256_file(approval_manifest)},
        "region": {"id": region_id, "rect": rect, "actual_crop_box": box}, "source_image_size": [sw, sh],
        "reference_crop": crop_path.name, "reference_crop_size": list(crop.size), "reference_crop_sha256": common.sha256_file(crop_path),
        "settings_file": ".gamearts/project.json", "settings_sha256": common.sha256_file(root / ".gamearts" / "project.json"),
        "resolved_style": style, "resolved_camera": camera, "resolved_directions": directions,
        "export_rule": "full_bleed" if cls in FULL_BLEED else "key_background",
        "identity_lock": detail, "applicable_custom_instructions": rules, "prompt_path": prompt_path.name,
        "conditioning_status": "prepared_not_attached", "visual_review": "pending", "production_approval": "not_granted"}
    if anchor is not None:
        packet["style_anchor"] = {"id": anchor["id"], "revision": anchor["revision"], "image": ANCHOR_COPY,
                                  "sha256": common.sha256_file(anchor_copy), "source_image": rel(root, anchor["path"])}
    common.validate_schema(packet, "gamearts-reference-packet")
    common.atomic_write_json(packet_path, packet)
    prompt_path.write_text(prompt, encoding="utf-8")
    return packet_path


def verify_style_anchor(packet, packet_file, root, receipt):
    """Whether the packet's style anchor is intact and whether the image tool received it. Returns (state, note); the state is
    `not_set`, `attached` or `not_attached`. A changed anchor file is an error; an anchor the tool did not receive is reported."""
    anchor = packet.get("style_anchor")
    if not anchor:
        return "not_set", None
    for path, expected in ((Path(packet_file).parent / anchor["image"], anchor["sha256"]),
                           (root / anchor.get("source_image", ""), anchor["sha256"])):
        if not path.is_file() or common.sha256_file(path).lower() != str(expected).lower():
            fail(f"File or SHA256 changed since preparation: {path.name}")
    if receipt.get("style_anchor_attached") is True:
        return "attached", None
    return "not_attached", ("The style anchor was not passed to the image tool, so the candidate must be compared with the anchor by eye "
                            "before it is trusted to match the game's look.")


def verify(packet_file, receipt_file, game_root=None):
    packet_file = Path(packet_file).resolve()
    packet = common.read_json(packet_file)
    common.validate_schema(packet, "gamearts-reference-packet")
    root = Path(game_root).resolve() if game_root else find_game_root(packet_file.parent)
    crop_path = packet_file.parent / packet["reference_crop"]
    mockup = packet["approved_mockup"]
    for path, expected in ((crop_path, packet["reference_crop_sha256"]), (root / packet["settings_file"], packet["settings_sha256"]),
                           (root / mockup["image"], mockup["sha256"]),
                           (root / mockup["lifecycle_manifest"], mockup["lifecycle_manifest_sha256"])):
        if not path.is_file() or common.sha256_file(path).lower() != str(expected).lower():
            fail(f"File or SHA256 changed since preparation: {path.name}")
    receipt_file = Path(receipt_file)
    if not receipt_file.is_file():
        fail("No actual image-tool attachment receipt; cannot claim conditioned production")
    receipt = common.read_json(receipt_file)
    common.validate_schema(receipt, "gamearts-reference-receipt")
    if receipt.get("reference_crop_sha256") != packet["reference_crop_sha256"]:
        fail("Attached reference does not match prepared approved crop")
    attached = receipt.get("reference_image_path", "")
    if attached != packet["reference_crop"] and resolve_under(packet_file.parent, attached) != crop_path.resolve():
        fail("Tool receipt did not reference the actual prepared crop path")
    if receipt.get("image_input_attached") is not True:
        fail("Image input was not attached to tool call; text prompt alone is insufficient")
    if not isinstance(receipt.get("tool_invocation_id"), str) or not receipt["tool_invocation_id"]:
        fail("Tool invocation ID must be captured from actual image-tool result")
    candidate = resolve_under(packet_file.parent, receipt.get("candidate_image", ""))
    if not candidate.is_file() or candidate.suffix.lower() != ".png":
        fail("Missing PNG candidate produced by the referenced image-tool call")
    if common.sha256_file(candidate) != receipt.get("candidate_sha256"):
        fail("Candidate image hash differs from tool receipt")
    image = common.load_rgba(candidate, "Generated candidate")
    report = common.key_policy_report(image)
    if report["near_key_pixels"]:
        fail(f"Generated candidate has {report['near_key_pixels']} near-{common.KEY_HEX} pixels (blend fringe or contamination)")
    full_bleed = packet.get("export_rule") == "full_bleed"
    if not full_bleed and report["key_pixels"] < MIN_KEY_FRACTION * report["total_pixels"]:
        fail(f"Generated candidate lacks the exact {common.KEY_HEX} background (under {MIN_KEY_FRACTION:.0%} key pixels)")
    anchor_state, anchor_note = verify_style_anchor(packet, packet_file, root, receipt)
    return {"file_integrity": "passed", "export_rule": packet.get("export_rule", "key_background"), "style_anchor": anchor_state,
            **({"style_anchor_note": anchor_note} if anchor_note else {}),
            "agent_reported_reference_attachment": "recorded_not_independently_proven", "visual_match_to_mockup": "not_verified",
            "status": "candidate_pending_visual_review",
            "message": "A self-recorded receipt cannot prove provider-side image conditioning."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--game-root", type=Path, required=True)
    p.add_argument("--job", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, help="Candidate reference folder; defaults to .gamearts/outputs/assets/generated/<asset_id>/reference")
    v = sub.add_parser("verify")
    v.add_argument("--packet", type=Path, required=True)
    v.add_argument("--receipt", type=Path, required=True)
    v.add_argument("--game-root", type=Path, help="Defaults to the nearest folder above the packet that holds .gamearts")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            job = common.read_json(args.job)
            default = args.game_root / ".gamearts" / "outputs" / "assets" / "generated" / str(job.get("asset_id", "candidate")) / "reference"
            print("PREPARED", prepare(args.game_root, args.job, args.output_dir or default))
            print("Image tool must receive the actual reference crop as image input.")
        else:
            import json
            print(json.dumps(verify(args.packet, args.receipt, args.game_root), indent=2))
    except (OSError, ValueError, TypeError, KeyError) as err:  # ValueError covers JSON and contract errors
        parser.exit(1, f"BLOCKED: {err}\n")


if __name__ == "__main__":
    main()
