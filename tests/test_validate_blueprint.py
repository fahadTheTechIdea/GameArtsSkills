"""Schema validation for generated/pending mockup blueprints."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_blueprint.py"


class ValidateBlueprintTests(unittest.TestCase):
    def blueprint(self, root):
        path = root / "generated.blueprint.json"
        path.write_text(json.dumps({
            "schema_version": "7.2",
            "mockup_id": "test-game-colony",
            "mockup_revision": "v001",
            "approval_status": "pending_approval",
            "scope": "world",
            "elements": [{
                "element_id": "terrain",
                "scope": "world",
                "evidence_status": "observed",
                "observed_details": {"surface": "regolith"},
                "motion_candidates": [],
                "production_strategy": "separate ground sheet"
            }],
            "coverage_audit": {
                "status": "pending_review",
                "unassigned_regions": []
            }
        }))
        return path

    def test_pending_blueprint_requires_explicit_allow_pending(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.blueprint(Path(td))
            blocked = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                capture_output=True, text=True)
            allowed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--allow-pending"],
                capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 1)
            self.assertIn("not approved", blocked.stdout)
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
            self.assertIn("PASS pending/generated blueprint", allowed.stdout)

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)

    def test_the_current_and_the_legacy_format_marker_are_accepted_and_others_are_not(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.blueprint(Path(td))
            for marker, expected in (("1.0", 0), ("7.2", 0), ("9.9", 1)):
                data = json.loads(path.read_text())
                data["schema_version"] = marker
                path.write_text(json.dumps(data))
                result = self.run_script(path, "--allow-pending")
                self.assertEqual(result.returncode, expected, f"{marker}: {result.stdout}{result.stderr}")

    def test_an_element_missing_a_required_field_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.blueprint(Path(td))
            data = json.loads(path.read_text())
            del data["elements"][0]["evidence_status"]
            path.write_text(json.dumps(data))
            result = self.run_script(path, "--allow-pending")
            self.assertEqual(result.returncode, 1)
            self.assertIn("evidence_status", result.stdout)

    def test_a_missing_validator_package_fails_instead_of_passing(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.blueprint(Path(td))
            code = ("import sys, runpy; sys.modules['jsonschema'] = None; "
                    f"sys.argv = [{str(SCRIPT)!r}, {str(path)!r}, '--allow-pending']; "
                    f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')")
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("jsonschema is required", result.stdout)
            self.assertNotIn("PASS", result.stdout)

    def test_an_unreadable_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            broken = Path(td) / "broken.json"
            broken.write_text("{nope")
            self.assertEqual(self.run_script(broken).returncode, 1)
            self.assertEqual(self.run_script(Path(td) / "missing.json").returncode, 1)


if __name__ == "__main__":
    unittest.main()
