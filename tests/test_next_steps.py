"""Every operation that changes a record ends with `ok` and a plain `next_step` built from its own result (plan P13.3)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import make_mockup, make_sheet, picture, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_asset_lifecycle.py"
OUT = ".gamearts/outputs"


class NextStepWordingTests(unittest.TestCase):
    def test_each_operation_has_a_sentence_that_fits_what_happened(self):
        self.assertIn("approve it, or what should change", life.next_step_for("register", {}))
        self.assertEqual(life.next_step_for("register-generated", {}), life.next_step_for("register", {}))
        self.assertIn("is approved", life.next_step_for("import-mockup", {"status": "approved"}))
        self.assertIn("approved or what should change", life.next_step_for("import-mockup", {"status": "generated"}))
        self.assertIn("mockup-analyzer", life.next_step_for("approve-mockup", {}))
        self.assertIn("ask what to make next", life.next_step_for("approve", {}))

    def test_a_registered_asset_is_either_ready_to_show_or_to_be_fixed(self):
        passed = life.next_step_for("register-asset", {"technical_validation": "passed"})
        failed = life.next_step_for("register-asset", {"technical_validation": "failed"})
        self.assertIn("ask the owner to approve", passed)
        self.assertIn("fix the issues", failed)
        self.assertNotEqual(passed, failed)

    def test_a_revoked_mockup_names_the_assets_that_now_need_rebuilding(self):
        alone = life.next_step_for("revoke", {"dependents": []})
        built = life.next_step_for("revoke", {"dependents": [{"asset_id": "a"}, {"asset_id": "b"}]})
        self.assertNotIn("built on it", alone)
        self.assertIn("2 asset(s) were built on it", built)
        self.assertIn("replacement", built)

    def test_every_operation_that_changes_a_record_has_its_own_sentence(self):
        generic = life.next_step_for("an-unknown-operation", {})
        for name in life.MUTATING_OPERATIONS:
            if name != "restore":  # restore returns its own, more specific sentence
                self.assertNotEqual(life.next_step_for(name, {}), generic, name)


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        write_settings(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def run_op(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), args[0], "--game-root", str(self.root), *args[1:]], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_a_whole_flow_reports_ok_and_a_next_step_each_time(self):
        image, metadata = make_mockup(self.root, "flow-scene", "v001", "world")
        registered = self.run_op("register", "--metadata", str(metadata), "--image", str(image))
        approved = self.run_op("approve-mockup", "--id", "flow-scene", "--revision", "v001", "--user-approval-ref", "yes, approved")
        folder = self.root / OUT / "assets/generated/flow_asset_v001"
        folder.mkdir(parents=True)
        make_sheet(folder, "flow_asset_v001_sheet", "flow_asset")
        built = self.run_op("register-asset", "--id", "flow_asset_v001", "--revision", "v001", "--bundle", f"{OUT}/assets/generated/flow_asset_v001",
                            "--source-mockup", "flow-scene:v001")
        accepted = self.run_op("approve", "--id", "flow_asset_v001", "--user-approval-ref", "looks right")
        withdrawn = self.run_op("revoke", "--kind", "mockups", "--id", "flow-scene", "--revision", "v001", "--reason", "wrong mood")
        for name, result in (("register", registered), ("approve-mockup", approved), ("register-asset", built), ("approve", accepted), ("revoke", withdrawn)):
            with self.subTest(operation=name):
                self.assertIs(result["ok"], True)
                self.assertEqual(result["next_step"], life.next_step_for(name, result))
                self.assertTrue(result["report"]["updated"])
        self.assertIn("1 asset(s) were built on it", withdrawn["next_step"])

    def test_an_import_reports_whether_it_ended_approved_or_waiting(self):
        source = picture(self.root / "painting.png")
        waiting = self.run_op("import-mockup", "--source", str(source), "--id", "imported", "--revision", "v001", "--scope", "scene")
        self.assertIn("approved or what should change", waiting["next_step"])
        done = self.run_op("import-mockup", "--source", str(source), "--id", "imported-b", "--revision", "v001", "--scope", "scene",
                           "--user-approval-ref", "it is approved")
        self.assertIn("is approved", done["next_step"])

    def test_restore_keeps_its_own_more_specific_sentence(self):
        image, metadata = make_mockup(self.root, "back-scene", "v001", "world")
        self.run_op("register", "--metadata", str(metadata), "--image", str(image))
        self.run_op("revoke", "--kind", "mockups", "--id", "back-scene", "--revision", "v001", "--reason", "oops")
        restored = self.run_op("restore", "--kind", "mockups", "--id", "back-scene", "--revision", "v001", "--user-restore-ref", "bring it back")
        self.assertIn("fresh explicit approval", restored["next_step"])

    def test_reading_operations_are_not_given_a_next_step(self):
        listed = subprocess.run([sys.executable, str(SCRIPT), "list", "--game-root", str(self.root), "--kind", "mockups"], capture_output=True, text=True)
        self.assertEqual(json.loads(listed.stdout), [])


if __name__ == "__main__":
    unittest.main()
