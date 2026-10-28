#!/usr/bin/env python3
"""Find the objects of a scene with a detection model and write a draft blueprint (the detection step of the mockup analyzer).

  python scripts/detect_scene_objects.py detect --mockup IMG.png --mockup-id ID --revision R --output-dir DIR [--device auto|cpu|cuda] [--tiles N]
                                                [--detector-kind grounding-dino|owlv2] [--box-threshold T] [--text-threshold T] [--exclude-region X,Y,W,H ...] [--runs N --min-runs K]
                                                [--detector MODEL] [--segmenter MODEL]
  python scripts/extract_scene_objects.py extract --blueprint DIR/detected.blueprint.json --mockup IMG.png --output-dir OUT --provisional

Grounding DINO (open-vocabulary detection, from a text prompt per object class) finds the objects, and SAM gives each one an accurate mask. The picture is searched whole and in an
N x N grid of overlapping tiles (small objects are enlarged that way); detections are merged (same-class overlaps, near-identical regions of two classes) and each survivor takes
the tight box of its mask. The result is a **draft** blueprint: `pending_approval`, every object `inferred` with the detector's score as its confidence, an `object_sweep` that says
which classes were found and, for the classes not found, that the detector found nothing (the detector's finding, not a visual audit), and a mask per object that the extraction
step turns into a cut-out sprite. A draft is reviewed by the analyzer against the picture before it is relied on: a detector misses things and sees things that are not there. To help that review every object the
draft is least sure of carries `review_flags` (oversized, tiny, low score, no mask or a weak one, an ambiguous label), and `--exclude-region` (repeatable) names where the interface
overlays are, so detections inside them (an icon found as a sign) are dropped and recorded as deliberate exclusions instead of being extracted.

The prompts for each class are the table PROMPTS below (the single owner); a class with no prompt cannot be found. The models are an optional extra, never a dependency of the framework:
`pip install torch transformers` and the models are fetched from the Hugging Face hub as plain weights (no remote code is run). A missing package is a refusal that says so, never a
silent skip. Nothing is overwritten and the output folder must be empty.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import validate_blueprint as blueprint_rules  # noqa: E402

SEGMENTER = "facebook/sam-vit-base"
PROMPTS = {  # object class -> the phrases the detector is asked for; every class but `other` has some. No word belongs to two classes (a label is mapped to a class by its words).
    # Measured on a real mockup (plan V-34): a longer list (shrub, topiary, signboard, banner, mailbox, lamp post, railing, sidewalk, parking lot ...) scored a lower F1 against the
    # reference, 0.47 against 0.50, even with fewer phrases per pass; signs improved and openings, lighting and props fell. This list is the best of those tried.
    "character": ["person"],
    "vehicle": ["car", "van", "bicycle"],
    "building": ["building"],
    "plant": ["tree", "bush", "hedge", "flower pot"],
    "sign": ["sign"],
    "street_furniture": ["bench", "litter bin", "bollard", "bike rack"],
    "lighting": ["street lamp", "lantern"],
    "barrier": ["fence", "gate"],
    "opening": ["door", "window"],
    "prop": ["crate", "ball", "traffic cone"],
    "structure_part": ["chimney", "awning"],
    "street": ["road", "pavement", "pedestrian crossing"],
    "parking": ["parking bay"],
}
PHRASES_PER_PASS = 9
SAME_CLASS_OVERLAP = 0.5       # intersection over union at or above which two boxes of one class are one object
CONTAINED = 0.9                # a same-class box with this share of its area inside a better one is a fragment of it
CROSS_CLASS_OVERLAP = 0.75     # near-identical boxes of two classes are one object: the better score names it
MIN_SIDE = 6                   # pixels: a box thinner than this is noise
MASK_SHARE = 0.3               # the mask's box replaces the detector's box when the mask covers at least this share of it
AREA_CLASSES = {"street", "parking", "building", "barrier"}   # large or long by nature (a fence run, a road): not flagged oversized
OVERSIZED = 0.02               # share of the picture above which a box of any other class is probably several objects in one (a tree is about 1%; a row of trees is more)
TINY_SIDE = 12                 # pixels: a box thinner than this is probably a fragment
LOW_SCORE = 0.35
WEAK_MASK = 0.5                # a mask covering less than this share of the detector's box is weak
EXCLUDED_SHARE = 0.5           # a detection with at least this share of its area inside an excluded region is dropped
MOVABLE = {"character", "vehicle"}
OPEN = {"opening"}


def phrase_class():
    return {phrase: cls for cls, phrases in PROMPTS.items() for phrase in phrases}


def class_of_label(label):
    """(class, ambiguous) for a label the detector returned: the class whose phrases cover most of the label's words (a label can be several phrases run together, such as
    'tree bush'); None when no word matches. Ambiguous when the words belong to more than one class (the first word's class wins)."""
    words = label.lower().replace(".", " ").split()
    by_phrase = phrase_class()
    votes, order = {}, []
    for word in words:
        for phrase, cls in by_phrase.items():
            if word in phrase.split():
                votes[cls] = votes.get(cls, 0) + 1
                if cls not in order:
                    order.append(cls)
                break
    if not votes:
        return None, False
    best = max(order, key=lambda cls: (votes[cls], -order.index(cls)))
    return best, len(votes) > 1


def overlap(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def inside(a, b):
    """The share of box a's area that lies inside box b."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    area = (a[2] - a[0]) * (a[3] - a[1])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) / area if area > 0 else 0.0


def parse_region(text):
    """'x,y,w,h' as four whole numbers [x, y, w, h]; refuses anything else."""
    try:
        parts = [int(v) for v in text.split(",")]
    except ValueError:
        parts = []
    if len(parts) != 4 or parts[2] < 1 or parts[3] < 1 or parts[0] < 0 or parts[1] < 0:
        raise ValueError(f"'{text}' is not a region: write X,Y,W,H as whole numbers with a positive width and height")
    return parts


def cluster_runs(per_run):
    """Combine the survivors of several runs: a box of the same class that overlaps an earlier (better) one is that object seen again. `per_run` is a list of merged survivor lists;
    returns one list, best score first, each with `seen_in` (how many runs found it) and `runs_total`."""
    clusters = []
    ranked = sorted(((run, item) for run, items in enumerate(per_run) for item in items), key=lambda pair: -pair[1]["score"])
    for run, item in ranked:
        home = next((c for c in clusters if c["object_class"] == item["object_class"] and overlap(item["box"], c["box"]) >= SAME_CLASS_OVERLAP), None)
        if home is None:
            clusters.append(dict(item, _runs={run}))
        else:
            home["_runs"].add(run)
            for alternative in item.get("alternatives", []):
                home.setdefault("alternatives", []).append(alternative)
    for cluster in clusters:
        cluster["seen_in"] = len(cluster.pop("_runs"))
        cluster["runs_total"] = len(per_run)
    return clusters


def review_flags(item, size):
    """Why a detection should be looked at again, from what the step knows: a list of short reasons (empty when nothing stands out)."""
    flags = []
    x, y, w, h = item["region"]
    if item["object_class"] not in AREA_CLASSES and w * h > OVERSIZED * size[0] * size[1]:
        flags.append("oversized")
    if min(w, h) < TINY_SIDE:
        flags.append("tiny")
    if item["score"] < LOW_SCORE:
        flags.append("low_score")
    if item["mask"] is None:
        flags.append("no_mask")
    elif item.get("mask_share", 1.0) < WEAK_MASK:
        flags.append("weak_mask")
    if item.get("ambiguous"):
        flags.append("ambiguous_label")
    if item.get("runs_total", 1) > 1 and item.get("seen_in", 1) == 1:
        flags.append("seen_once")
    return flags


def merge(raw):
    """Merge raw detections {"object_class", "phrase", "score", "box": [x0, y0, x1, y1]} into one entry per object: same-class overlaps and fragments are dropped in favour of the
    higher score, and a near-identical box of another class is recorded as an alternative of the better one. Returns the survivors, best score first."""
    sized = [d for d in raw if d["box"][2] - d["box"][0] >= MIN_SIDE and d["box"][3] - d["box"][1] >= MIN_SIDE]
    kept = []
    for item in sorted(sized, key=lambda d: -d["score"]):
        same = [k for k in kept if k["object_class"] == item["object_class"]]
        if any(overlap(item["box"], k["box"]) >= SAME_CLASS_OVERLAP or inside(item["box"], k["box"]) >= CONTAINED for k in same):
            continue
        twin = next((k for k in kept if k["object_class"] != item["object_class"] and overlap(item["box"], k["box"]) >= CROSS_CLASS_OVERLAP), None)
        if twin is not None:
            twin.setdefault("alternatives", []).append({"object_class": item["object_class"], "phrase": item["phrase"], "score": round(item["score"], 3)})
            continue
        kept.append(dict(item))
    return kept


def tile_boxes(size, n, margin=0.08):
    """The whole picture, then an n x n grid of tiles that overlap by `margin` of the picture; [(x0, y0, x1, y1)]. n = 1 is the whole picture only."""
    width, height = size
    tiles = [(0, 0, width, height)]
    if n > 1:
        for row in range(n):
            for col in range(n):
                tiles.append((max(0, round(col * width / n - margin * width)), max(0, round(row * height / n - margin * height)),
                              min(width, round((col + 1) * width / n + margin * width)), min(height, round((row + 1) * height / n + margin * height))))
    return tiles


# How each kind of object is searched for: mid-size objects over the picture and a grid of tiles, small objects over a finer grid (they are enlarged so the detector can see them), and
# long or area objects (a building, a street, a car park) over the whole picture only, because a tile cuts them into pieces. Every class but `other` is in exactly one pass.
PASSES = (("objects", ("character", "vehicle", "plant", "barrier", "structure_part", "opening", "lighting", "street_furniture"), "tiles"),
          ("small", ("sign", "prop"), "small_tiles"),
          ("area", ("building", "street", "parking"), None))
# Chosen by measurement on a real mockup (plan V-34), class by class: the whole-picture search for areas made buildings 2 of 2 with no false ones (it was 2 of 5) and found street and
# parking in one piece; the fine grid made signs 5 of 5 and props 2 of 5 but over-detected openings, lighting and street furniture, so those stay on the normal grid.


def groups_of_phrases(classes=None, variant=0, per_pass=PHRASES_PER_PASS, prompts=None):
    """The phrases of `classes` in passes of at most PHRASES_PER_PASS. Variant k starts the list k * 3 phrases further on, so the same phrases meet different neighbours in the prompt: the
    detector's answer depends on that composition, which is what a repeated run uses to tell a steady detection from a lucky one."""
    phrases = [p for cls, ps in (prompts or PROMPTS).items() if classes is None or cls in classes for p in ps]
    shift = (variant * 3) % len(phrases) if phrases else 0
    phrases = phrases[shift:] + phrases[:shift]
    return [phrases[i:i + per_pass] for i in range(0, len(phrases), per_pass)]


def need(*modules):
    missing = []
    for name in modules:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise ValueError("the detection step needs " + ", ".join(missing) + " (an optional extra: pip install torch transformers); it is not a dependency of the framework and nothing was run")


class GroundingDino:
    """The open-vocabulary detector: asked for phrases, it returns boxes with scores and the phrase it matched."""

    def __init__(self, model_id, device):
        need("torch", "transformers")
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        self.id, self.device, self.torch = model_id, device, torch
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device).eval()

    def find(self, image, phrases, box_threshold, text_threshold):
        text = ". ".join(phrases) + "."
        inputs = self.processor(images=image, text=text, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        result = self.processor.post_process_grounded_object_detection(outputs, inputs.input_ids, threshold=box_threshold, text_threshold=text_threshold,
                                                                       target_sizes=[image.size[::-1]])[0]
        labels = result.get("text_labels") or result["labels"]
        return [{"label": label, "score": float(score), "box": [float(v) for v in box]} for box, score, label in zip(result["boxes"].tolist(), result["scores"].tolist(), labels)]


class Owlv2:
    """The other open-vocabulary detector: OWLv2 scores every phrase against every part of the picture on its own (no shared prompt, so no limit on phrases per pass and no dependence
    on how they are grouped), and answers with the exact phrase. Its scores are of another scale than Grounding DINO's, which is why the two have their own default thresholds."""

    phrases_per_pass = 64
    # Phrases that suit this detector better than the shared ones, per class (measured: for a car park, "parking space" and "painted parking lines" found 4 of 10 where "parking bay" found none)
    prompts = {"parking": ["parking bay", "parking space", "painted parking lines"]}

    def __init__(self, model_id, device):
        need("torch", "transformers")
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
        self.id, self.device, self.torch = model_id, device, torch
        self.processor = Owlv2Processor.from_pretrained(model_id)
        self.model = Owlv2ForObjectDetection.from_pretrained(model_id).to(device).eval()

    def find(self, image, phrases, box_threshold, text_threshold):
        inputs = self.processor(text=[phrases], images=image, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        side = max(image.size)  # the picture is padded to a square before it is looked at; boxes are in that square, which keeps the crop's own pixel scale
        result = self.processor.post_process_grounded_object_detection(outputs, threshold=box_threshold, target_sizes=[(side, side)], text_labels=[phrases])[0]
        return [{"label": label, "score": float(score), "box": [float(v) for v in box]} for box, score, label in zip(result["boxes"].tolist(), result["scores"].tolist(), result["text_labels"])]


# detector kind -> (class, default model, default box threshold, default text threshold): the thresholds are of different scales, so each kind has its own measured default
DETECTORS = {"grounding-dino": (GroundingDino, "IDEA-Research/grounding-dino-tiny", 0.25, 0.2),
             "owlv2": (Owlv2, "google/owlv2-base-patch16-ensemble", 0.15, 0.0)}


def resolve_detector(kind, model, box_threshold, text_threshold):
    """(class, model id, box threshold, text threshold) for a detector kind, taking the kind's default for anything not given."""
    if kind not in DETECTORS:
        raise ValueError(f"unknown detector kind {kind}: " + ", ".join(sorted(DETECTORS)))
    cls, default_model, default_box, default_text = DETECTORS[kind]
    return cls, model or default_model, default_box if box_threshold is None else box_threshold, default_text if text_threshold is None else text_threshold


def also_detector(spec, device):
    """(detector, classes, box threshold, text threshold) for an --also KIND:CLASS,CLASS option; refuses a kind or a class that does not exist."""
    kind, _, names = spec.partition(":")
    classes = [c for c in names.split(",") if c]
    if not classes:
        raise ValueError(f"--also {spec}: name the classes the second detector answers for, KIND:CLASS,CLASS")
    unknown = [c for c in classes if c not in PROMPTS]
    if unknown:
        raise ValueError(f"--also {spec}: no detection prompt for the class {', '.join(unknown)}; the classes are " + ", ".join(PROMPTS))
    cls, model, box, text = resolve_detector(kind, None, None, None)
    return cls(model, device), classes, box, text


class Sam:
    """The segmenter: given boxes, an accurate mask for each, as "L" pictures the size of the picture (255 inside the object)."""

    def __init__(self, model_id, device):
        need("torch", "transformers")
        import torch
        from PIL import Image
        from transformers import SamModel, SamProcessor
        self.id, self.device, self.torch = model_id, device, torch
        self.processor = SamProcessor.from_pretrained(model_id)
        self.model = SamModel.from_pretrained(model_id).to(device).eval()

    def masks(self, image, boxes, chunk=24):
        from PIL import Image
        inputs = self.processor(image, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            embeddings = self.model.get_image_embeddings(inputs["pixel_values"])
        out = []
        for start in range(0, len(boxes), chunk):
            part = [list(map(float, b)) for b in boxes[start:start + chunk]]
            prompt = self.processor(image, input_boxes=[part], return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                result = self.model(image_embeddings=embeddings, input_boxes=prompt["input_boxes"], multimask_output=False)
            masks = self.processor.image_processor.post_process_masks(result.pred_masks.cpu(), prompt["original_sizes"].cpu(), prompt["reshaped_input_sizes"].cpu())[0]
            out += [Image.fromarray((m[0].numpy() * 255).astype("uint8"), "L") for m in masks]  # the only place the framework meets numpy: inside the optional model wrapper
        return out


def detect(image, detector, segmenter, tiles=2, box_threshold=0.25, text_threshold=0.2, exclude=(), small_tiles=4, runs=1, min_runs=1, extras=()):
    """Run the detector over the picture (whole and tiled), merge, drop what lies in an excluded region, and segment: returns (detections, raw_count, unmatched, excluded). A detection is
    {id, object_class, phrase, score, region [x, y, w, h], mask (a PIL "L" picture the size of the region, or None), mask_share, flags, alternatives, ambiguous}. `detector` and `segmenter` are objects with `find` and `masks`, so a test can supply its own."""
    if runs < 1 or not 1 <= min_runs <= runs:
        raise ValueError("runs is at least 1 and min_runs is between 1 and runs")
    unmatched, raw_count, per_run = [], 0, []
    grids = {"tiles": tiles, "small_tiles": small_tiles, None: 1}

    def search(finder, only, variant, box_thr, text_thr, prompts=None):
        """The raw detections of `finder` for the classes in `only` (all when None), each class searched with its own pass plan."""
        raw = []
        per_pass = getattr(finder, "phrases_per_pass", PHRASES_PER_PASS)
        plan = [(box, phrases) for _, classes, grid in PASSES for box in tile_boxes(image.size, grids[grid])
                for phrases in groups_of_phrases([c for c in classes if only is None or c in only], variant, per_pass, prompts) if phrases]
        for (x0, y0, x1, y1), phrases in plan:
            for found in finder.find(image.crop((x0, y0, x1, y1)), phrases, box_thr, text_thr):
                cls, ambiguous = class_of_label(found["label"])
                box = [found["box"][0] + x0, found["box"][1] + y0, found["box"][2] + x0, found["box"][3] + y0]
                if cls is None:
                    unmatched.append({"label": found["label"], "score": round(found["score"], 3), "box": [round(v) for v in box]})
                    continue
                raw.append({"object_class": cls, "phrase": found["label"], "score": found["score"], "box": box, "ambiguous": ambiguous})
        return raw

    for variant in range(runs):
        raw = search(detector, None, variant, box_threshold, text_threshold)
        raw_count += len(raw)
        per_run.append(merge(raw))
    agreed = [c for c in cluster_runs(per_run) if c["seen_in"] >= min_runs]
    for finder, only, box_thr, text_thr in extras:
        # the second detector answers for its classes alone: the first detector's findings of those classes are replaced, not added to (measured: adding both doubled the false ones)
        raw = search(finder, only, 0, box_thr, text_thr, dict(PROMPTS, **getattr(finder, "prompts", {})))
        raw_count += len(raw)
        agreed = [c for c in agreed if c["object_class"] not in only] + [dict(item, seen_in=1, runs_total=1) for item in merge(raw)]
    survivors, excluded = [], []
    for item in agreed:
        zone = next((r for r in exclude if inside(item["box"], [r[0], r[1], r[0] + r[2], r[1] + r[3]]) >= EXCLUDED_SHARE), None)
        if zone is None:
            survivors.append(item)
        else:
            excluded.append({"object_class": item["object_class"], "phrase": item["phrase"], "score": round(item["score"], 3), "box": [round(v) for v in item["box"]], "region": zone})
    width, height = image.size
    masks = segmenter.masks(image, [d["box"] for d in survivors]) if survivors else []
    detections = []
    for item, mask in zip(survivors, masks):
        x0, y0, x1, y1 = (max(0, int(item["box"][0])), max(0, int(item["box"][1])), min(width, int(round(item["box"][2]))), min(height, int(round(item["box"][3]))))
        region, picture, share = [x0, y0, x1 - x0, y1 - y0], None, 0.0
        inside_box = mask.crop((x0, y0, x1, y1)).point(lambda v: 255 if v >= 128 else 0)
        found = inside_box.getbbox()
        share = inside_box.histogram()[255] / max(1, (x1 - x0) * (y1 - y0))
        if found and share >= MASK_SHARE:
            mx0, my0, mx1, my1 = x0 + found[0], y0 + found[1], x0 + found[2], y0 + found[3]
            region = [mx0, my0, mx1 - mx0, my1 - my0]
            picture = mask.crop((mx0, my0, mx1, my1)).point(lambda v: 255 if v >= 128 else 0)
        detections.append(dict(item, region=region, mask=picture, mask_share=round(share, 3)))
    for item in detections:
        item["flags"] = review_flags(item, image.size)
    detections.sort(key=lambda d: (d["region"][1], d["region"][0]))
    counters = {}
    for item in detections:
        counters[item["object_class"]] = counters.get(item["object_class"], 0) + 1
        item["id"] = f"{item['object_class']}_{counters[item['object_class']]:02d}"
    return detections, raw_count, unmatched, excluded


def build_blueprint(detections, size, mockup_id, revision, mockup_sha256, detector_id, segmenter_id, tiles, box_threshold, text_threshold, excluded=(), small_tiles=4):
    """The draft blueprint for a set of detections: pending, every object inferred with the detector's score, the sweep, and the mask each object has."""
    scene = {"element_id": "scene", "scope": "scene", "evidence_status": "inferred", "coordinate_system": f"image pixels ({size[0]} x {size[1]})",
             "observed_details": {"how": "objects found by a detection model, not yet reviewed", "detector": detector_id, "segmenter": segmenter_id, "tiles": tiles, "small_tiles": small_tiles, "passes": [[name, list(classes)] for name, classes, _ in PASSES],
                                  "box_threshold": box_threshold, "text_threshold": text_threshold, "prompts": PROMPTS},
             "motion_candidates": [], "production_strategy": "separate every object found; ground and open surfaces stay tiles or materials",
             "separation_inventory": [], "parent_cleanup": {"required": True, "status": "pending"}}
    elements, by_class = [scene], {}
    for d in detections:
        evidence = f"detected by {detector_id} for '{d['phrase']}' (score {d['score']:.2f}) at {d['region']}" + (f"; mask by {segmenter_id}" if d["mask"] else "; no usable mask: the detector's box")
        elements.append({"element_id": d["id"], "scope": "asset", "parent_id": "scene", "source_region_px": d["region"], "coordinate_system": scene["coordinate_system"],
                         "evidence_status": "inferred", "confidence": round(d["score"], 3),
                         "observed_details": {"phrase": d["phrase"], "object_class": d["object_class"], "alternatives": d.get("alternatives", []), "ambiguous_label": d.get("ambiguous", False),
                                              "review_flags": d["flags"], "mask_share": d["mask_share"], "seen_in": d.get("seen_in", 1), "runs": d.get("runs_total", 1)},
                         "motion_candidates": [], "production_strategy": "separate sprite from the parent; the clean plate shows what lay behind it",
                         "asset_class": "mobile_directional" if d["object_class"] in MOVABLE else "prop", "output_ids": [f"{d['id']}_sprite"]})
        component = {"component_id": d["id"], "ownership": ["independent_prop"] + (["movable"] if d["object_class"] in MOVABLE else []) + (["interactive"] if d["object_class"] in OPEN else []),
                     "object_class": d["object_class"], "source_evidence": evidence, "static_parent_action": "exclude", "sprite_output_id": f"{d['id']}_sprite", "visual_status": "pending"}
        if d["mask"]:
            component["removal_mask_ref"] = f"masks/{d['id']}.png"
        scene["separation_inventory"].append(component)
        by_class.setdefault(d["object_class"], []).append(d["id"])
    sweep = []
    for cls in blueprint_rules.object_classes():
        if by_class.get(cls):
            sweep.append({"object_class": cls, "status": "present", "component_ids": by_class[cls], "evidence": f"{len(by_class[cls])} found by the detector, listed with their regions"})
        else:
            prompts = PROMPTS.get(cls)
            sweep.append({"object_class": cls, "status": "absent", "evidence": (f"the detector found nothing above its thresholds for {prompts}: its finding, not a visual audit" if prompts
                                                                                  else "this class has no detection prompt, so the detector could not look for it: it needs the analyzer's own audit")})
    return {"schema_version": "1.0", "mockup_id": mockup_id, "mockup_revision": revision, "approval_status": "pending_approval", "scope": "scene",
            "source_ref": f"sha256 {mockup_sha256}", "elements": elements, "object_sweep": sweep,
            "coverage_audit": {"status": "pending_review", "unassigned_regions": [],
                               "intentional_exclusions": [{"what": f"{e['object_class']} '{e['phrase']}' found inside the excluded region {e['region']}", "why": "named by the analyzer as interface, not scene"}
                                                          for e in excluded],
                               "unknowns": ["whether the detector missed objects or saw ones that are not there: the draft must be reviewed against the picture",
                                            "what lies behind every separated object: unknown until a clean plate is made and reviewed"]}}


def run(mockup_path, output_dir, mockup_id, revision, detector, segmenter, tiles=2, box_threshold=0.25, text_threshold=0.2, exclude=(), small_tiles=4, runs=1, min_runs=1, extras=()):
    """Detect, segment and write the draft blueprint, the masks and the raw findings into an empty folder; returns the summary."""
    from PIL import Image
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"{output_dir} is not empty; a detection never writes into a folder that has something in it")
    with Image.open(mockup_path) as opened:
        image = opened.convert("RGB")
    detections, raw_count, unmatched, excluded = detect(image, detector, segmenter, tiles, box_threshold, text_threshold, exclude, small_tiles, runs, min_runs, extras)
    if not detections:
        raise ValueError("the detector found no object: lower the thresholds, or the picture has none of the prompted classes")
    sha = hashlib.sha256(Path(mockup_path).read_bytes()).hexdigest()
    draft = build_blueprint(detections, image.size, mockup_id, revision, sha, detector.id, segmenter.id, tiles, box_threshold, text_threshold, excluded, small_tiles)
    common.validate_schema(draft, "mockup-blueprint")
    problems = blueprint_rules.sweep_problems(draft)
    if problems:
        raise ValueError("the draft's sweep is inconsistent (a defect of this step): " + "; ".join(problems))
    (output_dir / "masks").mkdir(parents=True, exist_ok=True)
    for d in detections:
        if d["mask"]:
            d["mask"].save(output_dir / "masks" / f"{d['id']}.png")
    common.atomic_write_json(output_dir / "detected.blueprint.json", draft)
    per_class = {}
    for d in detections:
        per_class[d["object_class"]] = per_class.get(d["object_class"], 0) + 1
    findings = {"detector": detector.id, "segmenter": segmenter.id, "raw_detections": raw_count, "kept": len(detections), "per_class": per_class, "unmatched_labels": unmatched,
                "with_mask": sum(1 for d in detections if d["mask"]), "excluded": excluded, "flagged": sum(1 for d in detections if d["flags"]),
                "flags": {f: sum(1 for d in detections if f in d["flags"]) for f in sorted({f for d in detections for f in d["flags"]})}, "thresholds": {"box": box_threshold, "text": text_threshold}, "tiles": tiles, "small_tiles": small_tiles, "runs": runs, "min_runs": min_runs,
                "objects": [{"id": d["id"], "object_class": d["object_class"], "phrase": d["phrase"], "score": round(d["score"], 3), "region_px": d["region"], "review_flags": d["flags"], "seen_in": d.get("seen_in", 1),
                             "alternatives": d.get("alternatives", [])} for d in detections],
                "not_assessed": ["whether the detector missed objects or saw ones that are not there: a draft is reviewed against the picture before it is relied on",
                                 "the accuracy of each mask beyond the detector and segmenter's own scores"]}
    common.atomic_write_json(output_dir / "detections.json", findings)
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    one = ops.add_parser("detect")
    one.add_argument("--mockup", type=Path, required=True)
    one.add_argument("--mockup-id", required=True)
    one.add_argument("--revision", required=True)
    one.add_argument("--output-dir", type=Path, required=True)
    one.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    one.add_argument("--tiles", type=int, default=2, help="search mid-size objects over the picture whole and an N x N grid of overlapping tiles (1 = whole only)")
    one.add_argument("--also", action="append", default=[], metavar="KIND:CLASS,CLASS", help="let a second detector answer for these classes alone, e.g. owlv2:street_furniture,lighting,parking (measured: it finds far more of them than Grounding DINO)")
    one.add_argument("--runs", type=int, default=1, help="run the detection this many times with the phrases grouped differently (the detector's answer depends on the grouping)")
    one.add_argument("--min-runs", type=int, default=1, help="keep only objects found in at least this many runs: raises precision at the cost of recall; the rest are flagged seen_once")
    one.add_argument("--small-tiles", type=int, default=4, help="search small objects (bollards, signs, windows, props) over an N x N grid: they are enlarged so the detector can see them")
    one.add_argument("--detector-kind", choices=sorted(DETECTORS), default="grounding-dino")
    one.add_argument("--box-threshold", type=float, default=None, help="the detector kind's own default when not given")
    one.add_argument("--text-threshold", type=float, default=None, help="the detector kind's own default when not given (Grounding DINO only)")
    one.add_argument("--exclude-region", action="append", default=[], metavar="X,Y,W,H", help="where an interface overlay is (repeatable): detections inside it are dropped and recorded")
    one.add_argument("--detector", default=None, help="the model id (the kind's default when not given)")
    one.add_argument("--segmenter", default=SEGMENTER)
    args = parser.parse_args()
    try:
        need("torch", "transformers")
        import torch
        device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("--device cuda was asked for and this PyTorch has no CUDA")
        detector_class, model, box_threshold, text_threshold = resolve_detector(args.detector_kind, args.detector, args.box_threshold, args.text_threshold)
        findings = run(args.mockup, args.output_dir, args.mockup_id, args.revision, detector_class(model, device), Sam(args.segmenter, device), args.tiles,
                       box_threshold, text_threshold, [parse_region(r) for r in args.exclude_region], args.small_tiles, args.runs, args.min_runs,
                       [also_detector(spec, device) for spec in args.also])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps({k: findings[k] for k in ("detector", "segmenter", "raw_detections", "kept", "per_class", "with_mask", "flagged", "flags", "excluded", "not_assessed")}, indent=2))


if __name__ == "__main__":
    main()
