#!/usr/bin/env python3
"""Universal Game Arts static-parent cleanup validator.

Pixel-check a decomposed source against the cleaned static parent and an independently reviewed clean plate. Applies
after raster export to ALL art styles (pixel, painted, illustrated, vector, rendered, custom).

Strict mode (`--strict-props`, required for new production) additionally requires, per detached sprite, a reviewed
silhouette mask AND the sprite's position in the source composite, and then proves the sprite is the source pixels
under its removal mask. This does NOT infer omitted props or certify that the reviewed plate is artistically correct;
visual inventory and clean-plate review remain mandatory.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageChops  # noqa: E402

import gamearts_common as common  # noqa: E402

KINDS = {"movable", "removable", "interactive", "replaceable", "animated", "independent_prop"}


def require_path(folder, ref, label):
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"{label} must specify a file")
    file = common.safe_member(folder, ref, label)
    if not file.is_file():
        raise ValueError(f"{label} is missing: {file}")
    return file


def mask_image(path, size, label):
    with Image.open(path) as src:
        if src.mode not in ("1", "L"):
            raise ValueError(f"{label} must be 1-bit or grayscale removal mask")
        image = src.convert("L")
    if image.size != size:
        raise ValueError(f"{label} dimensions differ from parent master")
    if image.point(lambda p: 255 if p not in (0, 255) else 0).getbbox():
        raise ValueError(f"{label} must be binary black/white")
    return image


def both(a, b):
    return ImageChops.multiply(a, b)


def checked_report(manifest_path, strict_props=False):
    manifest_path = Path(manifest_path).resolve()
    data = common.read_json(manifest_path)
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("Cleanup manifest must be version 1.0 JSON object")
    common.validate_schema(data, "gamearts-cleanup")
    if data.get("clean_plate_review") != "approved":
        raise ValueError("Independently reviewed clean plate must have approved status")
    directory = manifest_path.parent
    source = require_path(directory, data["source_composite"], "source_composite")
    parent = require_path(directory, data["static_parent"], "static_parent")
    plate = require_path(directory, data["clean_plate"], "clean_plate")
    if parent == plate or source == plate:
        raise ValueError("Clean plate must be distinct source, not alias of original or parent")
    src, dst, bg = (common.load_rgba(p, n) for p, n in ((source, "source_composite"), (parent, "static_parent"), (plate, "clean_plate")))
    if src.size != dst.size or src.size != bg.size:
        raise ValueError("Source, parent and plate must have identical pixel dimensions")
    size = src.size
    src_vs_parent = common.diff_mask(src, dst)       # pixels the cleanup changed
    parent_vs_plate = common.diff_mask(dst, bg)      # pixels where the parent departs from the reviewed plate
    union = Image.new("L", size, 0)
    hashes = {p.name: common.sha256_file(p) for p in (source, parent, plate)}
    counts, silhouettes, ties, masks = {}, {}, {}, {}
    identifiers = set()
    for part in data["detached_components"]:
        identifier = part["id"]
        if identifier in identifiers:
            raise ValueError("Each separated component requires distinct nonempty ID")
        identifiers.add(identifier)
        if part["kind"] not in KINDS:
            raise ValueError(f"{identifier}: invalid component classification")
        part_file = require_path(directory, part["sprite"], f"{identifier}.sprite")
        mask_file = require_path(directory, part["removal_mask"], f"{identifier}.removal_mask")
        component = common.load_rgba(part_file, f"{identifier}.sprite")
        ink = common.nonkey_mask(component)
        if ink.getbbox() is None:
            raise ValueError(f"{identifier}: detached sprite contains no non-pink artwork")
        if strict_props:
            if part.get("silhouette_review") != "approved" or not part.get("silhouette_reference_id"):
                raise ValueError(f"{identifier}: independently approved silhouette reference required")
            stencil_file = require_path(directory, part.get("sprite_silhouette_mask"), f"{identifier}.sprite_silhouette_mask")
            stencil = mask_image(stencil_file, component.size, f"{identifier}.sprite_silhouette_mask")
            leaked = common.mask_count(both(ink, ImageChops.invert(stencil)))
            missing = common.mask_count(both(ImageChops.invert(ink), stencil))
            if leaked or missing:
                raise ValueError(f"{identifier}: detached sprite silhouette mismatch: {leaked} colored pixels outside approved "
                                 f"mask, {missing} missing inside")
            silhouettes[identifier] = {"status": "passed", "ink_pixels": common.mask_count(ink), "mask_sha256": common.sha256_file(stencil_file)}
            hashes[stencil_file.name] = silhouettes[identifier]["mask_sha256"]
        mask = mask_image(mask_file, size, f"{identifier}.removal_mask")
        if both(union, mask).getbbox() is not None:
            raise ValueError(f"{identifier}: overlapping separation masks require layered evidence")
        area = common.mask_count(mask)
        if not area:
            raise ValueError(f"{identifier}: empty removal mask")
        union = ImageChops.lighter(union, mask)
        masks[identifier] = mask
        if strict_props:
            offset = part.get("source_offset")
            if offset is None:
                raise ValueError(f"{identifier}: strict props require source_offset (where the sprite sits in source_composite)")
            ox, oy = offset
            if ox < 0 or oy < 0 or ox + component.width > size[0] or oy + component.height > size[1]:
                raise ValueError(f"{identifier}: source_offset places the sprite outside the source composite")
            tolerance = part.get("source_tolerance", 0)
            region = src.crop((ox, oy, ox + component.width, oy + component.height))
            mismatch = common.diff_mask(region, component, tolerance)
            bad = common.mask_count(both(ink, mismatch))
            if bad:
                raise ValueError(f"{identifier}: sprite pixels differ from the source composite at its offset at {bad} ink pixels")
            placed = Image.new("L", size, 0)
            placed.paste(ink, (ox, oy))
            outside = common.mask_count(both(placed, ImageChops.invert(mask)))
            if outside:
                raise ValueError(f"{identifier}: {outside} sprite pixels lie outside its removal mask, so they would stay in the parent")
            ties[identifier] = {"status": "passed", "offset": [ox, oy], "tolerance": tolerance}
        counts[identifier] = {"removal_pixels": area,
                              "source_changed_pixels": common.mask_count(both(src_vs_parent, mask)),
                              "clean_plate_mismatch_pixels": common.mask_count(both(parent_vs_plate, mask))}
        hashes[part_file.name] = common.sha256_file(part_file)
        hashes[mask_file.name] = common.sha256_file(mask_file)
    outside_union = ImageChops.invert(union)
    changed_outside = common.mask_count(both(src_vs_parent, outside_union))
    wrong_inside = common.mask_count(both(parent_vs_plate, union))
    removed_changed = common.mask_count(both(src_vs_parent, union))
    failures = []
    if changed_outside:
        failures.append(f"static parent changed outside removal masks at {changed_outside} pixels")
    if wrong_inside:
        failures.append(f"static parent differs from approved clean plate inside masks at {wrong_inside} pixels")
    if not removed_changed:
        failures.append("no detached component was actually removed from the original parent artwork")
    for identifier, row in counts.items():
        if not row["source_changed_pixels"]:
            failures.append(f"{identifier}: separate sprite exists but object remains in static parent")
    return {
        "schema_version": "1.0", "manifest": manifest_path.name, "manifest_sha256": common.sha256_file(manifest_path),
        "technical_status": "failed" if failures else "passed",
        "visual_inventory_completeness": "not_verified",
        "independent_plate_visual_approval": "agent_declared_not_attested",
        "clean_plate_identical_to_parent": parent_vs_plate.getbbox() is None,
        "style": data.get("art_style_id", "selected_project_style"),
        "sprite_isolation": {"status": "passed" if strict_props else "not_verified", "components": silhouettes},
        "sprite_source_tie": {"status": "passed" if strict_props else "not_verified", "components": ties},
        "image_size": list(size), "components": counts,
        "unchanged_pixels_altered_outside_masks": changed_outside,
        "parent_pixels_unrestored_inside_masks": wrong_inside, "separated_pixels_modified": removed_changed,
        "artifact_hashes": hashes, "failures": failures}


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
                   help="Require reviewed silhouettes and source offsets (required for new production)")
    args = p.parse_args()
    try:
        result = checked_report(args.manifest, strict_props=args.strict_props)
        if args.report:
            common.atomic_write_json(args.report, result)
        if result["failures"]:
            for issue in result["failures"]:
                print("FAIL", issue)
            return 1
        print("PASS: separated component artwork is absent from static parent inside declared masks")
        print("NOT VERIFIED: omitted objects or artistic validity of approved clean plate")
        if not args.strict_props:
            print("NOT VERIFIED: independent prop silhouettes and source tie (use --strict-props for new production)")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as err:  # ValueError covers JSON and contract errors
        print("BLOCKED", str(err))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
