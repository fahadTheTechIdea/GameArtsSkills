#!/usr/bin/env python3
"""Extract every object of a scene from its mockup, as the blueprint says (the extraction step of the mockup analyzer).

  python scripts/extract_scene_objects.py extract --blueprint BP.json --mockup MOCKUP.png --output-dir DIR [--provisional]

The blueprint (schemas/mockup-blueprint.schema.json) names every separated object in a `separation_inventory` with its `object_class`, gives each one a region in an element of the
same id (`source_region_px`), and holds the `object_sweep` that addresses every class. This step checks the sweep (`validate_blueprint.py`'s rules), then cuts each object's region
out of the mockup into DIR/<object_class>/<id>.png (and, for an object with a `removal_mask_ref` beside the blueprint, a cut-out <id>.sprite.png whose alpha is the mask) and writes:

  extraction.json   every object: id, class, ownership, region, crop file and hash (and the cut-out sprite and its hash when the object has a mask); per-class counts; the mockup's hash; what was not assessed
  overview.png      the mockup with every region drawn and labelled, coloured by class
  contact_sheet.png every crop, by class

It refuses: a blueprint whose sweep is missing or inconsistent, a component with no class or no region, a region outside the mockup, a mockup that is not the one an approved blueprint
names by hash, and an unapproved mockup unless `--provisional` (an analysis of an unapproved mockup is provisional and is labelled so). It reports, without refusing, pairs of objects
whose regions overlap so much that one is probably a duplicate of the other (a person standing in front of a door is not: only near-identical regions are flagged), and how much of
the mockup the objects cover. Nothing is overwritten; the output folder must be empty.

The regions themselves are the analyzer's reading of the mockup. This step cuts what it is told and checks the account is consistent; it does not find objects, and a crop is a
reference crop from the source, not a clean sprite: removing the object from its parent and making the clean plate behind it is the cleanup gate's work (master §17).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import validate_blueprint as blueprint_rules  # noqa: E402

DUPLICATE_OVERLAP = 0.6  # intersection over union at or above which two regions are reported as probable duplicates
COLOURS = {"character": (255, 60, 60), "vehicle": (60, 160, 255), "building": (255, 170, 90), "plant": (60, 255, 90), "sign": (255, 230, 40), "street_furniture": (255, 140, 0), "lighting": (255, 255, 255),
           "barrier": (200, 90, 255), "opening": (0, 255, 230), "prop": (255, 100, 200), "structure_part": (180, 120, 60), "street": (120, 120, 255),
           "parking": (255, 255, 120), "other": (150, 150, 150)}


def components_of(data):
    """Every separated object of the blueprint: {id: (class, ownership, region, mask reference or None)}; raises in words when one has no class or no region."""
    regions = {e["element_id"]: e.get("source_region_px") for e in data["elements"]}
    found, problems = {}, []
    for element in data["elements"]:
        for component in element.get("separation_inventory", []) or []:
            component_id = component["component_id"]
            if component_id in found:
                problems.append(f"{component_id} is in the inventory twice")
                continue
            if not component.get("object_class"):
                problems.append(f"{component_id} has no object_class")
            region = regions.get(component_id)
            if not region:
                problems.append(f"{component_id} has no element with that id giving its source_region_px")
            found[component_id] = (component.get("object_class"), component.get("ownership", []), region, component.get("removal_mask_ref"))
    if problems:
        raise ValueError("the inventory cannot be extracted: " + "; ".join(problems))
    if not found:
        raise ValueError("the blueprint's separation_inventory is empty: there is nothing to extract")
    return found


def overlap(a, b):
    """Intersection over union of two [x, y, w, h] regions."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


def check_source(data, mockup_hash, provisional):
    """The mockup must be the approved one when the blueprint is approved, and an unapproved blueprint is extracted only when asked to be provisional."""
    hashes = {e["approved_source_sha256"] for e in data["elements"] if e.get("approved_source_sha256")}
    if data["approval_status"] == "approved":
        if not hashes:
            raise ValueError("the blueprint is approved but no element names the approved source's sha256, so the mockup cannot be checked")
        if mockup_hash not in hashes:
            raise ValueError("the mockup is not the approved source the blueprint names (sha256 differs)")
    elif not provisional:
        raise ValueError(f"the blueprint is {data['approval_status']}, not approved: extract with --provisional for an analysis that is labelled provisional")
    elif hashes and mockup_hash not in hashes:
        raise ValueError("the mockup is not the source the blueprint names (sha256 differs)")


def extract(blueprint_path, mockup_path, output_dir, provisional=False):
    """Cut every object out of the mockup and write the manifest, the overview and the contact sheet; returns the manifest."""
    from PIL import Image, ImageDraw
    data = common.read_json(blueprint_path)
    if not isinstance(data, dict):
        raise ValueError("the blueprint must be a JSON object")
    common.validate_schema(data, "mockup-blueprint")
    if "object_sweep" not in data:
        raise ValueError("the blueprint has no object_sweep: address every object class as present or absent first")
    problems = blueprint_rules.sweep_problems(data)
    if problems:
        raise ValueError("the object sweep is inconsistent: " + "; ".join(problems))
    mockup_hash = hashlib.sha256(Path(mockup_path).read_bytes()).hexdigest()
    check_source(data, mockup_hash, provisional)
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"{output_dir} is not empty; an extraction never writes into a folder that has something in it")
    components = components_of(data)
    for component_id, (_, _, region, mask_ref) in components.items():  # every mask is checked before anything is written
        if mask_ref:
            mask_file = common.safe_member(Path(blueprint_path).resolve().parent, mask_ref, f"{component_id} mask")
            if not mask_file.is_file():
                raise ValueError(f"{component_id}: the mask {mask_ref} is not beside the blueprint")
            with Image.open(mask_file) as opened:
                if opened.size != (region[2], region[3]):
                    raise ValueError(f"{component_id}: the mask is {opened.width} x {opened.height} and the region is {region[2]} x {region[3]}; they must be the same size")
    with Image.open(mockup_path) as opened:
        image = opened.convert("RGB")
    for component_id, (_, _, region, _) in components.items():
        x, y, w, h = region
        if w < 1 or h < 1 or x < 0 or y < 0 or x + w > image.width or y + h > image.height:
            raise ValueError(f"{component_id}: the region {region} is empty or lies outside the {image.width} x {image.height} mockup")
    objects, drawn = [], image.copy()
    draw = ImageDraw.Draw(drawn)
    covered = Image.new("1", image.size, 0)
    cover_draw = ImageDraw.Draw(covered)
    base = Path(blueprint_path).resolve().parent
    for component_id, (cls, ownership, (x, y, w, h), mask_ref) in components.items():
        crop_path = output_dir / cls / f"{component_id}.png"
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        crop = image.crop((x, y, x + w, y + h))
        crop.save(crop_path)
        draw.rectangle((x, y, x + w, y + h), outline=COLOURS.get(cls, (150, 150, 150)), width=2)
        draw.text((x + 2, y + 1), component_id, fill=COLOURS.get(cls, (150, 150, 150)))
        cover_draw.rectangle((x, y, x + w - 1, y + h - 1), fill=1)
        entry = {"id": component_id, "object_class": cls, "ownership": ownership, "region_px": [x, y, w, h], "crop": f"{cls}/{component_id}.png", "crop_sha256": common.sha256_file(crop_path)}
        if mask_ref:  # the component's mask makes a cut-out sprite: the crop with everything outside the mask transparent
            with Image.open(common.safe_member(base, mask_ref, f"{component_id} mask")) as opened:
                mask = opened.convert("L")
            sprite = crop.convert("RGBA")
            sprite.putalpha(mask.point(lambda v: 255 if v >= 128 else 0))
            sprite_path = output_dir / cls / f"{component_id}.sprite.png"
            sprite.save(sprite_path)
            entry.update({"sprite": f"{cls}/{component_id}.sprite.png", "sprite_sha256": common.sha256_file(sprite_path)})
        objects.append(entry)
    drawn.save(output_dir / "overview.png")
    columns, cell = 12, 110
    ordered = sorted(objects, key=lambda o: (o["object_class"], o["id"]))
    sheet = Image.new("RGB", (columns * cell, -(-len(ordered) // columns) * (cell + 14)), (30, 30, 30))
    sheet_draw = ImageDraw.Draw(sheet)
    for index, item in enumerate(ordered):
        with Image.open(output_dir / item["crop"]) as opened:
            thumb = opened.convert("RGB")
        thumb.thumbnail((cell - 6, cell - 6))
        px, py = (index % columns) * cell + 3, (index // columns) * (cell + 14) + 3
        sheet.paste(thumb, (px, py))
        sheet_draw.text((px, py + thumb.height + 1), item["id"], fill=COLOURS.get(item["object_class"], (150, 150, 150)))
    sheet.save(output_dir / "contact_sheet.png")
    duplicates = [{"objects": [a["id"], b["id"]], "overlap": round(overlap(a["region_px"], b["region_px"]), 3)}
                  for index, a in enumerate(objects) for b in objects[index + 1:] if overlap(a["region_px"], b["region_px"]) >= DUPLICATE_OVERLAP]
    counts = {}
    for item in objects:
        counts[item["object_class"]] = counts.get(item["object_class"], 0) + 1
    manifest = {"mockup_id": data["mockup_id"], "mockup_revision": data["mockup_revision"], "mockup_sha256": mockup_hash, "approval_status": data["approval_status"],
                "provisional": data["approval_status"] != "approved", "mockup_size": [image.width, image.height], "objects": objects, "per_class": counts,
                "absent_classes": [e["object_class"] for e in data["object_sweep"] if e["status"] == "absent"],
                "possible_duplicates": duplicates, "mockup_covered_by_objects": round(covered.convert("L").point(lambda v: 255 if v else 0).tobytes().count(255) / (image.width * image.height), 4),
                "not_assessed": ["whether each region is exactly one whole object: the regions are the analyzer's reading and a crop is a reference crop, not a clean sprite",
                                 "what lies behind each object: the clean plate is the cleanup gate's work",
                                 "whether every object of a present class was found: the independent visual audit finds the ones that were missed"]}
    common.atomic_write_json(output_dir / "extraction.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("extract")
    one.add_argument("--blueprint", type=Path, required=True)
    one.add_argument("--mockup", type=Path, required=True)
    one.add_argument("--output-dir", type=Path, required=True)
    one.add_argument("--provisional", action="store_true", help="extract for an unapproved mockup; the result is labelled provisional")
    args = parser.parse_args()
    try:
        manifest = extract(args.blueprint, args.mockup, args.output_dir, args.provisional)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps({k: manifest[k] for k in ("mockup_id", "provisional", "per_class", "absent_classes", "possible_duplicates", "mockup_covered_by_objects", "not_assessed")}, indent=2))


if __name__ == "__main__":
    main()
