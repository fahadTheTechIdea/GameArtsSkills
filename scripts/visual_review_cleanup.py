#!/usr/bin/env python3
"""Produce inspectable Game Arts extraction boards and bind a user decision to exact file hashes.

prepare --cleanup cleanup.json --review-spec spec.json --output-dir review/
verify  --packet review/visual_review.packet.json --decision review/decision.json

This DOES NOT visually recognize objects or independently attest a user message. An agent must display both boards,
obtain real user approval, then write the decision. Approved original assets are never silently modified.
Review-spec contract: schemas/gamearts-review-spec.schema.json.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageChops, ImageDraw, ImageFont  # noqa: E402

import gamearts_common as common  # noqa: E402
from validate_parent_cleanup import checked_report, mask_image  # noqa: E402


def asset(path, ref, desc):
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"Missing {desc} file")
    p = common.safe_member(Path(path).parent, ref, desc)
    if not p.is_file():
        raise ValueError(f"Missing {desc}: {p}")
    return p


def checker(size, tile=12):
    canvas = Image.new("RGB", size, (239, 239, 237))
    painter = ImageDraw.Draw(canvas)
    w, h = size
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if (x // tile + y // tile) % 2 == 0:
                painter.rectangle((x, y, min(w - 1, x + tile - 1), min(h - 1, y + tile - 1)), fill=(207, 209, 210))
    return canvas


def fit(image, size, method=Image.Resampling.NEAREST):
    w, h = image.size
    scale = min(size[0] / w, size[1] / h)
    return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), method)


def matte(image):
    image = image.convert("RGBA")
    background = checker(image.size).convert("RGBA")
    background.paste(image, (0, 0), common.nonkey_mask(image))
    return background.convert("RGB")


def panel_board(panels, cols=3, panel=(330, 275), method=Image.Resampling.NEAREST):
    margin, label_h = 12, 34
    rows = math.ceil(len(panels) / cols)
    cell_w, cell_h = panel[0] + 2 * margin, panel[1] + label_h + 2 * margin
    board = Image.new("RGB", (cols * cell_w, rows * cell_h), (245, 241, 230))
    painter = ImageDraw.Draw(board)
    font = ImageFont.load_default()
    for i, (title, image) in enumerate(panels):
        x, y = i % cols * cell_w + margin, i // cols * cell_h + margin
        painter.rectangle((x - 3, y - 3, x + panel[0] + 3, y + panel[1] + label_h + 3), outline=(68, 69, 71), width=2)
        art = fit(image.convert("RGB"), panel, method)
        board.paste(art, (x + (panel[0] - art.width) // 2, y + (panel[1] - art.height) // 2))
        painter.text((x + 4, y + panel[1] + 6), title[:47], fill=(20, 20, 20), font=font)
    return board


def overlay(image, mask, color, strength=0.35):
    base = image.convert("RGB")
    mixed = Image.blend(base, Image.new("RGB", image.size, color), strength)
    return Image.composite(mixed, base, mask)


def rel(base, target):
    return os.path.relpath(str(target), str(base))


def prepare(cleanup_file, review_spec_file, output_dir):
    cleanup_file, review_spec_file, output_dir = (Path(p).resolve() for p in (cleanup_file, review_spec_file, output_dir))
    manifest, spec = common.read_json(cleanup_file), common.read_json(review_spec_file)
    if not isinstance(manifest, dict) or not isinstance(spec, dict):
        raise ValueError("Expected cleanup manifest and review specification objects")
    common.validate_schema(spec, "gamearts-review-spec")
    # Hard requirement: independent clean-plate review, actual parent removal and independently approved
    # sprite-local silhouettes with a proven source tie must pass before a human is asked to look.
    technical = checked_report(cleanup_file, strict_props=True)
    if technical["technical_status"] != "passed":
        raise ValueError("Strict parent cleanup gate failed: " + "; ".join(technical["failures"]))
    parts = manifest["detached_components"]
    ids = [p["id"] for p in parts]
    expected = spec["expected_component_ids"]
    if len(expected) != len(ids) or set(expected) != set(ids):
        raise ValueError("Review inventory must exactly match separated component IDs")
    reference = spec["approved_reference"]
    approved_reference_file = asset(review_spec_file, reference["file"], "approved mockup reference crop")
    if common.sha256_file(approved_reference_file) != reference["sha256"]:
        raise ValueError("Approved mockup reference crop hash differs from registered source")
    # A crop path + claimed mockup ID by themselves are not proof the crop came from the approved source: bind it to the
    # reference packet the crop gate wrote (the packet's crop is named relative to the packet's own folder).
    crop_packet_file = asset(review_spec_file, reference["crop_packet"], "approved reference preparation packet")
    crop_packet = common.read_json(crop_packet_file)
    original_meta = crop_packet.get("approved_mockup", {})
    packet_crop = (crop_packet_file.parent / str(crop_packet.get("reference_crop", ""))).resolve()
    if (original_meta.get("id") != reference["mockup_id"] or original_meta.get("revision") != reference["mockup_revision"]
            or crop_packet.get("reference_crop_sha256") != reference["sha256"] or packet_crop != approved_reference_file):
        raise ValueError("Approved crop provenance differs from prepared reference packet")
    if not isinstance(original_meta.get("sha256"), str) or not original_meta["sha256"]:
        raise ValueError("Prepared crop packet lacks approved mockup source hash")
    approved_reference_art = common.load_rgba(approved_reference_file, "approved reference crop")
    identity, revision = spec["asset_id"], spec["revision"]
    uncertain = spec["uncertain_regions"]
    original_file = asset(cleanup_file, manifest["source_composite"], "original composite")
    parent_file = asset(cleanup_file, manifest["static_parent"], "cleaned parent")
    plate_file = asset(cleanup_file, manifest["clean_plate"], "clean background plate")
    original, parent, plate = (common.load_rgba(p, n) for p, n in ((original_file, "original"), (parent_file, "parent"), (plate_file, "plate")))
    if not (original.size == parent.size == plate.size):
        raise ValueError("Review requires aligned original/clean/plate raster sizes")
    size = original.size
    changed = common.diff_mask(original, parent)
    mask_union = Image.new("L", size, 0)
    dependencies = [cleanup_file, review_spec_file, original_file, parent_file, plate_file, approved_reference_file, crop_packet_file]
    prop_panels, bounds = [], {}
    for part in parts:
        ident = part["id"]
        removal_file = asset(cleanup_file, part["removal_mask"], ident + " removal mask")
        sprite_file = asset(cleanup_file, part["sprite"], ident + " sprite")
        stencil_file = asset(cleanup_file, part.get("sprite_silhouette_mask"), ident + " independent silhouette mask")
        removal = mask_image(removal_file, size, ident + " removal mask")
        sprite = common.load_rgba(sprite_file, ident + " sprite")
        stencil = mask_image(stencil_file, sprite.size, ident + " independent silhouette mask")
        if stencil.getbbox() is None or removal.getbbox() is None:
            raise ValueError(f"{ident}: empty ownership/silhouette mask")
        if ImageChops.multiply(mask_union, removal).getbbox() is not None:
            raise ValueError(f"Overlapping removal masks for {ident}")
        mask_union = ImageChops.lighter(mask_union, removal)
        bounds[ident] = list(removal.getbbox())
        if ImageChops.multiply(changed, removal).getbbox() is None:
            raise ValueError(f"{ident}: detached sprite exists but object still painted in parent")
        if ImageChops.difference(common.nonkey_mask(sprite), stencil).getbbox():
            raise ValueError(f"{ident}: independent silhouette mask differs from sprite pixels")
        prop_panels.extend([(ident + " / original context", original.crop(removal.getbbox()).convert("RGB")),
                            (ident + " / isolated sprite", matte(sprite))])
        dependencies.extend([removal_file, sprite_file, stencil_file])
    # Geometric clean-parent proof is only a precondition for human visual review.
    outside_changed = common.mask_count(ImageChops.multiply(changed, ImageChops.invert(mask_union)))
    inside_unrestored = common.mask_count(ImageChops.multiply(common.diff_mask(parent, plate), mask_union))
    if outside_changed or inside_unrestored:
        raise ValueError(f"Clean parent pixel test failed: {outside_changed} outside changes, {inside_unrestored} unrecovered interior pixels")
    uncertain_union, uncertain_ids = Image.new("L", size, 0), []
    for record in uncertain:
        if record["id"] in uncertain_ids:
            raise ValueError("Duplicate uncertain region ID")
        unknown_file = asset(review_spec_file, record["mask"], "uncertainty mask")
        unknown_mask = mask_image(unknown_file, size, "uncertainty mask")
        if unknown_mask.getbbox() is None:
            raise ValueError(f"{record['id']}: empty uncertainty region")
        uncertain_union = ImageChops.lighter(uncertain_union, unknown_mask)
        dependencies.append(unknown_file)
        uncertain_ids.append(record["id"])
    panels = [("0 / Approved original mockup crop", approved_reference_art), ("A / Original reference composite", original),
              ("B / Static parent after cleanup", parent), ("C / Proposed clean background plate", plate),
              ("D / Removal regions in original", overlay(original, mask_union, (233, 80, 24))),
              ("E / Hidden/reconstructed areas", overlay(parent, uncertain_union, (238, 185, 37), .68)),
              ("F / Changed pixels marked blue", overlay(original, changed, (72, 140, 210)))]
    # All review evidence must come from the CURRENT candidate: no hidden revoked dependency, and the relative hashes stay
    # valid when the complete bundle later moves from generated to approved.
    candidate_root = output_dir.parent
    if not all(common.inside(path, candidate_root) for path in dependencies):
        raise ValueError("Visual review depends on files outside current asset candidate")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("Review output exists; use another candidate or revision")
    output_dir.mkdir(parents=True, exist_ok=True)
    main_board, prop_board, packet_file = output_dir / "visual_review_board.png", output_dir / "visual_review_props.png", output_dir / "visual_review.packet.json"
    art_style = spec.get("art_style_id", manifest.get("art_style_id", "custom"))
    resampling = Image.Resampling.NEAREST if art_style == "pixel_art" else Image.Resampling.LANCZOS
    panel_board(panels, method=resampling).save(main_board)
    panel_board(prop_panels, cols=2, panel=(285, 220), method=resampling).save(prop_board)
    packet = {
        "schema_version": "1.0", "type": "gamearts-visual-acceptance", "asset_id": identity, "revision": revision,
        "review_status": "pending_user_visual_review", "cleanup_manifest": rel(output_dir, cleanup_file),
        "review_spec": rel(output_dir, review_spec_file),
        "approved_reference": {"mockup_id": reference["mockup_id"], "revision": reference["mockup_revision"],
                               "path": rel(output_dir, approved_reference_file), "sha256": reference["sha256"],
                               "source_sha256": original_meta["sha256"], "crop_packet": rel(output_dir, crop_packet_file)},
        "source_files": [{"path": rel(output_dir, path), "sha256": common.sha256_file(path)} for path in sorted(set(dependencies))],
        "art_style_id": art_style,
        "review_board": {"path": main_board.name, "sha256": common.sha256_file(main_board)},
        "props_board": {"path": prop_board.name, "sha256": common.sha256_file(prop_board)},
        "component_ids": sorted(ids), "object_source_bounds": bounds, "uncertain_region_ids": sorted(uncertain_ids),
        "review_criteria": ["all separable objects inventoried", "correct object-shaped cutouts",
                            "no detached object remains baked into static parent", "reconstructed background looks plausible",
                            "approved style, camera and proportions preserved"],
        "semantic_object_verification": "requires_human_review", "background_plausibility": "requires_human_review",
        "engine_validation": "not_tested"}
    common.atomic_write_json(packet_file, packet)
    return packet_file


def verify(packet_file, decision_file):
    packet_file = Path(packet_file).resolve()
    packet = common.read_json(packet_file)
    if packet.get("type") != "gamearts-visual-acceptance" or packet.get("review_status") != "pending_user_visual_review":
        raise ValueError("Invalid or modified review packet")
    common.validate_schema(packet, "gamearts-review-packet")
    root = packet_file.parent
    for item in packet.get("source_files", []):
        path = (root / item["path"]).resolve()
        if not common.inside(path, root.parent):
            raise ValueError("Review source path escapes approved candidate bundle")
        if not path.is_file() or common.sha256_file(path) != item["sha256"]:
            raise ValueError("Review source file changed after presentation: " + str(item.get("path")))
    for field in ("review_board", "props_board"):
        item = packet[field]
        path = (root / item["path"]).resolve()
        if not path.is_file() or common.sha256_file(path) != item["sha256"]:
            raise ValueError(field + " changed after presentation")
    decision = common.read_json(decision_file)
    common.validate_schema(decision, "gamearts-review-decision")
    if decision.get("decision") != "approved" or decision.get("reviewer_type") != "user":
        raise ValueError("Explicit real user visual approval is required")
    if decision.get("asset_id") != packet["asset_id"] or decision.get("revision") != packet["revision"]:
        raise ValueError("Approval targets a different asset revision")
    if decision.get("packet_sha256") != common.sha256_file(packet_file):
        raise ValueError("Approval did not reference the exact reviewed packet")
    for key, expected in (("component_ids_approved", packet["component_ids"]), ("uncertainty_ids_acknowledged", packet["uncertain_region_ids"])):
        values = decision.get(key)
        if not isinstance(values, list) or len(values) != len(expected) or set(values) != set(expected):
            raise ValueError(key + " does not cover every reviewed item")
    for field in ("reviewed_inventory", "reviewed_silhouettes", "reviewed_clean_background"):
        if decision.get(field) is not True:
            raise ValueError(field + " must be explicitly reviewed")
    if not isinstance(decision.get("user_approval_reference"), str) or not decision["user_approval_reference"].strip():
        raise ValueError("Missing reference to actual user approval message")
    return {"asset_id": packet["asset_id"], "revision": packet["revision"], "review_status": "user_visual_approval_recorded",
            "review_packet_sha256": common.sha256_file(packet_file), "decision_sha256": common.sha256_file(decision_file),
            "accepted_components": packet["component_ids"], "accepted_uncertainties": packet["uncertain_region_ids"],
            "approved_mockup_id": packet["approved_reference"]["mockup_id"],
            "approved_mockup_revision": packet["approved_reference"]["revision"],
            "approved_mockup_source_sha256": packet["approved_reference"]["source_sha256"],
            "approval_source_verification": "agent_recorded_not_host_attested", "semantic_recognition": "not_automated",
            "engine_validation": "not_tested"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)
    first = actions.add_parser("prepare")
    first.add_argument("--cleanup", type=Path, required=True)
    first.add_argument("--review-spec", type=Path, required=True)
    first.add_argument("--output-dir", type=Path, required=True)
    second = actions.add_parser("verify")
    second.add_argument("--packet", type=Path, required=True)
    second.add_argument("--decision", type=Path, required=True)
    second.add_argument("--result", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print("REVIEW PREPARED", prepare(args.cleanup, args.review_spec, args.output_dir))
        else:
            result = verify(args.packet, args.decision)
            if args.result:
                common.atomic_write_json(args.result, result)
            print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:  # ValueError covers JSON and contract errors
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
