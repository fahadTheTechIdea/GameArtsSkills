#!/usr/bin/env python3
"""Remove the extracted objects from the scene and reconstruct what was behind them: a DRAFT clean parent (the removal step of the mockup analyzer).

  python scripts/remove_scene_objects.py remove --blueprint BP.json --mockup IMG.png --output-dir DIR [--grow 2] [--max-share 0.03] [--provisional]

Every object that has a mask (`removal_mask_ref` beside the blueprint, from `detect_scene_objects.py` or a person) is cut out of the picture: its mask is placed at its region,
grown by --grow pixels (shadows and soft edges), and the union is filled in by classical inpainting (OpenCV's Telea method, an optional extra: `pip install opencv-python`). It writes

  clean_parent_draft.png        the scene with the objects removed and their places reconstructed
  removal_masks/<class>/<id>.png one full-size 0 / 255 mask per object (the cleanup contract's removal mask)
  removal_report.json           what was removed, what could not be (no mask), the share of the picture that is reconstructed, overlapping masks, and what was not assessed

The reconstructed pixels are INFERRED, never observed: inpainting invents plausible ground, it does not recover it. The result is a draft for the cleanup gate (master §17), whose clean
plate must be reviewed by a person before it counts; it is not the approved clean parent. Objects without a mask are not removed (a box would take out the ground around them), and are
listed. Classical inpainting can only plausibly reconstruct a SMALL object against a plain surface, so an object of an area class (street, parking, building: the parent's own surfaces) and any
object whose mask covers more than --max-share of the picture are not removed and are listed with the reason; removing them would only smear the picture (measured: removing every detected object, big
ones included, reconstructed 63% of a street scene into smears). Overlapping masks are reported, because the cleanup gate wants disjoint ones (a person standing in front of a door overlaps it). An unapproved mockup needs --provisional, and an approved
one is checked against its hash, as in `extract_scene_objects.py`. Nothing is overwritten; the output folder must be empty.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_scene_objects as extractor  # noqa: E402
import gamearts_common as common  # noqa: E402
import validate_blueprint as blueprint_rules  # noqa: E402


class TeleaInpainter:
    """Classical (non-generative) inpainting with OpenCV's Telea method: fills each masked pixel from the unmasked ones around it."""

    id = "opencv-telea"

    def __init__(self, radius=3):
        try:
            import cv2
            import numpy
        except ImportError as exc:
            raise ValueError("the removal step needs opencv-python (an optional extra: pip install opencv-python); it is not a dependency of the framework and nothing was run") from exc
        self.cv2, self.numpy, self.radius = cv2, numpy, radius

    def inpaint(self, image, mask):
        from PIL import Image
        array = self.numpy.asarray(image.convert("RGB"))
        filled = self.cv2.inpaint(array[:, :, ::-1].copy(), self.numpy.asarray(mask), self.radius, self.cv2.INPAINT_TELEA)
        return Image.fromarray(filled[:, :, ::-1].copy())


AREA_CLASSES = {"street", "parking", "building"}  # the parent's own surfaces and structures: never reconstructed by inpainting


def object_masks(data, base, size, grow, max_share):
    """({id: (class, full-size "L" mask grown by `grow` pixels)}, {reason: [ids not removed]}) for the blueprint's objects. A mask is the object's own, placed at its region."""
    from PIL import Image, ImageFilter
    components = extractor.components_of(data)
    masks, skipped = {}, {"no_mask": [], "area_class": [], "too_large": []}
    for component_id, (cls, _, (x, y, w, h), mask_ref) in components.items():
        if not mask_ref:
            skipped["no_mask"].append(component_id)
            continue
        if cls in AREA_CLASSES:
            skipped["area_class"].append(component_id)
            continue
        file = common.safe_member(base, mask_ref, f"{component_id} mask")
        if not file.is_file():
            raise ValueError(f"{component_id}: the mask {mask_ref} is not beside the blueprint")
        with Image.open(file) as opened:
            mask = opened.convert("L").point(lambda v: 255 if v >= 128 else 0)
        if mask.size != (w, h):
            raise ValueError(f"{component_id}: the mask is {mask.width} x {mask.height} and the region is {w} x {h}; they must be the same size")
        if mask.histogram()[255] > max_share * size[0] * size[1]:
            skipped["too_large"].append(component_id)
            continue
        full = Image.new("L", size, 0)
        full.paste(mask, (x, y))
        if grow:
            full = full.filter(ImageFilter.MaxFilter(2 * grow + 1))
        masks[component_id] = (cls, full)
    return masks, skipped


def remove(blueprint_path, mockup_path, output_dir, inpainter, grow=2, provisional=False, max_share=0.03):
    """Write the draft clean parent, the removal masks and the report into an empty folder; returns the report."""
    from PIL import Image, ImageChops
    data = common.read_json(blueprint_path)
    if not isinstance(data, dict):
        raise ValueError("the blueprint must be a JSON object")
    common.validate_schema(data, "mockup-blueprint")
    if "object_sweep" not in data:
        raise ValueError("the blueprint has no object_sweep: address every object class as present or absent first")
    problems = blueprint_rules.sweep_problems(data)
    if problems:
        raise ValueError("the object sweep is inconsistent: " + "; ".join(problems))
    if grow < 0:
        raise ValueError("--grow is zero or more pixels")
    if not 0 < max_share <= 1:
        raise ValueError("--max-share is above 0 and at most 1")
    mockup_hash = hashlib.sha256(Path(mockup_path).read_bytes()).hexdigest()
    extractor.check_source(data, mockup_hash, provisional)
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"{output_dir} is not empty; a removal never writes into a folder that has something in it")
    with Image.open(mockup_path) as opened:
        image = opened.convert("RGB")
    masks, skipped = object_masks(data, Path(blueprint_path).resolve().parent, image.size, grow, max_share)
    if not masks:
        raise ValueError("no object can be removed: none has a mask small enough that is not of an area class (run detect_scene_objects.py, or give each object a removal_mask_ref; see --max-share)")
    union = Image.new("L", image.size, 0)
    for _, mask in masks.values():
        union = ImageChops.lighter(union, mask)
    clean = inpainter.inpaint(image, union)
    if clean.size != image.size:
        raise ValueError("the inpainter returned a picture of another size")
    (output_dir / "removal_masks").mkdir(parents=True, exist_ok=True)
    clean.save(output_dir / "clean_parent_draft.png")
    ids = sorted(masks)
    for component_id in ids:
        cls, mask = masks[component_id]
        (output_dir / "removal_masks" / cls).mkdir(exist_ok=True)
        mask.save(output_dir / "removal_masks" / cls / f"{component_id}.png")
    overlaps = []
    for index, first in enumerate(ids):
        for second in ids[index + 1:]:
            both = ImageChops.multiply(masks[first][1], masks[second][1]).point(lambda v: 255 if v else 0)
            if both.getbbox():
                overlaps.append([first, second])
    covered = union.point(lambda v: 255 if v else 0).histogram()[255]
    report = {"mockup_id": data["mockup_id"], "mockup_sha256": mockup_hash, "provisional": data["approval_status"] != "approved", "inpainter": inpainter.id, "grow_px": grow,
              "max_share": max_share, "removed": ids, "not_removed": {reason: sorted(found) for reason, found in skipped.items() if found}, "reconstructed_share": round(covered / (image.width * image.height), 4), "overlapping_masks": overlaps,
              "clean_parent": "clean_parent_draft.png", "pixel_status": "reconstructed: inferred by inpainting, never observed",
              "not_assessed": ["whether the reconstruction is plausible: it must be reviewed by a person (master §17) before it counts as a clean plate",
                               "whether every object was removed: objects without a mask, of an area class or too large, and ones the detector missed, are still in the picture",
                               "the disjoint-mask rule of the cleanup gate: overlapping masks are listed and must be resolved before the gate"]}
    common.atomic_write_json(output_dir / "removal_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("remove")
    one.add_argument("--blueprint", type=Path, required=True)
    one.add_argument("--mockup", type=Path, required=True)
    one.add_argument("--output-dir", type=Path, required=True)
    one.add_argument("--grow", type=int, default=2, help="pixels to grow each mask by, to take in shadows and soft edges")
    one.add_argument("--max-share", type=float, default=0.03, help="an object whose mask covers more than this share of the picture is not removed (inpainting would smear it)")
    one.add_argument("--provisional", action="store_true", help="remove from an unapproved mockup; the result is labelled provisional")
    args = parser.parse_args()
    try:
        report = remove(args.blueprint, args.mockup, args.output_dir, TeleaInpainter(), args.grow, args.provisional, args.max_share)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps({k: report[k] for k in ("provisional", "inpainter", "grow_px", "reconstructed_share", "pixel_status", "not_assessed")} | {"removed": len(report["removed"]), "not_removed": {k: len(v) for k, v in report["not_removed"].items()},
                                                                                                                                     "overlapping_masks": len(report["overlapping_masks"])}, indent=2))


if __name__ == "__main__":
    main()
