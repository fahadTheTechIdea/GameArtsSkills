"""The detection step of the mockup analyzer: prompts, merging, tiling, masks and the draft blueprint, with stand-in models; the real models only when asked."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from PIL import Image, ImageDraw  # noqa: E402

import detect_scene_objects as detector_step  # noqa: E402
import extract_scene_objects as extractor  # noqa: E402
import gamearts_common as common  # noqa: E402
import validate_blueprint as blueprint_rules  # noqa: E402

SCRIPT_VALIDATE = ROOT / "scripts" / "validate_blueprint.py"
REAL = os.environ.get("GAMEARTS_DETECTION_E2E")  # set to run the real models (an optional extra: torch, transformers and the models' weights)


class FakeDetector:
    id = "fake-detector"

    def __init__(self, answers):
        self.answers = answers          # a function (crop size, phrases) -> list of {"label", "score", "box"} in the crop's own pixels
        self.calls = []

    def find(self, image, phrases, box_threshold, text_threshold):
        self.calls.append((image.size, tuple(phrases)))
        return self.answers(image.size, phrases)


class FakeSegmenter:
    id = "fake-segmenter"

    def __init__(self, shape="full"):
        self.shape = shape

    def masks(self, image, boxes):
        out = []
        for x0, y0, x1, y1 in boxes:
            mask = Image.new("L", image.size, 0)
            draw = ImageDraw.Draw(mask)
            x0, y0, x1, y1 = int(x0), int(y0), int(round(x1)), int(round(y1))
            if self.shape == "full":
                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
            elif self.shape == "inner":                                      # only the middle of the box: the mask's own box is tighter
                draw.rectangle((x0 + 4, y0 + 4, x1 - 5, y1 - 5), fill=255)
            elif self.shape == "speck":                                      # a mask far smaller than the box: not trusted
                draw.rectangle((x0, y0, x0 + 1, y0 + 1), fill=255)
            out.append(mask)
        return out


def person_everywhere(size, phrases):
    return [{"label": "person", "score": 0.9, "box": [10.0, 10.0, 30.0, 50.0]}] if "person" in phrases else []


class VocabularyTests(unittest.TestCase):
    def test_every_class_but_other_has_prompts_and_the_classes_are_the_contracts(self):
        classes = blueprint_rules.object_classes()
        self.assertEqual(sorted(detector_step.PROMPTS), sorted(c for c in classes if c != "other"))
        self.assertTrue(all(detector_step.PROMPTS[c] for c in detector_step.PROMPTS))

    def test_a_phrase_belongs_to_one_class_only(self):
        phrases = [p for ps in detector_step.PROMPTS.values() for p in ps]
        self.assertEqual(len(phrases), len(set(phrases)))

    def test_no_word_belongs_to_two_classes_so_a_label_maps_to_one_class(self):
        owners = {}
        for cls, phrases in detector_step.PROMPTS.items():
            for phrase in phrases:
                for word in phrase.split():
                    owners.setdefault(word, set()).add(cls)
        self.assertEqual({w: c for w, c in owners.items() if len(c) > 1}, {})

    def test_every_class_but_other_is_searched_in_exactly_one_pass(self):
        classes = [c for _, cs, _ in detector_step.PASSES for c in cs]
        self.assertEqual(sorted(classes), sorted(c for c in blueprint_rules.object_classes() if c != "other"))
        self.assertEqual({grid for _, _, grid in detector_step.PASSES}, {"tiles", "small_tiles", None})

    def test_the_prompts_are_asked_in_passes_that_fit_and_each_phrase_once(self):
        groups = detector_step.groups_of_phrases()
        self.assertTrue(all(len(g) <= detector_step.PHRASES_PER_PASS for g in groups))
        self.assertEqual(sorted(p for g in groups for p in g), sorted(p for ps in detector_step.PROMPTS.values() for p in ps))

    def test_a_label_is_given_the_class_whose_phrases_it_matches_most(self):
        self.assertEqual(detector_step.class_of_label("person"), ("character", False))
        self.assertEqual(detector_step.class_of_label("car van"), ("vehicle", False))
        self.assertEqual(detector_step.class_of_label("tree bush hedge"), ("plant", False))
        self.assertEqual(detector_step.class_of_label("flower"), ("plant", False))
        self.assertEqual(detector_step.class_of_label("tree sign"), ("plant", True))        # words of two classes: the first wins and it is marked ambiguous
        self.assertEqual(detector_step.class_of_label("spaceship"), (None, False))


class GeometryTests(unittest.TestCase):
    def test_overlap_and_containment(self):
        self.assertEqual(detector_step.overlap([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(detector_step.overlap([0, 0, 10, 10], [10, 0, 20, 10]), 0.0)
        self.assertAlmostEqual(detector_step.overlap([0, 0, 10, 10], [5, 0, 15, 10]), 50 / 150)
        self.assertEqual(detector_step.inside([2, 2, 4, 4], [0, 0, 10, 10]), 1.0)
        self.assertEqual(detector_step.inside([8, 0, 12, 4], [0, 0, 10, 10]), 0.5)

    def test_tiles_cover_the_picture_overlap_and_stay_inside_it(self):
        self.assertEqual(detector_step.tile_boxes((100, 60), 1), [(0, 0, 100, 60)])
        tiles = detector_step.tile_boxes((100, 60), 2)
        self.assertEqual(len(tiles), 5)
        self.assertEqual(tiles[0], (0, 0, 100, 60))
        self.assertTrue(all(0 <= x0 < x1 <= 100 and 0 <= y0 < y1 <= 60 for x0, y0, x1, y1 in tiles))
        self.assertTrue(tiles[1][2] > 50 and tiles[2][0] < 50)                              # neighbouring tiles overlap
        self.assertEqual((tiles[1][0], tiles[1][1], tiles[4][2], tiles[4][3]), (0, 0, 100, 60))


class MergeTests(unittest.TestCase):
    def item(self, cls, score, box, phrase="x"):
        return {"object_class": cls, "phrase": phrase, "score": score, "box": box}

    def test_the_better_of_two_boxes_of_one_class_on_the_same_object_survives(self):
        kept = detector_step.merge([self.item("plant", 0.5, [0, 0, 40, 40]), self.item("plant", 0.8, [2, 2, 42, 42])])
        self.assertEqual([k["score"] for k in kept], [0.8])

    def test_a_fragment_inside_a_better_box_of_its_class_is_dropped_but_a_neighbour_is_kept(self):
        kept = detector_step.merge([self.item("plant", 0.9, [0, 0, 100, 100]), self.item("plant", 0.6, [10, 10, 30, 30]), self.item("plant", 0.6, [120, 0, 160, 40])])
        self.assertEqual(sorted(k["box"][0] for k in kept), [0, 120])

    def test_a_near_identical_box_of_another_class_becomes_an_alternative_of_the_better_one(self):
        kept = detector_step.merge([self.item("plant", 0.7, [0, 0, 40, 40], "tree"), self.item("sign", 0.4, [1, 1, 40, 40], "sign")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["object_class"], "plant")
        self.assertEqual(kept[0]["alternatives"][0]["object_class"], "sign")

    def test_boxes_of_different_classes_that_only_overlap_in_part_are_both_kept(self):
        kept = detector_step.merge([self.item("character", 0.9, [20, 20, 40, 60]), self.item("opening", 0.8, [0, 0, 100, 80])])
        self.assertEqual(sorted(k["object_class"] for k in kept), ["character", "opening"])

    def test_a_box_thinner_than_the_minimum_is_noise(self):
        self.assertEqual(detector_step.merge([self.item("plant", 0.9, [0, 0, 3, 50])]), [])


class DetectTests(unittest.TestCase):
    def image(self):
        return Image.new("RGB", (200, 120), (90, 120, 90))

    def test_detections_in_a_tile_are_placed_by_the_tiles_own_origin(self):
        detections, raw, unmatched, _ = detector_step.detect(self.image(), FakeDetector(person_everywhere), FakeSegmenter(), tiles=2)
        regions = sorted(d["region"][:2] for d in detections)
        self.assertEqual(raw, 5)                                                              # one per tile and one for the whole picture
        self.assertIn([10, 10], regions)                                                     # the whole picture's own
        self.assertTrue(any(r[0] > 80 or r[1] > 40 for r in regions))                        # a tile's, offset by its origin

    def test_a_label_the_prompts_do_not_explain_is_reported_not_kept(self):
        answers = lambda size, phrases: [{"label": "spaceship", "score": 0.9, "box": [10.0, 10.0, 40.0, 40.0]}, {"label": "person", "score": 0.8, "box": [50.0, 50.0, 70.0, 90.0]}] if "person" in phrases else []
        detections, _, unmatched, _ = detector_step.detect(self.image(), FakeDetector(answers), FakeSegmenter(), tiles=1)
        self.assertEqual([d["object_class"] for d in detections], ["character"])
        self.assertEqual(unmatched[0]["label"], "spaceship")

    def test_a_mask_tightens_the_region_and_a_tiny_mask_falls_back_to_the_detectors_box(self):
        tight, _, _, _ = detector_step.detect(self.image(), FakeDetector(person_everywhere), FakeSegmenter("inner"), tiles=1)
        self.assertEqual(tight[0]["region"], [14, 14, 12, 32])
        self.assertEqual(tight[0]["mask"].size, (12, 32))
        loose, _, _, _ = detector_step.detect(self.image(), FakeDetector(person_everywhere), FakeSegmenter("speck"), tiles=1)
        self.assertEqual(loose[0]["region"], [10, 10, 20, 40])
        self.assertIsNone(loose[0]["mask"])

    def test_ids_count_up_per_class_in_reading_order(self):
        answers = lambda size, phrases: ([{"label": "person", "score": 0.9, "box": [100.0, 10.0, 120.0, 50.0]}, {"label": "person", "score": 0.9, "box": [10.0, 60.0, 30.0, 100.0]},
                                          {"label": "person", "score": 0.9, "box": [40.0, 10.0, 60.0, 50.0]}] if "person" in phrases else [])
        detections, _, _, _ = detector_step.detect(self.image(), FakeDetector(answers), FakeSegmenter(), tiles=1)
        self.assertEqual([(d["id"], d["region"][:2]) for d in detections], [("character_01", [40, 10]), ("character_02", [100, 10]), ("character_03", [10, 60])])

    def test_the_detector_is_asked_every_phrase_of_every_class_and_each_pass_uses_its_own_grid(self):
        detector = FakeDetector(person_everywhere)
        detector_step.detect(self.image(), detector, FakeSegmenter(), tiles=2, small_tiles=3)
        asked = {phrase for _, phrases in detector.calls for phrase in phrases}
        self.assertEqual(asked, {p for ps in detector_step.PROMPTS.values() for p in ps})
        grids = {"tiles": 2, "small_tiles": 3, None: 1}
        expected = sum(len(detector_step.tile_boxes(self.image().size, grids[grid])) * len(detector_step.groups_of_phrases(classes)) for _, classes, grid in detector_step.PASSES)
        self.assertEqual(len(detector.calls), expected)

    def test_a_long_or_area_object_is_searched_for_over_the_whole_picture_only_and_never_in_tiles(self):
        detector = FakeDetector(lambda size, phrases: [])
        image = self.image()
        detector_step.detect(image, detector, FakeSegmenter(), tiles=2, small_tiles=4)
        area_phrases = {p for cls in ("building", "street", "parking") for p in detector_step.PROMPTS[cls]}
        sizes = {size for size, phrases in detector.calls if set(phrases) & area_phrases}
        self.assertEqual(sizes, {image.size})

    def test_a_small_object_is_searched_for_in_crops_smaller_than_a_mid_size_objects(self):
        detector = FakeDetector(lambda size, phrases: [])
        image = self.image()
        detector_step.detect(image, detector, FakeSegmenter(), tiles=2, small_tiles=4)
        small = {size for size, phrases in detector.calls if "sign" in phrases}
        mid = {size for size, phrases in detector.calls if "tree" in phrases}
        self.assertLess(max(w for w, _ in small if w < image.width), min(w for w, _ in mid if w < image.width))


class ReviewTests(unittest.TestCase):
    SIZE = (1000, 600)

    def item(self, cls="character", score=0.9, region=(10, 10, 20, 40), mask=True, share=1.0, ambiguous=False):
        return {"object_class": cls, "score": score, "region": list(region), "mask": Image.new("L", (1, 1)) if mask else None, "mask_share": share, "ambiguous": ambiguous}

    def test_a_clean_detection_has_no_flags(self):
        self.assertEqual(detector_step.review_flags(self.item(), self.SIZE), [])

    def test_each_reason_to_look_again_is_flagged(self):
        self.assertEqual(detector_step.review_flags(self.item("plant", region=(0, 0, 200, 200)), self.SIZE), ["oversized"])
        self.assertEqual(detector_step.review_flags(self.item("plant", region=(0, 0, 90, 100)), self.SIZE), [])                   # 1.5% of the picture is about one tree's share, not several
        self.assertEqual(detector_step.review_flags(self.item(region=(10, 10, 8, 40)), self.SIZE), ["tiny"])
        self.assertEqual(detector_step.review_flags(self.item(score=0.3), self.SIZE), ["low_score"])
        self.assertEqual(detector_step.review_flags(self.item(mask=False), self.SIZE), ["no_mask"])
        self.assertEqual(detector_step.review_flags(self.item(share=0.4), self.SIZE), ["weak_mask"])
        self.assertEqual(detector_step.review_flags(self.item(ambiguous=True), self.SIZE), ["ambiguous_label"])

    def test_a_street_a_car_park_a_building_and_a_fence_run_are_large_by_nature_and_not_flagged_oversized(self):
        for cls in ("street", "parking", "building", "barrier"):
            self.assertEqual(detector_step.review_flags(self.item(cls, region=(0, 0, 190, 110)), self.SIZE), [], cls)

    def test_a_region_to_exclude_is_four_whole_numbers(self):
        self.assertEqual(detector_step.parse_region("10,20,30,40"), [10, 20, 30, 40])
        for bad in ("10,20,30", "a,b,c,d", "10,20,0,40", "-1,0,5,5", ""):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "is not a region"):
                detector_step.parse_region(bad)

    def test_a_detection_inside_an_excluded_region_is_dropped_and_recorded_and_one_outside_is_kept(self):
        answers = lambda size, phrases: ([{"label": "sign", "score": 0.9, "box": [150.0, 10.0, 190.0, 30.0]}, {"label": "person", "score": 0.8, "box": [20.0, 50.0, 40.0, 90.0]}]
                                         if "person" in phrases else [])
        image = Image.new("RGB", (200, 120), (90, 120, 90))
        detections, _, _, excluded = detector_step.detect(image, FakeDetector(answers), FakeSegmenter(), tiles=1, exclude=[[140, 0, 60, 40]])
        self.assertEqual([d["object_class"] for d in detections], ["character"])
        self.assertEqual([(e["object_class"], e["region"]) for e in excluded], [("sign", [140, 0, 60, 40])])
        halfway = detector_step.detect(image, FakeDetector(answers), FakeSegmenter(), tiles=1, exclude=[[180, 0, 20, 40]])        # only a quarter of the sign lies inside
        self.assertEqual(sorted(d["object_class"] for d in halfway[0]), ["character", "sign"])


class DetectorKindTests(unittest.TestCase):
    def test_each_kind_has_its_own_defaults_and_a_kind_not_known_is_refused(self):
        cls, model, box, text = detector_step.resolve_detector("grounding-dino", None, None, None)
        self.assertEqual((cls, model, box, text), (detector_step.GroundingDino, "IDEA-Research/grounding-dino-tiny", 0.25, 0.2))
        cls, model, box, text = detector_step.resolve_detector("owlv2", None, None, None)
        self.assertEqual((cls, model, box), (detector_step.Owlv2, "google/owlv2-base-patch16-ensemble", 0.15))
        with self.assertRaisesRegex(ValueError, "unknown detector kind"):
            detector_step.resolve_detector("yolo", None, None, None)

    def test_a_model_and_thresholds_given_override_the_kinds_defaults(self):
        self.assertEqual(detector_step.resolve_detector("owlv2", "my/model", 0.3, 0.1)[1:], ("my/model", 0.3, 0.1))
        self.assertEqual(detector_step.resolve_detector("owlv2", None, 0.0, None)[2], 0.0)                 # a threshold of zero is a choice, not "not given"

    def test_a_detector_that_takes_many_phrases_at_once_is_asked_them_in_one_pass_per_search(self):
        class Wide(FakeDetector):
            phrases_per_pass = 100
        detector = Wide(lambda size, phrases: [])
        detector_step.detect(Image.new("RGB", (200, 120)), detector, FakeSegmenter(), tiles=1, small_tiles=1)
        self.assertEqual(len(detector.calls), len(detector_step.PASSES))                                   # one search per pass, since every phrase of the pass fits
        narrow = FakeDetector(lambda size, phrases: [])
        detector_step.detect(Image.new("RGB", (200, 120)), narrow, FakeSegmenter(), tiles=1, small_tiles=1)
        self.assertGreater(len(narrow.calls), len(detector_step.PASSES))

    def test_an_exact_phrase_label_maps_to_its_class(self):
        for phrase, cls in (("window", "opening"), ("flower pot", "plant"), ("street lamp", "lighting"), ("parking bay", "parking"), ("pedestrian crossing", "street")):
            self.assertEqual(detector_step.class_of_label(phrase), (cls, False))


class SecondDetectorTests(unittest.TestCase):
    def image(self):
        return Image.new("RGB", (200, 120), (90, 120, 90))

    def test_the_second_detector_answers_for_its_classes_and_replaces_the_first_ones_findings_of_them(self):
        first = FakeDetector(lambda size, phrases: [{"label": "person", "score": 0.9, "box": [10.0, 10.0, 30.0, 50.0]}] if "person" in phrases else
                             [{"label": "bollard", "score": 0.5, "box": [100.0, 10.0, 110.0, 40.0]}] if "bollard" in phrases else [])
        second = FakeDetector(lambda size, phrases: [{"label": "bollard", "score": 0.7, "box": [150.0, 10.0, 160.0, 40.0]}] if "bollard" in phrases else
                              [{"label": "person", "score": 0.7, "box": [0.0, 0.0, 5.0, 5.0]}] if "person" in phrases else [])
        detections, _, _, _ = detector_step.detect(self.image(), first, FakeSegmenter(), tiles=1, small_tiles=1, extras=[(second, ["street_furniture"], 0.15, 0.0)])
        found = {(d["object_class"], d["region"][0]) for d in detections}
        self.assertEqual(found, {("character", 10), ("street_furniture", 150)})              # the person is the first detector's, the bollard the second's: the first one's bollard is replaced

    def test_the_second_detector_is_asked_only_for_its_classes_and_with_its_own_phrases(self):
        class Owl(FakeDetector):
            prompts = {"parking": ["parking space"]}
        second = Owl(lambda size, phrases: [])
        detector_step.detect(self.image(), FakeDetector(lambda size, phrases: []), FakeSegmenter(), tiles=1, small_tiles=1, extras=[(second, ["parking", "lighting"], 0.15, 0.0)])
        asked = {p for _, phrases in second.calls for p in phrases}
        self.assertEqual(asked, {"parking space", "street lamp", "lantern"})

    def test_also_options_are_checked_in_words(self):
        for spec, message in (("owlv2", "name the classes"), ("owlv2:nothing", "no detection prompt"), ("yolo:parking", "unknown detector kind")):
            with self.subTest(spec=spec), self.assertRaisesRegex(ValueError, message):
                detector_step.also_detector(spec, "cpu")


class RunAgreementTests(unittest.TestCase):
    def image(self):
        return Image.new("RGB", (200, 120), (90, 120, 90))

    def detector(self):
        """Finds one person whatever the prompt, and a second object only when 'person' leads the prompt (the first run's grouping)."""
        def answers(size, phrases):
            found = []
            if "person" in phrases:
                found.append({"label": "person", "score": 0.9, "box": [10.0, 10.0, 30.0, 50.0]})
                if phrases[0] == "person":
                    found.append({"label": "person", "score": 0.6, "box": [100.0, 10.0, 120.0, 50.0]})
            return found
        return FakeDetector(answers)

    def test_a_variant_groups_the_same_phrases_differently_and_covers_all_of_them_once(self):
        first, second = detector_step.groups_of_phrases(None, 0), detector_step.groups_of_phrases(None, 1)
        self.assertNotEqual(first, second)
        self.assertEqual(sorted(p for g in first for p in g), sorted(p for g in second for p in g))
        self.assertEqual(detector_step.groups_of_phrases(None, 0), detector_step.groups_of_phrases(None))

    def test_one_run_gives_every_object_seen_once_with_no_seen_once_flag(self):
        detections, _, _, _ = detector_step.detect(self.image(), self.detector(), FakeSegmenter(), tiles=1, small_tiles=1)
        self.assertEqual([d["seen_in"] for d in detections], [1, 1])
        self.assertTrue(all("seen_once" not in d["flags"] for d in detections))

    def test_two_runs_keep_the_steady_object_and_flag_the_one_only_the_first_grouping_found(self):
        detections, raw, _, _ = detector_step.detect(self.image(), self.detector(), FakeSegmenter(), tiles=1, small_tiles=1, runs=2)
        by_x = {d["region"][0]: d for d in detections}
        self.assertEqual((by_x[10]["seen_in"], by_x[100]["seen_in"]), (2, 1))
        self.assertIn("seen_once", by_x[100]["flags"])
        self.assertNotIn("seen_once", by_x[10]["flags"])
        self.assertEqual(raw, 3)                                                              # two in the first run, one in the second

    def test_the_minimum_runs_drops_what_too_few_runs_agree_on(self):
        detections, _, _, _ = detector_step.detect(self.image(), self.detector(), FakeSegmenter(), tiles=1, small_tiles=1, runs=2, min_runs=2)
        self.assertEqual([d["region"][0] for d in detections], [10])

    def test_runs_and_minimum_runs_must_make_sense(self):
        for runs, minimum in ((0, 1), (2, 0), (2, 3)):
            with self.subTest(runs=runs, minimum=minimum), self.assertRaisesRegex(ValueError, "between 1 and runs"):
                detector_step.detect(self.image(), self.detector(), FakeSegmenter(), tiles=1, small_tiles=1, runs=runs, min_runs=minimum)

    def test_the_agreement_travels_into_the_draft_and_the_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.image().save(tmp / "mock.png")
            summary = detector_step.run(tmp / "mock.png", tmp / "out", "street", "candidate", self.detector(), FakeSegmenter(), tiles=1, small_tiles=1, runs=2)
            draft = common.read_json(tmp / "out" / "detected.blueprint.json")
            seen = {e["element_id"]: e["observed_details"]["seen_in"] for e in draft["elements"][1:]}
            self.assertEqual(sorted(seen.values()), [1, 2])
            self.assertEqual((summary["runs"], summary["min_runs"]), (2, 1))
            self.assertEqual(summary["flags"]["seen_once"], 1)


class DraftTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        Image.new("RGB", (1000, 600), (90, 120, 90)).save(self.root / "mock.png")
        self.out = self.root / "out"

    def run_step(self, answers=person_everywhere, shape="full", **kw):
        return detector_step.run(self.root / "mock.png", self.out, "street", "candidate", FakeDetector(answers), FakeSegmenter(shape), tiles=kw.pop("tiles", 1), **kw)

    def test_the_draft_is_a_pending_blueprint_whose_objects_are_inferred_with_the_detectors_score(self):
        summary = self.run_step()
        draft = common.read_json(self.out / "detected.blueprint.json")
        self.assertEqual(draft["elements"][0]["observed_details"]["small_tiles"], 4)
        self.assertEqual([name for name, _ in draft["elements"][0]["observed_details"]["passes"]], ["objects", "small", "area"])
        self.assertEqual((draft["approval_status"], draft["scope"]), ("pending_approval", "scene"))
        person = next(e for e in draft["elements"] if e["element_id"] == "character_01")
        self.assertEqual((person["evidence_status"], person["confidence"], person["source_region_px"]), ("inferred", 0.9, [10, 10, 20, 40]))
        component = draft["elements"][0]["separation_inventory"][0]
        self.assertEqual((component["object_class"], component["removal_mask_ref"]), ("character", "masks/character_01.png"))
        self.assertIn("fake-detector", component["source_evidence"])
        self.assertEqual(summary["per_class"], {"character": 1})

    def test_the_draft_passes_the_blueprint_validator_as_pending_and_is_not_taken_for_approved(self):
        self.run_step()
        path = self.out / "detected.blueprint.json"
        pending = subprocess.run([sys.executable, str(SCRIPT_VALIDATE), str(path), "--allow-pending"], capture_output=True, text=True)
        self.assertEqual(pending.returncode, 0, pending.stdout)
        approved = subprocess.run([sys.executable, str(SCRIPT_VALIDATE), str(path)], capture_output=True, text=True)
        self.assertEqual(approved.returncode, 1)

    def test_the_sweep_says_the_detector_found_nothing_not_that_the_picture_has_none(self):
        self.run_step()
        sweep = {e["object_class"]: e for e in common.read_json(self.out / "detected.blueprint.json")["object_sweep"]}
        self.assertEqual(sweep["character"]["status"], "present")
        self.assertEqual(sweep["vehicle"]["status"], "absent")
        self.assertIn("its finding, not a visual audit", sweep["vehicle"]["evidence"])
        self.assertIn("no detection prompt", sweep["other"]["evidence"])
        self.assertEqual(len(sweep), len(blueprint_rules.object_classes()))

    def test_the_flags_the_exclusions_and_the_mask_share_travel_into_the_draft_and_the_findings(self):
        answers = lambda size, phrases: ([{"label": "person", "score": 0.3, "box": [20.0, 50.0, 40.0, 90.0]}, {"label": "sign", "score": 0.9, "box": [150.0, 10.0, 190.0, 30.0]}]
                                         if "person" in phrases else [])
        summary = self.run_step(answers=answers, exclude=[[140, 0, 60, 40]])
        draft = common.read_json(self.out / "detected.blueprint.json")
        details = next(e for e in draft["elements"] if e["element_id"] == "character_01")["observed_details"]
        self.assertEqual((details["review_flags"], details["mask_share"]), (["low_score"], 1.0))
        self.assertIn("excluded region [140, 0, 60, 40]", draft["coverage_audit"]["intentional_exclusions"][0]["what"])
        self.assertEqual((summary["flagged"], summary["flags"], len(summary["excluded"])), (1, {"low_score": 1}, 1))
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT_VALIDATE), str(self.out / "detected.blueprint.json"), "--allow-pending"], capture_output=True, text=True).returncode, 0)

    def test_the_masks_and_the_raw_findings_are_written_and_an_object_with_no_mask_names_none(self):
        self.run_step(shape="speck")
        draft = common.read_json(self.out / "detected.blueprint.json")
        self.assertNotIn("removal_mask_ref", draft["elements"][0]["separation_inventory"][0])
        self.assertEqual(list((self.out / "masks").iterdir()), [])
        findings = common.read_json(self.out / "detections.json")
        self.assertEqual((findings["kept"], findings["with_mask"], findings["raw_detections"]), (1, 0, 1))
        self.assertIn("missed objects", " ".join(findings["not_assessed"]))

    def test_nothing_found_and_a_folder_with_files_are_refused(self):
        with self.assertRaisesRegex(ValueError, "found no object"):
            self.run_step(answers=lambda size, phrases: [])
        self.out.mkdir()
        (self.out / "old.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "is not empty"):
            self.run_step()

    def test_the_extraction_step_turns_a_detections_mask_into_a_cut_out_sprite(self):
        self.run_step(shape="inner")
        extraction = self.root / "extracted"
        manifest = extractor.extract(self.out / "detected.blueprint.json", self.root / "mock.png", extraction, provisional=True)
        entry = manifest["objects"][0]
        self.assertEqual(entry["region_px"], [14, 14, 12, 32])
        sprite = Image.open(extraction / entry["sprite"]).convert("RGBA")
        self.assertEqual(sprite.size, (12, 32))
        self.assertEqual(sprite.getpixel((6, 16))[3], 255)
        self.assertTrue(manifest["provisional"])
        sprite.close()


class DependencyTests(unittest.TestCase):
    def test_a_missing_optional_package_is_a_refusal_that_says_what_to_install(self):
        with self.assertRaisesRegex(ValueError, "optional extra"):
            detector_step.need("definitely_not_a_real_module")
        detector_step.need("json")

    def test_the_command_says_what_is_missing_when_the_models_cannot_be_loaded(self):
        code = "import sys; sys.modules['torch'] = None; sys.argv = ['x', 'detect', '--mockup', 'a.png', '--mockup-id', 'm', '--revision', 'r', '--output-dir', 'o']; import runpy; runpy.run_path(%r, run_name='__main__')" % str(ROOT / "scripts" / "detect_scene_objects.py")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("optional extra", result.stderr)


@unittest.skipUnless(REAL, "GAMEARTS_DETECTION_E2E is not set: the real-model test did NOT run (set it with torch and transformers installed)")
class RealModelTests(unittest.TestCase):
    def test_the_real_models_run_end_to_end_and_the_draft_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            image = Image.new("RGB", (320, 200), (90, 140, 90))
            image.save(tmp / "scene.png")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "detect_scene_objects.py"), "detect", "--mockup", str(tmp / "scene.png"), "--mockup-id", "m", "--revision", "r",
                                   "--output-dir", str(tmp / "out"), "--tiles", "1"], capture_output=True, text=True)
            self.assertIn(done.returncode, (0, 1), done.stderr)                           # a flat green picture may truthfully contain nothing
            if done.returncode == 1:
                self.assertIn("found no object", done.stderr)


if __name__ == "__main__":
    unittest.main()
