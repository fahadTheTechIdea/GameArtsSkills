"""Measuring a draft extraction against a reviewed one: one-to-one matching by region overlap, per-class recall and precision, class confusions."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_extraction as evaluator  # noqa: E402

SCRIPT = ROOT / "scripts" / "evaluate_extraction.py"
CLASSES = ["character", "vehicle", "building", "plant", "sign", "street_furniture", "lighting", "barrier", "opening", "prop", "structure_part", "street", "parking", "other"]


def blueprint(objects):
    """A blueprint whose inventory is {id: (class, region)}; the sweep addresses every class."""
    by_class = {}
    for object_id, (cls, _) in objects.items():
        by_class.setdefault(cls, []).append(object_id)
    scene = {"element_id": "scene", "scope": "scene", "evidence_status": "observed", "observed_details": {}, "motion_candidates": [], "production_strategy": "separate everything",
             "separation_inventory": [{"component_id": i, "ownership": ["independent_prop"], "object_class": c, "source_evidence": "seen"} for i, (c, _) in objects.items()]}
    elements = [scene] + [{"element_id": i, "scope": "asset", "parent_id": "scene", "source_region_px": r, "evidence_status": "observed", "observed_details": {}, "motion_candidates": [],
                           "production_strategy": "separate sprite"} for i, (_, r) in objects.items()]
    sweep = [{"object_class": c, "status": "present", "component_ids": by_class[c], "evidence": "found"} if c in by_class else {"object_class": c, "status": "absent", "evidence": "none"}
             for c in CLASSES]
    return {"schema_version": "1.0", "mockup_id": "street", "mockup_revision": "v1", "approval_status": "pending_approval", "scope": "scene", "elements": elements, "object_sweep": sweep,
            "coverage_audit": {"status": "pending_review", "unassigned_regions": []}}


REFERENCE = {"car_a": ("vehicle", [0, 0, 40, 20]), "car_b": ("vehicle", [100, 0, 40, 20]), "oak": ("plant", [0, 50, 30, 40]), "lamp": ("lighting", [200, 0, 10, 60])}


class CompareTests(unittest.TestCase):
    def objects(self, draft_extra=None, drop=()):
        draft = {k: v for k, v in REFERENCE.items() if k not in drop}
        draft.update(draft_extra or {})
        return {k: (c, r) for k, (c, r) in REFERENCE.items()}, draft

    def test_a_draft_that_equals_the_reference_scores_perfectly(self):
        reference, draft = self.objects()
        report = evaluator.compare(reference, draft)
        self.assertEqual((report["recall"], report["precision"], report["f1"], report["matched"]), (1.0, 1.0, 1.0, 4))
        self.assertEqual(report["per_class"]["vehicle"]["missed"], [])

    def test_a_missed_object_lowers_recall_and_an_extra_one_lowers_precision(self):
        reference, draft = self.objects(drop=("oak",), draft_extra={"ghost": ("sign", [300, 300, 10, 10])})
        report = evaluator.compare(reference, draft)
        self.assertEqual((report["recall"], report["precision"]), (0.75, 0.75))
        self.assertEqual(report["per_class"]["plant"]["missed"], ["oak"])
        self.assertEqual(report["per_class"]["plant"]["recall"], 0.0)
        self.assertEqual(report["per_class"]["sign"]["extra"], ["ghost"])
        self.assertEqual(report["per_class"]["sign"]["precision"], 0.0)

    def test_an_object_must_overlap_enough_to_count_and_each_reference_object_matches_once(self):
        reference = {"car": ("vehicle", [0, 0, 40, 20])}
        near = evaluator.compare(reference, {"d": ("vehicle", [30, 0, 40, 20])}, iou=0.5)        # a quarter overlap: not the same object
        self.assertEqual(near["matched"], 0)
        twice = evaluator.compare(reference, {"d1": ("vehicle", [0, 0, 40, 20]), "d2": ("vehicle", [1, 0, 40, 20])})
        self.assertEqual((twice["matched"], twice["per_class"]["vehicle"]["extra"]), (1, ["d2"]))   # the second draft box is a duplicate, not a second hit

    def test_the_best_overlap_wins_when_two_draft_boxes_could_match(self):
        reference = {"car": ("vehicle", [0, 0, 40, 20])}
        report = evaluator.compare(reference, {"loose": ("vehicle", [0, 0, 60, 30]), "tight": ("vehicle", [1, 1, 40, 20])})
        self.assertEqual(report["per_class"]["vehicle"]["extra"], ["loose"])

    def test_the_right_place_with_the_wrong_class_is_confused_not_matched(self):
        reference = {"oak": ("plant", [0, 0, 30, 40])}
        report = evaluator.compare(reference, {"d": ("sign", [0, 0, 30, 40])})
        self.assertEqual(report["matched"], 0)
        self.assertEqual(report["confused"], [{"reference": "oak", "reference_class": "plant", "draft": "d", "draft_class": "sign", "overlap": 1.0}])
        self.assertEqual(report["per_class"]["plant"]["missed"], ["oak"])

    def test_a_class_with_nothing_in_one_side_has_no_rate_instead_of_a_wrong_one(self):
        report = evaluator.compare({"oak": ("plant", [0, 0, 30, 40])}, {"d": ("plant", [0, 0, 30, 40]), "x": ("sign", [100, 100, 10, 10])})
        self.assertIsNone(report["per_class"]["sign"]["recall"])
        self.assertEqual(report["per_class"]["sign"]["precision"], 0.0)

    def test_an_empty_draft_scores_zero_without_dividing_by_zero(self):
        report = evaluator.compare({"oak": ("plant", [0, 0, 30, 40])}, {})
        self.assertEqual((report["recall"], report["precision"], report["f1"]), (0.0, 0.0, 0.0))

    def test_the_overlap_threshold_must_be_a_fraction(self):
        for bad in (0, -0.1, 1.5):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "above 0 and at most 1"):
                evaluator.compare(REFERENCE, REFERENCE, bad)


class FileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "reference.json").write_text(json.dumps(blueprint(REFERENCE)), encoding="utf-8")
        (self.root / "draft.json").write_text(json.dumps(blueprint({k: v for k, v in REFERENCE.items() if k != "lamp"})), encoding="utf-8")

    def run_command(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "compare", "--reference", str(self.root / "reference.json"), "--draft", str(self.root / "draft.json"),
                               "--output", str(self.root / "report.json"), *extra], capture_output=True, text=True)

    def test_the_command_reads_two_blueprints_and_writes_the_report(self):
        done = self.run_command()
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads((self.root / "report.json").read_text(encoding="utf-8"))
        self.assertEqual((report["reference_objects"], report["draft_objects"], report["recall"], report["precision"]), (4, 3, 0.75, 1.0))
        self.assertIn("lighting", done.stdout)
        self.assertTrue(any("reference is complete" in line for line in report["not_assessed"]))

    def test_an_existing_report_is_never_overwritten(self):
        self.run_command()
        again = self.run_command()
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("never overwritten", again.stderr)

    def test_a_blueprint_that_is_not_an_inventory_is_refused_in_words(self):
        data = blueprint(REFERENCE)
        data["elements"] = [e for e in data["elements"] if e["element_id"] != "oak"]
        (self.root / "draft.json").write_text(json.dumps(data), encoding="utf-8")
        done = self.run_command()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("draft cannot be read as an inventory", done.stderr)
        self.assertIn("oak has no element", done.stderr)


if __name__ == "__main__":
    unittest.main()
