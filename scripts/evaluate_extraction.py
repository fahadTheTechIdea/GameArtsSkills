#!/usr/bin/env python3
"""Measure a draft extraction against a reviewed one: how many of the reference's objects the draft found, and how many of its own were real.

  python scripts/evaluate_extraction.py compare --reference REVIEWED.blueprint.json --draft DRAFT.blueprint.json --output report.json [--iou 0.5]

Both are mockup blueprints (schemas/mockup-blueprint.schema.json) with a `separation_inventory` whose components have an `object_class` and a region (`source_region_px` on
the element of the same id). The reference is the owner's or analyzer's reviewed account; the draft is, usually, the detection step's output. Objects are matched one to one by
the overlap of their regions (intersection over union at or above --iou, best overlap first), and a match counts when the classes agree. It reports, per class and overall:

  recall     the share of the reference's objects the draft found      precision  the share of the draft's objects that are in the reference
  missed     reference objects with no match                           extra      draft objects with no match
  confused   objects that overlap a reference object well but carry another class

It tells how far a draft is from a reference; it does not say the reference is complete (a reference written by eye misses things too), and a regions-only match does not judge a mask.
Nothing is overwritten.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_scene_objects as extractor  # noqa: E402
import gamearts_common as common  # noqa: E402


def objects_of(path, label):
    """{id: (class, [x, y, w, h])} of a blueprint's inventory; refuses a blueprint that cannot be read as an inventory."""
    data = common.read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"the {label} must be a JSON object")
    common.validate_schema(data, "mockup-blueprint")
    try:
        found = extractor.components_of(data)
    except ValueError as exc:
        raise ValueError(f"the {label} cannot be read as an inventory: {exc}") from exc
    return {component_id: (cls, region) for component_id, (cls, _, region, _) in found.items()}


def compare(reference, draft, iou=0.5):
    """Match the draft to the reference and score it: returns the report. `reference` and `draft` are {id: (class, region)}."""
    if not 0 < iou <= 1:
        raise ValueError("the overlap threshold is above 0 and at most 1")
    pairs = sorted(((extractor.overlap(reference[r][1], draft[d][1]), r, d) for r in reference for d in draft), key=lambda item: (-item[0], item[1], item[2]))
    taken_reference, taken_draft, matches, confused = set(), set(), [], []
    for score, r, d in pairs:
        if score < iou:
            break
        if r in taken_reference or d in taken_draft:
            continue
        taken_reference.add(r)
        taken_draft.add(d)
        if reference[r][0] == draft[d][0]:
            matches.append({"reference": r, "draft": d, "overlap": round(score, 3), "object_class": reference[r][0]})
        else:
            confused.append({"reference": r, "reference_class": reference[r][0], "draft": d, "draft_class": draft[d][0], "overlap": round(score, 3)})
    matched_reference = {m["reference"] for m in matches}
    matched_draft = {m["draft"] for m in matches}
    classes = sorted({c for c, _ in reference.values()} | {c for c, _ in draft.values()})
    per_class = {}
    for cls in classes:
        ref_ids = [i for i, (c, _) in reference.items() if c == cls]
        draft_ids = [i for i, (c, _) in draft.items() if c == cls]
        hit = sum(1 for m in matches if m["object_class"] == cls)
        per_class[cls] = {"reference": len(ref_ids), "draft": len(draft_ids), "matched": hit, "recall": round(hit / len(ref_ids), 3) if ref_ids else None,
                          "precision": round(hit / len(draft_ids), 3) if draft_ids else None,
                          "missed": sorted(i for i in ref_ids if i not in matched_reference), "extra": sorted(i for i in draft_ids if i not in matched_draft)}
    total_ref, total_draft, hit = len(reference), len(draft), len(matches)
    recall = hit / total_ref if total_ref else 0.0
    precision = hit / total_draft if total_draft else 0.0
    return {"overlap_threshold": iou, "reference_objects": total_ref, "draft_objects": total_draft, "matched": hit, "recall": round(recall, 3), "precision": round(precision, 3),
            "f1": round(2 * recall * precision / (recall + precision), 3) if recall + precision else 0.0, "per_class": per_class, "confused": confused,
            "not_assessed": ["whether the reference is complete: a reference written by eye misses objects too, so a draft object marked extra may be real",
                             "mask quality: objects are matched by their regions only"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("compare")
    one.add_argument("--reference", type=Path, required=True)
    one.add_argument("--draft", type=Path, required=True)
    one.add_argument("--output", type=Path, required=True)
    one.add_argument("--iou", type=float, default=0.5)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError(f"{args.output.name} already exists; it is never overwritten")
        report = compare(objects_of(args.reference, "reference"), objects_of(args.draft, "draft"), args.iou)
        common.atomic_write_json(args.output, report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps({k: report[k] for k in ("reference_objects", "draft_objects", "matched", "recall", "precision", "f1")}, indent=2))
    for cls, row in report["per_class"].items():
        print(f"  {cls:18s} reference {row['reference']:3d}  draft {row['draft']:3d}  matched {row['matched']:3d}  recall {row['recall']}  precision {row['precision']}")


if __name__ == "__main__":
    main()
