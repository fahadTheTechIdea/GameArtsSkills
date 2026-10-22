#!/usr/bin/env python3
"""Produce inspectable Game Arts extraction boards and bind a user decision to exact file hashes.

prepare --cleanup cleanup.json --review-spec spec.json --output-dir review/
verify  --packet review/visual_review.packet.json --decision review/decision.json

This DOES NOT visually recognize objects or independently attest a user message.
An agent must display both boards, obtain real user approval, then write the
decision. Approved original assets are never silently modified.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont, ImageChops

PINK = (255, 0, 255, 255)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixels(image):
    return image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def asset(path, ref, desc):
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"Missing {desc} file")
    p = (Path(path).parent / ref).resolve()
    if not p.is_file():
        raise ValueError(f"Missing {desc}: {p}")
    return p


def rgba(path):
    with Image.open(path) as image:
        return image.convert("RGBA")


def binary(path, size):
    with Image.open(path) as source:
        if source.mode not in ("1", "L"):
            raise ValueError(f"Mask must use L or 1 mode: {path}")
        image = source.convert("L")
    if image.size != size:
        raise ValueError(f"Mask size differs from source geometry: {path}")
    if image.point(lambda p: 255 if p not in (0, 255) else 0).getbbox():
        raise ValueError(f"Mask contains nonbinary values: {path}")
    return image


def checker(size, tile=12):
    canvas = Image.new("RGB", size, (239, 239, 237))
    painter = ImageDraw.Draw(canvas)
    w, h = size
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if (x // tile + y // tile) % 2 == 0:
                painter.rectangle((x, y, min(w-1, x+tile-1), min(h-1, y+tile-1)),
                                  fill=(207, 209, 210))
    return canvas


def fit(image, size, method=Image.Resampling.NEAREST):
    w, h = image.size
    scale = min(size[0] / w, size[1] / h)
    return image.resize((max(1, int(w*scale)), max(1, int(h*scale))),
                        method)


def matte(image):
    image = image.convert("RGBA")
    background = checker(image.size).convert("RGBA")
    visible = Image.new("L", image.size)
    visible.putdata([0 if rgba == PINK else 255 for rgba in pixels(image)])
    background.paste(image, (0, 0), visible)
    return background.convert("RGB")


def panel_board(panels, cols=3, panel=(330, 275), method=Image.Resampling.NEAREST):
    margin, label_h = 12, 34
    rows = math.ceil(len(panels) / cols)
    cell_w, cell_h = panel[0] + 2*margin, panel[1] + label_h + 2*margin
    board = Image.new("RGB", (cols*cell_w, rows*cell_h), (245, 241, 230))
    painter = ImageDraw.Draw(board)
    font = ImageFont.load_default()
    for i, (title, image) in enumerate(panels):
        x = i % cols * cell_w + margin
        y = i // cols * cell_h + margin
        painter.rectangle((x-3, y-3, x+panel[0]+3, y+panel[1]+label_h+3),
                          outline=(68, 69, 71), width=2)
        art = fit(image.convert("RGB"), panel, method)
        board.paste(art, (x+(panel[0]-art.width)//2, y+(panel[1]-art.height)//2))
        painter.text((x+4, y+panel[1]+6), title[:47], fill=(20, 20, 20), font=font)
    return board


def overlay(image, mask, color, strength=0.35):
    base = image.convert("RGB")
    shade = Image.new("RGB", image.size, color)
    mixed = Image.blend(base, shade, strength)
    return Image.composite(mixed, base, mask)


def rel(base, target):
    return os.path.relpath(str(target), str(base))


def inside(file, directory):
    try:
        Path(file).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False


def prepare(cleanup_file, review_spec_file, output_dir):
    cleanup_file = Path(cleanup_file).resolve()
    review_spec_file = Path(review_spec_file).resolve()
    output_dir = Path(output_dir).resolve()
    manifest, spec = read(cleanup_file), read(review_spec_file)
    if not isinstance(manifest, dict) or not isinstance(spec, dict):
        raise ValueError("Expected cleanup manifest and review specification objects")
    parts = manifest.get("detached_components", [])
    if not isinstance(parts, list) or not parts:
        raise ValueError("No detached components to review")
    ids = [p.get("id") for p in parts if isinstance(p, dict)]
    if len(ids) != len(parts) or len(set(ids)) != len(ids) or any(
        not isinstance(i, str) or not i for i in ids
    ):
        raise ValueError("Invalid duplicate/missing object IDs")
    expected = spec.get("expected_component_ids")
    if not isinstance(expected, list) or len(expected) != len(ids) or set(expected) != set(ids):
        raise ValueError("Review inventory must exactly match separated component IDs")
    if spec.get("inventory_audit") != "complete_for_visible_reference":
        raise ValueError("Analyzer must declare a completed visible-object inventory audit")
    if spec.get("occlusion_audit") != "completed":
        raise ValueError("Occlusion audit must be explicitly completed")
    reference = spec.get("approved_reference")
    if not isinstance(reference, dict) or any(
        not isinstance(reference.get(field), str) or not reference[field].strip()
        for field in ("file", "sha256", "mockup_id", "mockup_revision")
    ):
        raise ValueError("Exact approved reference crop, hash, mockup ID and revision required")
    approved_reference_file = asset(review_spec_file, reference["file"], "approved mockup reference crop")
    if sha(approved_reference_file) != reference["sha256"]:
        raise ValueError("Approved mockup reference crop hash differs from registered source")
    approved_reference_art = rgba(approved_reference_file)
    identity, revision = spec.get("asset_id"), spec.get("revision")
    if not all(isinstance(v, str) and v.strip() for v in (identity, revision)):
        raise ValueError("Asset identity and exact revision are required")
    uncertain = spec.get("uncertain_regions")
    if not isinstance(uncertain, list):
        raise ValueError("Explicit uncertain_regions list required; empty only after actual occlusion audit")

    original_file = asset(cleanup_file, manifest.get("source_composite"), "original composite")
    parent_file = asset(cleanup_file, manifest.get("static_parent"), "cleaned parent")
    plate_file = asset(cleanup_file, manifest.get("clean_plate"), "clean background plate")
    original, parent, plate = (rgba(path) for path in (original_file, parent_file, plate_file))
    if not (original.size == parent.size == plate.size):
        raise ValueError("Review requires aligned original/clean/plate raster sizes")
    size = original.size
    mask_union = Image.new("L", size, 0)
    dependencies = [cleanup_file, review_spec_file, original_file, parent_file, plate_file,
                    approved_reference_file]
    prop_panels = []
    bounds = {}
    original_bytes, parent_bytes, plate_bytes = original.tobytes(), parent.tobytes(), plate.tobytes()
    for part in parts:
        ident = part["id"]
        removal_file = asset(cleanup_file, part.get("removal_mask"), ident + " removal mask")
        sprite_file = asset(cleanup_file, part.get("sprite"), ident + " sprite")
        stencil_file = asset(cleanup_file, part.get("sprite_silhouette_mask"),
                             ident + " independent silhouette mask")
        removal = binary(removal_file, size)
        sprite = rgba(sprite_file)
        if sprite.getchannel("A").getextrema() != (255, 255):
            raise ValueError(f"{ident}: sprite must be fully opaque")
        stencil = binary(stencil_file, sprite.size)
        if stencil.getbbox() is None or removal.getbbox() is None:
            raise ValueError(f"{ident}: empty ownership/silhouette mask")
        if ImageChops.multiply(mask_union, removal).getbbox() is not None:
            raise ValueError(f"Overlapping removal masks for {ident}")
        mask_union = ImageChops.lighter(mask_union, removal)
        bounds[ident] = list(removal.getbbox())
        if not any(v and original_bytes[4*i:4*i+4] != parent_bytes[4*i:4*i+4]
                   for i, v in enumerate(removal.tobytes())):
            raise ValueError(f"{ident}: detached sprite exists but object still painted in parent")

        # Exact comparison to chroma pink, independent of color-space/luma rounding.
        ink = Image.new("L", sprite.size)
        ink.putdata([0 if rgba == PINK else 255 for rgba in pixels(sprite)])
        if ImageChops.difference(ink, stencil).getbbox():
            raise ValueError(f"{ident}: independent silhouette mask differs from sprite pixels")
        prop_panels.extend([(ident + " / original context",
                             original.crop(removal.getbbox()).convert("RGB")),
                            (ident + " / isolated sprite", matte(sprite))])
        dependencies.extend([removal_file, sprite_file, stencil_file])

    # Geometric clean-parent proof is only a precondition for human visual review.
    outside_changed = inside_unrestored = 0
    for i, v in enumerate(mask_union.tobytes()):
        j = 4*i
        if v:
            if parent_bytes[j:j+4] != plate_bytes[j:j+4]:
                inside_unrestored += 1
        elif parent_bytes[j:j+4] != original_bytes[j:j+4]:
            outside_changed += 1
    if outside_changed or inside_unrestored:
        raise ValueError(f"Clean parent pixel test failed: {outside_changed} outside changes, "
                         f"{inside_unrestored} unrecovered interior pixels")
    uncertain_union = Image.new("L", size, 0)
    uncertain_ids = []
    for record in uncertain:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
            raise ValueError("Each uncertain region needs an ID")
        if record["id"] in uncertain_ids:
            raise ValueError("Duplicate uncertain region ID")
        if record.get("evidence_status") not in ("inferred", "partially_observed", "unknown"):
            raise ValueError(f"{record['id']}: uncertainty must be classified")
        if not isinstance(record.get("reason"), str) or not record["reason"].strip():
            raise ValueError(f"{record['id']}: explain hidden/reconstructed surface")
        unknown_file = asset(review_spec_file, record.get("mask"), "uncertainty mask")
        unknown_mask = binary(unknown_file, size)
        if unknown_mask.getbbox() is None:
            raise ValueError(f"{record['id']}: empty uncertainty region")
        uncertain_union = ImageChops.lighter(uncertain_union, unknown_mask)
        dependencies.append(unknown_file)
        uncertain_ids.append(record["id"])

    delta = ImageChops.difference(original.convert("RGB"), parent.convert("RGB"))
    delta_mask = Image.new("L", size)
    delta_mask.putdata([255 if rgb != (0, 0, 0) else 0 for rgb in pixels(delta)])
    panels = [
        ("0 / Approved original mockup crop", approved_reference_art),
        ("A / Original reference composite", original),
        ("B / Static parent after cleanup", parent),
        ("C / Proposed clean background plate", plate),
        ("D / Removal regions in original", overlay(original, mask_union, (233, 80, 24))),
        ("E / Hidden/reconstructed areas", overlay(parent, uncertain_union, (238, 185, 37), .68)),
        ("F / Changed pixels marked blue", overlay(original, delta_mask, (72, 140, 210))),
    ]
    # All review evidence must come from the CURRENT candidate. This prevents
    # hidden v001/revoked dependencies and keeps relative hashes valid if the
    # complete v002+ bundle later moves from generated to approved.
    candidate_root = output_dir.parent
    if not all(inside(path, candidate_root) for path in dependencies):
        raise ValueError("Visual review depends on files outside current asset candidate")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("Review output exists; use another candidate or revision")
    output_dir.mkdir(parents=True, exist_ok=True)
    main_board = output_dir / "visual_review_board.png"
    prop_board = output_dir / "visual_review_props.png"
    packet_file = output_dir / "visual_review.packet.json"
    art_style = spec.get("art_style_id", manifest.get("art_style_id", "custom"))
    resampling = Image.Resampling.NEAREST if art_style == "pixel_art" else Image.Resampling.LANCZOS
    panel_board(panels, method=resampling).save(main_board)
    panel_board(prop_panels, cols=2, panel=(285, 220), method=resampling).save(prop_board)
    tracked = [{"path": rel(output_dir, path), "sha256": sha(path)}
               for path in sorted(set(dependencies))]
    packet = {
        "schema_version": "1.0", "type": "gamearts-visual-acceptance",
        "asset_id": identity, "revision": revision,
        "review_status": "pending_user_visual_review",
        "cleanup_manifest": rel(output_dir, cleanup_file),
        "review_spec": rel(output_dir, review_spec_file),
        "approved_reference": {"mockup_id": reference["mockup_id"],
                               "revision": reference["mockup_revision"],
                               "path": rel(output_dir, approved_reference_file),
                               "sha256": reference["sha256"]},
        "source_files": tracked,
        "art_style_id": art_style,
        "review_board": {"path": main_board.name, "sha256": sha(main_board)},
        "props_board": {"path": prop_board.name, "sha256": sha(prop_board)},
        "component_ids": sorted(ids), "object_source_bounds": bounds,
        "uncertain_region_ids": sorted(uncertain_ids),
        "review_criteria": [
            "all separable objects inventoried",
            "correct object-shaped cutouts",
            "no detached object remains baked into static parent",
            "reconstructed background looks plausible",
            "approved style, camera and proportions preserved"
        ],
        "semantic_object_verification": "requires_human_review",
        "background_plausibility": "requires_human_review",
        "godot_test": "not_performed"
    }
    packet_file.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    return packet_file


def verify(packet_file, decision_file):
    packet_file = Path(packet_file).resolve()
    packet = read(packet_file)
    if packet.get("type") != "gamearts-visual-acceptance" or packet.get("review_status") != "pending_user_visual_review":
        raise ValueError("Invalid or modified review packet")
    root = packet_file.parent
    for item in packet.get("source_files", []):
        path = (root / item["path"]).resolve()
        if not inside(path, root.parent):
            raise ValueError("Review source path escapes approved candidate bundle")
        if not path.is_file() or sha(path) != item["sha256"]:
            raise ValueError("Review source file changed after presentation: " + str(item.get("path")))
    for field in ("review_board", "props_board"):
        item = packet[field]
        path = (root / item["path"]).resolve()
        if not path.is_file() or sha(path) != item["sha256"]:
            raise ValueError(field + " changed after presentation")
    decision = read(decision_file)
    if decision.get("decision") != "approved" or decision.get("reviewer_type") != "user":
        raise ValueError("Explicit real user visual approval is required")
    if decision.get("asset_id") != packet["asset_id"] or decision.get("revision") != packet["revision"]:
        raise ValueError("Approval targets a different asset revision")
    if decision.get("packet_sha256") != sha(packet_file):
        raise ValueError("Approval did not reference the exact reviewed packet")
    for key, expected in (("component_ids_approved", packet["component_ids"]),
                          ("uncertainty_ids_acknowledged", packet["uncertain_region_ids"])):
        values = decision.get(key)
        if not isinstance(values, list) or len(values) != len(expected) or set(values) != set(expected):
            raise ValueError(key + " does not cover every reviewed item")
    for field in ("reviewed_inventory", "reviewed_silhouettes", "reviewed_clean_background"):
        if decision.get(field) is not True:
            raise ValueError(field + " must be explicitly reviewed")
    if not isinstance(decision.get("user_approval_reference"), str) or not decision["user_approval_reference"].strip():
        raise ValueError("Missing reference to actual user approval message")
    return {
        "asset_id": packet["asset_id"], "revision": packet["revision"],
        "review_status": "user_visual_approval_recorded",
        "review_packet_sha256": sha(packet_file),
        "decision_sha256": sha(decision_file),
        "accepted_components": packet["component_ids"],
        "accepted_uncertainties": packet["uncertain_region_ids"],
        "approved_mockup_id": packet["approved_reference"]["mockup_id"],
        "approved_mockup_revision": packet["approved_reference"]["revision"],
        "approval_source_verification": "agent_recorded_not_host_attested",
        "semantic_recognition": "not_automated",
        "engine_validation": "not_tested"
    }


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
                args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
