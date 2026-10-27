"""The environment doctor (plan P13.2): it looks, explains, and never changes anything."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import write_settings

import gamearts_common as common  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_doctor as doctor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_doctor.py"


def by_name(report):
    return {item["name"]: item for item in report["checks"]}


def missing(*names):
    """An importer that behaves as if the named top-level modules were not installed."""
    def importer(name):
        if name in names:
            raise ImportError(f"No module named {name!r}")
        return __import__(name)
    return importer


class DoctorTests(unittest.TestCase):
    def ready_game(self, root):
        write_settings(root, image_generation={"tool": "user_supplied"})
        return root

    def test_a_ready_game_reports_ready_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.ready_game(Path(td))
            before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
            report = doctor.run(root)
            self.assertEqual(report["status"], "ready", json.dumps(report, indent=1))
            self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob("*")), before)
            names = by_name(report)
            self.assertEqual(names["settings"]["status"], "ok")
            self.assertEqual(names["engine profile"]["status"], "ok")
            self.assertIn("Nothing needs fixing", report["next_step"])

    def test_a_missing_package_blocks_with_the_exact_command_for_this_interpreter(self):
        with tempfile.TemporaryDirectory() as td:
            report = doctor.run(self.ready_game(Path(td)), importer=missing("jsonschema"))
            item = by_name(report)["jsonschema"]
            self.assertEqual((report["status"], item["status"]), ("blocked", "fail"))
            self.assertIn("-m pip install jsonschema", item["fix"])
            self.assertIn(sys.executable, item["fix"])
            self.assertEqual(report["next_step"], item["fix"])

    def test_both_packages_are_checked_independently(self):
        with tempfile.TemporaryDirectory() as td:
            report = doctor.run(self.ready_game(Path(td)), importer=missing("PIL", "jsonschema"))
            names = by_name(report)
            self.assertEqual((names["pillow"]["status"], names["jsonschema"]["status"]), ("fail", "fail"))

    def test_an_old_python_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            report = doctor.run(self.ready_game(Path(td)), version=(3, 8, 10))
            self.assertEqual(by_name(report)["python"]["status"], "fail")
            self.assertEqual(report["status"], "blocked")

    def test_a_folder_that_cannot_be_written_blocks_and_says_where(self):
        with tempfile.TemporaryDirectory() as td:
            report = doctor.run(self.ready_game(Path(td)), can_write=lambda folder: False)
            item = by_name(report)["write access"]
            self.assertEqual(item["status"], "fail")
            self.assertIn("permissions", item["fix"])

    def test_a_game_with_no_settings_yet_needs_attention_not_a_block(self):
        with tempfile.TemporaryDirectory() as td:
            report = doctor.run(Path(td))
            self.assertEqual(by_name(report)["settings"]["status"], "warn")
            self.assertEqual(report["status"], "needs_attention")
            self.assertIn("setup", report["next_step"].lower())

    def test_unconfirmed_settings_are_a_warning_with_the_fix(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_settings(root, settings_status="inferred")
            item = by_name(doctor.run(root))["settings"]
            self.assertEqual(item["status"], "warn")
            self.assertIn("confirmation", item["fix"])

    def test_invalid_settings_block_and_name_the_problem(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".gamearts").mkdir()
            (root / ".gamearts" / "project.json").write_text('{"project_id": "partial"}', encoding="utf-8")
            item = by_name(doctor.run(root))["settings"]
            self.assertEqual(item["status"], "fail")
            self.assertIn("contract violation", item["detail"])

    def test_with_jsonschema_missing_the_settings_check_says_so_instead_of_crashing(self):
        original = common.validate_schema

        def fails(*args, **kwargs):
            raise common.DependencyMissing("jsonschema is required for contract validation (pip install jsonschema)")
        common.validate_schema = fails
        try:
            with tempfile.TemporaryDirectory() as td:
                item = by_name(doctor.run(self.ready_game(Path(td)), importer=missing("jsonschema")))["settings"]
                self.assertEqual(item["status"], "fail")
                self.assertIn("jsonschema", item["detail"])
        finally:
            common.validate_schema = original

    def test_a_missing_image_generator_is_a_warning_with_the_question_to_ask(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_settings(root)
            item = by_name(doctor.run(root))["image generator"]
            self.assertEqual(item["status"], "warn")
            self.assertIn("Ask the owner once", item["fix"])

    def test_an_engine_with_no_profile_is_information_never_a_problem(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_settings(root, image_generation={"tool": "user_supplied"}, engine_target={"profile": "some-other-engine"})
            report = doctor.run(root)
            self.assertEqual(by_name(report)["engine profile"]["status"], "info")
            self.assertEqual(report["status"], "ready")

    def test_the_interpreter_commands_on_the_path_are_listed(self):
        with tempfile.TemporaryDirectory() as td:
            report = doctor.run(self.ready_game(Path(td)), which=lambda name: "/bin/x" if name == "py" else None)
            self.assertIn("py", by_name(report)["interpreter command"]["detail"])
            none = doctor.run(self.ready_game(Path(td)), which=lambda name: None)
            self.assertEqual(by_name(none)["interpreter command"]["status"], "warn")

    def test_edited_framework_files_the_updater_kept_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.ready_game(Path(td))
            state = root / ".gamearts" / "system" / "agent-sync-state.json"
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({"revision": "a" * 40, "conflicts": ["scripts/x.py (local change)"]}), encoding="utf-8")
            item = by_name(doctor.run(root))["updater"]
            self.assertEqual(item["status"], "warn")
            self.assertIn("1 framework file", item["detail"])

    def test_a_game_folder_that_does_not_exist_blocks(self):
        report = doctor.run(Path(tempfile.gettempdir()) / "gamearts-doctor-no-such-folder")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(by_name(report)["game folder"]["status"], "fail")


class CommandLineTests(unittest.TestCase):
    def test_the_command_prints_json_and_exits_zero_for_a_ready_game(self):
        with tempfile.TemporaryDirectory() as td:
            write_settings(td, image_generation={"tool": "user_supplied"})
            result = subprocess.run([sys.executable, str(SCRIPT), "--game-root", td], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "ready")

    def test_the_command_exits_one_when_something_blocks(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--game-root", str(Path(tempfile.gettempdir()) / "gamearts-doctor-none")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
