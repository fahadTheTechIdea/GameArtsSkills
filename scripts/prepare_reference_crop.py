#!/usr/bin/env python3
"""Game Arts reference-image gate: prepare a real approved mockup crop and check receipts.

Agent workflow (run internally, not user-facing):
  python scripts/prepare_reference_crop.py prepare --game-root GAME --job JOB.json --output-dir CANDIDATE
  python scripts/prepare_reference_crop.py verify --packet CANDIDATE/reference.packet.json --receipt RECEIPT.json

A file-based receipt documents an agent-observed image-tool invocation; it is NOT
cryptographic proof of what the image provider actually saw. A human visual
comparison against the approved crop remains mandatory.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from PIL import Image

KEY = "#FF00FF"
CLASSES = {"static_structure", "fixed_machinery", "mobile_directional",
           "ui_presentation", "terrain", "prop", "effect"}
SLUG = re.compile(r"^[A-Za-z0-9_-]+$")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message):
    raise ValueError(message)


def inside(path, directory):
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def resolve_under(game_root, filename):
    path = Path(filename)
    return (game_root / path).resolve() if not path.is_absolute() else path.resolve()


def required_slug(value, label):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        fail(f"{label} must be a nonempty filename-safe ID")
    return value


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_approval_record(root, mockup_id, revision, source, source_hash):
    """Cross-check explicit approved lifecycle record, not just a job assertion."""
    manifest_path = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
    if not manifest_path.is_file():
        fail("Missing mockups.json lifecycle manifest; first register the explicitly approved mockup")
    manifest = read_json(manifest_path)
    if isinstance(manifest, list):
        entries = manifest
    elif isinstance(manifest, dict):
        entries = manifest.get("mockups", manifest.get("entries", []))
    else:
        entries = []
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
            if expected and str(expected).lower() != source_hash.lower():
                fail("Approved lifecycle record hash disagrees with actual image")
            return manifest_path
    fail("No matching explicitly approved mockup ID and revision in lifecycle manifest")


def prepare(game_root, job_file, out):
    root = game_root.resolve()
    job = read_json(job_file)
    if not isinstance(job, dict):
        fail("Reference job must be an object")
    asset = required_slug(job.get("asset_id"), "asset_id")
    cls = job.get("asset_class")
    if cls not in CLASSES:
        fail("asset_class must identify static/mobile/UI/terrain/prop/effect")
    mockup = job.get("approved_mockup", {})
    if not isinstance(mockup, dict) or mockup.get("approval_status") != "approved":
        fail("An exact explicitly approved mockup revision is required")
    mockup_id = required_slug(mockup.get("id"), "mockup ID")
    revision = required_slug(mockup.get("revision"), "mockup revision")
    source = resolve_under(root, mockup.get("file", ""))
    approved_root = root / ".gamearts" / "outputs" / "mockups" / "approved"
    if not inside(source, approved_root) or not source.is_file():
        fail("Approved source must be an existing managed file inside mockups/approved")
    if not mockup.get("sha256"):
        fail("Approved mockup record must include its source SHA256")
    source_hash = sha(source)
    if source_hash.lower() != str(mockup["sha256"]).lower():
        fail("Approved mockup image SHA256 differs from registered expected value")
    approval_manifest = validate_approval_record(root, mockup_id, revision, source, source_hash)
    settings_file = root / ".gamearts" / "project.json"
    if not settings_file.is_file():
        fail("Missing saved project settings; run conversational Game Arts project setup")
    settings = read_json(settings_file)
    style = settings.get("art_style", {})
    world = settings.get("world", {})
    if not isinstance(style, dict) or not style.get("id"):
        fail("Project art_style.id is missing")
    if not isinstance(world, dict) or not world.get("object_camera"):
        fail("Project world.object_camera is missing; confirm the selected game camera")
    if job.get("approved_camera") and job["approved_camera"] != world["object_camera"]:
        fail("Approved camera conflicts with project settings; resolve before generation")
    region = job.get("region", {})
    if not isinstance(region, dict):
        fail("region must specify a source-pixel crop rectangle")
    region_id = required_slug(region.get("id"), "region.id")
    rect = region.get("rect")
    if not isinstance(rect, list) or len(rect) != 4 or any(type(n) is not int for n in rect):
        fail("region.rect must be [x,y,width,height] integer source pixels")
    x, y, w, h = rect
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        fail("Crop region must have positive bounds")
    padding = region.get("padding_px", 0)
    if type(padding) is not int or padding < 0 or padding > 256:
        fail("padding_px must be an integer in 0..256")
    directions = job.get("directions")
    if directions is None:
        directions = ([world["object_camera"]] if cls in
                      {"static_structure", "fixed_machinery", "ui_presentation", "terrain", "prop", "effect"}
                      else settings.get("directions", []))
    if not isinstance(directions, list) or not directions or not all(
        isinstance(v, str) and v for v in directions
    ) or len(set(directions)) != len(directions):
        fail("Resolved directions must be nonempty and unique")
    if cls in {"static_structure", "fixed_machinery"} and len(directions) != 1:
        if job.get("rotation_policy") != "explicit_limited":
            fail("Fixed structures require ONE approved view unless placement rotation is explicitly approved")
    if cls == "mobile_directional" and len(directions) != 8 and job.get("rotation_policy") != "explicit_limited":
        fail("Free-facing mobile assets require 8 directions unless an approved limited profile applies")

    with Image.open(source) as image:
        sw, sh = image.size
        if x + w > sw or y + h > sh:
            fail(f"Crop {rect} exceeds approved source dimensions {sw}x{sh}")
        box = [max(0, x-padding), max(0, y-padding),
               min(sw, x+w+padding), min(sh, y+h+padding)]
        crop = image.convert("RGB").crop(tuple(box))
    detail = job.get("identity_lock", [])
    if not isinstance(detail, list) or not all(isinstance(v, str) for v in detail):
        fail("identity_lock must be a list of observed appearance constraints")
    rules = job.get("applicable_custom_instructions", [])
    if not isinstance(rules, list) or not all(isinstance(v, str) for v in rules):
        fail("applicable_custom_instructions must be an array of resolved instructions")
    if out.exists() and any(out.iterdir()):
        fail("Output folder is not empty; use a new descriptive candidate revision")
    out.mkdir(parents=True, exist_ok=True)
    crop_path = out / (asset + "_reference_crop.png")
    packet_path = out / "reference.packet.json"
    prompt_path = out / "reference.prompt.txt"
    if any(path.exists() for path in (crop_path, packet_path, prompt_path)):
        fail("Reference candidate already exists; do not overwrite")
    crop.save(crop_path)
    # IMPORTANT: this is the ORIGINAL reference crop; do not chroma-mask or alter
    # its source colors. Only generated game-art PNGs require opaque #FF00FF.
    style_desc = "; ".join(f"{key}={style[key]}" for key in (
        "id", "reference", "palette_reference", "outline_policy",
        "shading_policy", "texture_policy", "pixel_density") if style.get(key))
    prompt = "\n".join([
        f"TASK: Produce exactly ONE {cls} master candidate for {asset}; not a sprite sheet.",
        f"MANDATORY IMAGE INPUT: Attach the actual image file: {crop_path.resolve()}",
        f"APPROVED SOURCE: mockup {mockup_id}, revision {revision}; region {region_id}; sha256 {source_hash}.",
        f"STYLE FROM SAVED GAME SETTINGS: {style_desc}.",
        f"EXACT CAMERA FROM SAVED GAME SETTINGS: {world['object_camera']}.",
        f"ALLOWED VIEWS/DIRECTIONS: {', '.join(directions)}.",
        f"GAME SCALE: {world.get('pixels_per_meter', 'unspecified')} world pixels/meter (subject to approved asset profile).",
        "IDENTITY LOCK — observed visible features: " + ("; ".join(detail) or "preserve all visible details from the image"),
        "CUSTOM INSTRUCTIONS: " + ("; ".join(rules) or "none applicable"),
        "Use the ATTACHED crop as the authority, not a generic style description.",
        "Do not alter viewpoint, object identity, proportions or previously approved features.",
        "Do not invent hidden wall details without design approval.",
        "No multi-view contact sheets, alternate camera, labels, UI, frames, or printed JSON.",
        f"FINAL ART EXPORT: solid opaque {KEY} background, no transparency; real PNG output.",
        "If the image tool cannot accept the reference image as input, STOP: reference fidelity cannot be verified.",
    ]) + "\n"
    packet = {
        "schema_version": "1.0",
        "asset_id": asset,
        "asset_class": cls,
        "approved_mockup": {"id": mockup_id, "revision": revision,
                            "image": str(source), "sha256": source_hash,
                            "lifecycle_manifest": str(approval_manifest),
                            "lifecycle_manifest_sha256": sha(approval_manifest)},
        "region": {"id": region_id, "rect": rect, "actual_crop_box": box},
        "source_image_size": [sw, sh],
        "reference_crop": str(crop_path.resolve()),
        "reference_crop_size": list(crop.size),
        "reference_crop_sha256": sha(crop_path),
        "settings_file": str(settings_file.resolve()),
        "settings_sha256": sha(settings_file),
        "resolved_style": style,
        "resolved_camera": world["object_camera"],
        "resolved_directions": directions,
        "identity_lock": detail,
        "applicable_custom_instructions": rules,
        "prompt_path": str(prompt_path.resolve()),
        "conditioning_status": "prepared_not_attached",
        "visual_review": "pending",
        "production_approval": "not_granted"
    }
    packet_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    prompt_path.write_text(prompt, encoding="utf-8")
    return packet_path


def verify(packet_file, receipt_file):
    packet = read_json(packet_file)
    if not isinstance(packet, dict):
        fail("Invalid reference packet")
    crop_path = Path(packet["reference_crop"])
    settings_file = Path(packet["settings_file"])
    original = Path(packet["approved_mockup"]["image"])
    for path, expected in (
        (crop_path, packet["reference_crop_sha256"]),
        (settings_file, packet["settings_sha256"]),
        (original, packet["approved_mockup"]["sha256"]),
        (Path(packet["approved_mockup"]["lifecycle_manifest"]),
         packet["approved_mockup"]["lifecycle_manifest_sha256"])
    ):
        if not path.is_file() or sha(path).lower() != str(expected).lower():
            fail(f"File or SHA256 changed since preparation: {path}")
    if not receipt_file.is_file():
        fail("No actual image-tool attachment receipt; cannot claim conditioned production")
    receipt = read_json(receipt_file)
    if not isinstance(receipt, dict):
        fail("Invalid tool receipt")
    if receipt.get("reference_crop_sha256") != packet["reference_crop_sha256"]:
        fail("Attached reference does not match prepared approved crop")
    if receipt.get("reference_image_path") != packet["reference_crop"]:
        fail("Tool receipt did not reference the actual prepared crop path")
    if receipt.get("image_input_attached") is not True:
        fail("Image input was not attached to tool call; text prompt alone is insufficient")
    if not isinstance(receipt.get("tool_invocation_id"), str) or not receipt["tool_invocation_id"]:
        fail("Tool invocation ID must be captured from actual image-tool result")
    candidate = Path(receipt.get("candidate_image", ""))
    if not candidate.is_file() or candidate.suffix.lower() != ".png":
        fail("Missing PNG candidate produced by the referenced image-tool call")
    if sha(candidate) != receipt.get("candidate_sha256"):
        fail("Candidate image hash differs from tool receipt")
    with Image.open(candidate) as image:
        rgba = image.convert("RGBA")
        if rgba.getchannel("A").getextrema() != (255, 255):
            fail("Generated candidate has transparency instead of opaque source pixels")
        # An empty corner should have the solid export key. This cannot prove
        # all exterior pixels or edge coverage and must not pass artistic review.
        if any(rgba.getpixel(pt) != (255, 0, 255, 255) for pt in (
            (0, 0), (rgba.width-1, 0), (0, rgba.height-1),
            (rgba.width-1, rgba.height-1))):
            fail("Generated candidate corners are not exact opaque #FF00FF")
    return {
        "file_integrity": "passed",
        "agent_reported_reference_attachment": "recorded_not_independently_proven",
        "visual_match_to_mockup": "not_verified",
        "status": "candidate_pending_visual_review",
        "message": "A self-recorded receipt cannot prove provider-side image conditioning."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--game-root", type=Path, required=True)
    p.add_argument("--job", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--packet", type=Path, required=True)
    v.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print("PREPARED", prepare(args.game_root, args.job, args.output_dir))
            print("Image tool must receive the actual reference crop as image input.")
        else:
            print(json.dumps(verify(args.packet, args.receipt), indent=2))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as err:
        parser.exit(1, f"BLOCKED: {err}\n")


if __name__ == "__main__":
    main()
