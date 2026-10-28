"""The scene-extraction stage of the lifecycle: an approved scene mockup is extracted through `extract-scene`, the account is recorded on its row,
and the next steps (the operation's sentence and the report) name the stage until it has run."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import digest, make_mockup, make_sheet, write_settings
from PIL import Image
from test_extract_scene_objects import OBJECTS, blueprint, mockup

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_report as report  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_asset_lifecycle.py"


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        write_settings(self.root)

    def register(self, scope="scene", with_blueprint=True, approve=True):
        image, metadata = make_mockup(self.root, "street", "v001", scope=scope, picture_image=mockup())
        if with_blueprint:
            plan = self.root / "street_blueprint.json"
            plan.write_text(json.dumps(blueprint(sha=digest(image))), encoding="utf-8")
            body = json.loads(metadata.read_text())
            body["blueprint"] = plan.name
            metadata.write_text(json.dumps(body))
        life.register_mockup(self.root, metadata, image)
        if approve:
            life.approve_mockup(self.root, "street", "v001", "approved-in-test")

    def stub_detector(self, perfect=True):
        """A stand-in for the detection process (the real one needs torch): writes the draft blueprint and findings the real one writes."""
        draft = blueprint(sha=digest(self.root / ".gamearts/outputs/mockups/approved/street_mockup_v001.png"))
        if not perfect:
            draft["elements"] = [e for e in draft["elements"] if e["element_id"] != "oak"]
            draft["elements"][0]["separation_inventory"] = [c for c in draft["elements"][0]["separation_inventory"] if c["component_id"] != "oak"]
            for entry in draft["object_sweep"]:
                if entry["object_class"] == "plant":
                    entry.update({"status": "absent", "evidence": "the detector found nothing"})
                    entry.pop("component_ids", None)
        (self.root / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
        script = self.root / "stub_detector.py"
        body = ["import json, shutil, sys", "from pathlib import Path",
                "out = Path(sys.argv[sys.argv.index('--output-dir') + 1])", "out.mkdir(parents=True)",
                f"shutil.copy({str(self.root / 'draft.json')!r}, out / 'detected.blueprint.json')",
                "(out / 'detections.json').write_text(json.dumps({'kept': 5, 'per_class': {'building': 1}, 'flagged': 1, 'not_assessed': ['whether the detector missed objects']}))"]
        script.write_text(chr(10).join(body) + chr(10), encoding="utf-8")

        return [sys.executable, str(script)]

    def row(self):
        return life.records(self.root, "mockups")[0]


class ExtractSceneTests(Case):
    def test_an_approved_scene_mockup_is_extracted_and_the_account_is_recorded_on_its_row(self):
        self.register()
        result = life.extract_scene(self.root, "street", "v001")
        self.assertEqual(result["status"], "extracted")
        self.assertEqual(result["objects"], 5)
        recorded = self.row()["scene_extraction"]
        self.assertEqual(recorded["objects"], 5)
        self.assertTrue((self.root / recorded["path"] / "extraction.json").is_file())
        self.assertEqual(recorded["manifest_sha256"], digest(self.root / recorded["path"] / "extraction.json"))

    def test_a_mockup_that_is_not_approved_is_refused_and_nothing_is_written(self):
        self.register(approve=False)
        with self.assertRaisesRegex(ValueError, "approved"):
            life.extract_scene(self.root, "street", "v001")
        self.assertNotIn("scene_extraction", self.row())
        self.assertFalse((self.root / ".gamearts" / "outputs" / "scenes").exists())

    def test_a_mockup_of_a_single_asset_is_not_a_scene(self):
        self.register(scope="asset")
        with self.assertRaisesRegex(ValueError, "scene stages are for"):
            life.extract_scene(self.root, "street", "v001")

    def test_a_scene_mockup_without_a_blueprint_is_sent_back_to_the_analyzer(self):
        self.register(with_blueprint=False)
        with self.assertRaisesRegex(ValueError, "no blueprint"):
            life.extract_scene(self.root, "street", "v001")

    def test_running_it_twice_never_writes_into_the_first_extraction(self):
        self.register()
        life.extract_scene(self.root, "street", "v001")
        with self.assertRaisesRegex(ValueError, "not empty"):
            life.extract_scene(self.root, "street", "v001")

    def test_the_command_line_runs_it_and_ends_with_a_next_step_and_a_report(self):
        self.register()
        done = subprocess.run([sys.executable, str(SCRIPT), "extract-scene", "--game-root", str(self.root), "--id", "street", "--revision", "v001"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        body = json.loads(done.stdout)
        self.assertEqual(body["status"], "extracted")
        self.assertIn("contact sheet", body["next_step"])
        self.assertIn("report", body)


class FlatInpainter:
    id = "flat-stand-in"

    def inpaint(self, image, mask):
        out = image.copy()
        out.paste((1, 2, 3), mask=mask)
        return out


class DetectEvaluateRemoveTests(Case):
    def test_the_detection_is_recorded_as_a_draft_pending_review_and_never_as_the_blueprint(self):
        self.register()
        result = life.detect_scene(self.root, "street", "v001", self.stub_detector())
        self.assertEqual(result["status"], "draft_pending_review")
        row = self.row()
        self.assertEqual(row["scene_detection"]["status"], "draft_pending_review")
        self.assertTrue((self.root / row["scene_detection"]["path"] / "detected.blueprint.json").is_file())
        self.assertEqual(row["blueprint"], ".gamearts/outputs/mockups/approved/street_mockup_v001.blueprint.json")

    def test_a_detector_that_cannot_run_is_reported_and_nothing_is_recorded(self):
        self.register()
        broken = self.root / "broken.py"
        broken.write_text("import sys" + chr(10) + "sys.exit('the detection step needs torch')" + chr(10), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "detection step failed.*needs torch"):
            life.detect_scene(self.root, "street", "v001", [sys.executable, str(broken)])
        self.assertNotIn("scene_detection", self.row())

    def test_the_evaluation_scores_the_detection_against_the_reviewed_blueprint(self):
        self.register()
        life.detect_scene(self.root, "street", "v001", self.stub_detector(perfect=False))
        result = life.evaluate_scene(self.root, "street", "v001")
        self.assertEqual((result["reference_objects"], result["draft_objects"], result["matched"]), (5, 4, 4))
        self.assertEqual(result["recall"], 0.8)
        self.assertEqual(self.row()["scene_evaluation"]["precision"], 1.0)
        with self.assertRaisesRegex(ValueError, "never overwritten"):
            life.evaluate_scene(self.root, "street", "v001")

    def test_an_evaluation_needs_a_recorded_detection(self):
        self.register()
        with self.assertRaisesRegex(ValueError, "run detect-scene first"):
            life.evaluate_scene(self.root, "street", "v001")

    def with_oak_mask(self):
        """The registered blueprint names a mask for the oak; the mask itself is in a folder of the game (as the detection stage leaves them), not beside the blueprint."""
        plan = self.root / ".gamearts/outputs/mockups/approved/street_mockup_v001.blueprint.json"
        data = json.loads(plan.read_text())
        region = next(o for o in OBJECTS if o[0] == "oak")[2]
        next(c for c in data["elements"][0]["separation_inventory"] if c["component_id"] == "oak")["removal_mask_ref"] = "masks/oak.png"
        plan.write_text(json.dumps(data))
        folder = self.root / "analysis" / "masks"
        folder.mkdir(parents=True)
        Image.new("L", (region[2], region[3]), 255).save(folder / "oak.png")

    def test_the_removal_stages_the_masks_from_a_folder_of_the_game_and_leaves_the_approved_folder_alone(self):
        self.register()
        self.with_oak_mask()
        life.extract_scene(self.root, "street", "v001", masks_from="analysis")
        approved = self.root / ".gamearts/outputs/mockups/approved"
        before = sorted(p.name for p in approved.iterdir())
        result = life.remove_scene(self.root, "street", "v001", FlatInpainter(), max_share=0.2, masks_from="analysis")
        self.assertEqual(result["removed"], ["oak"])
        self.assertIn("inferred", result["pixel_status"])
        recorded = self.row()["scene_removal"]
        self.assertEqual((recorded["status"], recorded["masks_from"]), ("draft_pending_review", "analysis"))
        self.assertTrue((self.root / recorded["path"] / "clean_parent_draft.png").is_file())
        self.assertEqual(sorted(p.name for p in approved.iterdir()), before)

    def test_without_a_named_folder_the_removal_uses_the_recorded_detections_masks(self):
        self.register()
        self.with_oak_mask()
        with self.assertRaisesRegex(ValueError, "name the folder that holds them"):
            life.extract_scene(self.root, "street", "v001")
        life.extract_scene(self.root, "street", "v001", masks_from="analysis")
        with self.assertRaisesRegex(ValueError, "name the folder that holds them"):
            life.remove_scene(self.root, "street", "v001", FlatInpainter())
        life.detect_scene(self.root, "street", "v001", self.stub_detector())
        shutil.copytree(self.root / "analysis" / "masks", self.root / ".gamearts/outputs/scenes/street_v001/detection/masks")
        result = life.remove_scene(self.root, "street", "v001", FlatInpainter(), max_share=0.2)
        self.assertEqual(result["removed"], ["oak"])
        self.assertEqual(self.row()["scene_removal"]["masks_from"], ".gamearts/outputs/scenes/street_v001/detection")

    def test_a_mask_the_blueprint_names_but_the_folder_lacks_is_named(self):
        self.register()
        self.with_oak_mask()
        life.extract_scene(self.root, "street", "v001", masks_from="analysis")
        (self.root / "analysis" / "masks" / "oak.png").unlink()
        with self.assertRaisesRegex(ValueError, "oak: the mask masks/oak.png is not in analysis"):
            life.remove_scene(self.root, "street", "v001", FlatInpainter(), masks_from="analysis")
        self.assertNotIn("scene_removal", self.row())
        self.assertFalse((self.root / ".gamearts/outputs/scenes/street_v001/clean_parent").exists())

    def test_the_extraction_cuts_a_sprite_for_an_object_whose_mask_is_staged(self):
        self.register()
        self.with_oak_mask()
        life.extract_scene(self.root, "street", "v001", masks_from="analysis")
        folder = self.root / self.row()["scene_extraction"]["path"]
        self.assertTrue((folder / "plant" / "oak.sprite.png").is_file())
        self.assertEqual(self.row()["scene_extraction"]["masks_from"], "analysis")

    def test_the_removal_follows_the_extraction(self):
        self.register()
        self.with_oak_mask()
        with self.assertRaisesRegex(ValueError, "run extract-scene first"):
            life.remove_scene(self.root, "street", "v001", FlatInpainter(), masks_from="analysis")

    def test_stages_that_need_the_blueprint_refuse_a_mockup_without_one(self):
        self.register(with_blueprint=False)
        with self.assertRaisesRegex(ValueError, "no blueprint"):
            life.remove_scene(self.root, "street", "v001", FlatInpainter())
        life.detect_scene(self.root, "street", "v001", self.stub_detector())  # detection is how a blueprint begins, so it needs none
        self.assertIn("scene_detection", self.row())

    def test_the_command_line_names_each_stage_and_ends_with_a_next_step(self):
        self.register()
        stub = self.stub_detector()
        base = [sys.executable, str(SCRIPT)]
        run = lambda *a: subprocess.run(base + list(a) + ["--game-root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(run("detect-scene", "--id", "street", "--revision", "v001", "--python", stub[0]).returncode, 1)  # the real detector script is not the stub
        for name in ("detect-scene", "remove-scene", "evaluate-scene"):
            self.assertIn(name, run("--help").stdout)


class AssetOrderingTests(Case):
    def build(self):
        folder = self.root / ".gamearts/outputs/assets/generated/sprite_v001"
        folder.mkdir(parents=True)
        make_sheet(folder, "sprite_v001_sheet", "sprite")
        return "sprite_v001", ".gamearts/outputs/assets/generated/sprite_v001"

    def test_no_asset_is_registered_from_a_scene_that_has_not_been_extracted(self):
        self.register()
        name, bundle = self.build()
        with self.assertRaisesRegex(ValueError, "has not been extracted: run extract-scene first"):
            life.register_asset(self.root, name, "v001", bundle, [("street", "v001")])
        life.extract_scene(self.root, "street", "v001")
        self.assertEqual(life.register_asset(self.root, name, "v001", bundle, [("street", "v001")])["status"], "generated")

    def test_a_recorded_extraction_that_changed_on_disk_no_longer_counts(self):
        self.register()
        life.extract_scene(self.root, "street", "v001")
        folder = self.root / self.row()["scene_extraction"]["path"]
        (folder / "extraction.json").write_text("{}", encoding="utf-8")
        name, bundle = self.build()
        with self.assertRaisesRegex(ValueError, "missing or has changed"):
            life.register_asset(self.root, name, "v001", bundle, [("street", "v001")])

    def test_a_mockup_of_another_scope_or_with_no_blueprint_is_not_held_to_it(self):
        self.register(with_blueprint=False)
        name, bundle = self.build()
        self.assertEqual(life.register_asset(self.root, name, "v001", bundle, [("street", "v001")])["status"], "generated")


class NextStepTests(Case):
    def steps(self):
        return report.next_steps("owner_confirmed", life.records(self.root, "mockups"), [], None)

    def test_approving_a_scene_names_the_extraction_in_the_operations_sentence(self):
        self.assertIn("extract-scene", life.next_step_for("approve-mockup", {"scope": "scene"}))
        self.assertNotIn("extract-scene", life.next_step_for("approve-mockup", {"scope": "character"}))

    def test_the_report_asks_for_the_extraction_until_it_has_run(self):
        self.register()
        self.assertTrue(any("extract-scene" in step and "street" in step for step in self.steps()), self.steps())
        life.extract_scene(self.root, "street", "v001")
        self.assertFalse(any("extract" in step.lower() for step in self.steps()), self.steps())

    def test_each_scene_stage_has_its_own_closing_sentence(self):
        self.assertIn("DRAFT", life.next_step_for("detect-scene", {}))
        self.assertIn("inferred", life.next_step_for("remove-scene", {}))
        self.assertIn("recall", life.next_step_for("evaluate-scene", {}))

    def test_a_scene_without_a_blueprint_is_asked_for_the_analysis_first(self):
        self.register(with_blueprint=False)
        self.assertTrue(any("Analyze" in step and "street" in step for step in self.steps()), self.steps())


if __name__ == "__main__":
    unittest.main()
