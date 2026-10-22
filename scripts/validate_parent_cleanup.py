#!/usr/bin/env python3
"""Universal Game Arts static-parent cleanup validator.

Pixel-check a decomposed source against the cleaned static parent and an
independently approved clean plate. Applies after raster export to ALL art
styles (pixel, painted, illustrated, vector, rendered, custom).

This does NOT infer omitted props, certify an independently reviewed plate,
or remove artwork. Visual inventory and clean-plate review remain mandatory.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

PINK = (255, 0, 255, 255)
KINDS = {"movable", "removable", "interactive", "replaceable", "animated", "independent_prop"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_path(folder, ref, label):
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"{label} must specify a file")
    file = (folder / ref).resolve()
    if not file.is_file():
        raise ValueError(f"{label} is missing: {file}")
    return file


def rgba(path, label):
    with Image.open(path) as image:
        result = image.convert("RGBA")
    if result.getchannel("A").getextrema() != (255, 255):
        raise ValueError(f"{label} must be fully opaque; use a separate mask")
    return result


def mask_image(path, size, label):
    with Image.open(path) as src:
        if src.mode not in ("1", "L"):
            raise ValueError(f"{label} must be 1-bit or grayscale removal mask")
        image = src.convert("L")
    if image.size != size:
        raise ValueError(f"{label} dimensions differ from parent master")
    if any(color not in (0, 255) for _, color in image.getcolors(image.width * image.height) or []):
        raise ValueError(f"{label} must be binary black/white")
    return image


def checked_report(manifest_path, strict_props=False):
    manifest_path = Path(manifest_path).resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("Cleanup manifest must be version 1.0 JSON object")
    if data.get("method") != "pixel_exact":
        raise ValueError("Only pixel_exact is technically certified; other methods need independent evidence")
    if data.get("clean_plate_review") != "approved":
        raise ValueError("Independently reviewed clean plate must have approved status")
    if not data.get("clean_plate_reference_id"):
        raise ValueError("Clean plate needs independent approved reference ID")
    directory = manifest_path.parent
    source = require_path(directory, data.get("source_composite"), "source_composite")
    parent = require_path(directory, data.get("static_parent"), "static_parent")
    plate = require_path(directory, data.get("clean_plate"), "clean_plate")
    if parent == plate or source == plate:
        raise ValueError("Clean plate must be distinct source, not alias of original or parent")
    src, dst, bg = rgba(source, "source_composite"), rgba(parent, "static_parent"), rgba(plate, "clean_plate")
    if src.size != dst.size or src.size != bg.size:
        raise ValueError("Source, parent and plate must have identical pixel dimensions")
    parts = data.get("detached_components")
    if not isinstance(parts, list) or not parts:
        raise ValueError("At least one separated component is required")
    identifiers = set()
    total = src.width * src.height
    union = bytearray(total)
    counts = {}
    hashes = {str(source): digest(source), str(parent): digest(parent), str(plate): digest(plate)}
    masks = {}
    silhouettes = {}
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError("Each detached component must be an object")
        identifier = part.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ValueError("Each separated component requires distinct nonempty ID")
        identifiers.add(identifier)
        if part.get("kind") not in KINDS:
            raise ValueError(f"{identifier}: invalid component classification")
        part_file = require_path(directory, part.get("sprite"), f"{identifier}.sprite")
        mask_file = require_path(directory, part.get("removal_mask"), f"{identifier}.removal_mask")
        component = rgba(part_file, f"{identifier}.sprite")
        if strict_props:
            # A foreground stencil must be independently checked against
            # the approved source, not generated from the exported sprite.
            if part.get("silhouette_review") != "approved" or not part.get("silhouette_reference_id"):
                raise ValueError(f"{identifier}: independently approved silhouette reference required")
            ink_mask = require_path(directory, part.get("sprite_silhouette_mask"),
                                    f"{identifier}.sprite_silhouette_mask")
            binary = mask_image(ink_mask, component.size, f"{identifier}.sprite_silhouette_mask")
            ink = [pixel != PINK for pixel in component.getdata()]
            expected = [v == 255 for v in binary.getdata()]
            leaked = sum(1 for actual, allowed in zip(ink, expected) if actual and not allowed)
            empty_expected = sum(1 for actual, allowed in zip(ink, expected) if allowed and not actual)
            if leaked or empty_expected:
                raise ValueError(f"{identifier}: detached sprite silhouette mismatch: "
                                 f"{leaked} colored pixels outside approved mask, "
                                 f"{empty_expected} missing inside")
            silhouettes[identifier] = {"status": "passed", "ink_pixels": sum(ink),
                                       "mask_sha256": digest(ink_mask)}
            hashes[str(ink_mask)] = digest(ink_mask)
        if ImageChops.difference(component.convert("RGB"), Image.new("RGB", component.size, PINK[:3])).getbbox() is None:
            raise ValueError(f"{identifier}: detached sprite contains no non-pink artwork")
        mask = mask_image(mask_file, src.size, f"{identifier}.removal_mask").tobytes()
        area = 0
        for index, value in enumerate(mask):
            if value:
                if union[index]:
                    raise ValueError(f"{identifier}: overlapping separation masks require layered evidence")
                union[index] = 1
                area += 1
        if not area:
            raise ValueError(f"{identifier}: empty removal mask")
        masks[identifier] = mask
        counts[identifier] = {"removal_pixels": area, "source_changed_pixels": 0,
                              "clean_plate_mismatch_pixels": 0}
        hashes[str(part_file)] = digest(part_file)
        hashes[str(mask_file)] = digest(mask_file)
    original, cleaned, background = src.tobytes(), dst.tobytes(), bg.tobytes()
    changed_outside, wrong_inside, removed_changed = 0, 0, 0
    for i in range(total):
        p = 4*i
        before, after, plate_px = original[p:p+4], cleaned[p:p+4], background[p:p+4]
        if union[i]:
            if before != after:
                removed_changed += 1
            if after != plate_px:
                wrong_inside += 1
        elif after != before:
            changed_outside += 1
    failures = []
    if changed_outside:
        failures.append(f"static parent changed outside removal masks at {changed_outside} pixels")
    if wrong_inside:
        failures.append(f"static parent differs from approved clean plate inside masks at {wrong_inside} pixels")
    if not removed_changed:
        failures.append("no detached component was actually removed from the original parent artwork")
    for identifier, mask in masks.items():
        removed = sum(1 for i, v in enumerate(mask) if v and
                      original[4*i:4*i+4] != cleaned[4*i:4*i+4])
        wrong = sum(1 for i, v in enumerate(mask) if v and
                    cleaned[4*i:4*i+4] != background[4*i:4*i+4])
        counts[identifier]["source_changed_pixels"] = removed
        counts[identifier]["clean_plate_mismatch_pixels"] = wrong
        if not removed:
            failures.append(f"{identifier}: separate sprite exists but object remains in static parent")
    return {
        "schema_version": "1.0",
        "manifest": str(manifest_path),
        "manifest_sha256": digest(manifest_path),
        "technical_status": "failed" if failures else "passed",
        "visual_inventory_completeness": "not_verified",
        "independent_plate_visual_approval": "agent_declared_not_attested",
        "style": data.get("art_style_id", "selected_project_style"),
        "sprite_isolation": {"status": "passed" if strict_props else "not_verified",
                             "components": silhouettes},
        "image_size": list(src.size),
        "components": counts,
        "unchanged_pixels_altered_outside_masks": changed_outside,
        "parent_pixels_unrestored_inside_masks": wrong_inside,
        "separated_pixels_modified": removed_changed,
        "artifact_hashes": hashes,
        "failures": failures,
    }


def validate(manifest_path, strict_props=False):
    result = checked_report(manifest_path, strict_props=strict_props)
    if result["failures"]:
        raise ValueError("; ".join(result["failures"]))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--strict-props", action="store_true",
                   help="Require independently reviewed per-prop silhouette masks")
    args = p.parse_args()
    try:
        result = checked_report(args.manifest, strict_props=args.strict_props)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if result["failures"]:
            for issue in result["failures"]:
                print("FAIL", issue)
            return 1
        print("PASS: separated component artwork is absent from static parent inside declared masks")
        print("NOT VERIFIED: omitted objects or artistic validity of approved clean plate")
        if not args.strict_props:
            print("NOT VERIFIED: independent prop silhouettes (use --strict-props for new production)")
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as err:
        print("BLOCKED", str(err))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
