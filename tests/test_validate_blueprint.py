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


ROOT = Path(__file__).resolve().parents[1]
CLASSES = ["character", "vehicle", "building", "plant", "sign", "street_furniture", "lighting", "barrier", "opening", "prop", "structure_part", "street", "parking", "other"]


def element(component_ids=(), classes=()):
    return {"element_id": "scene_root", "scope": "scene", "evidence_status": "observed", "observed_details": {"note": "street"}, "motion_candidates": [],
            "production_strategy": "separate every object",
            "separation_inventory": [dict({"component_id": c, "ownership": ["independent_prop"], "source_evidence": "seen at the kerb"}, **({"object_class": k} if k else {}))
                                     for c, k in zip(component_ids, list(classes) + [None] * len(component_ids))]}


def sweep(present=None, absent_evidence="looked along the whole street; none visible"):
    """A complete sweep: the classes in `present` ({class: [component ids]}) are present, every other class is absent."""
    present = present or {}
    return [{"object_class": name, "status": "present", "component_ids": present[name], "evidence": "in the foreground"} if name in present
            else {"object_class": name, "status": "absent", "evidence": absent_evidence} for name in CLASSES]


class ObjectSweepTests(unittest.TestCase):
    def write(self, root, scope="scene", status="approved", elements=None, object_sweep=None, drop_sweep=False):
        data = {"schema_version": "1.0", "mockup_id": "street", "mockup_revision": "v001", "approval_status": status, "scope": scope,
                "elements": elements or [element(["car_1", "tree_1"], ["vehicle", "plant"])], "coverage_audit": {"status": "pass", "unassigned_regions": []}}
        if not drop_sweep:
            data["object_sweep"] = object_sweep if object_sweep is not None else sweep({"vehicle": ["car_1"], "plant": ["tree_1"]})
        path = Path(root) / "bp.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)

    def test_a_scene_with_every_class_addressed_passes(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_script(self.write(td))
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_an_approved_scene_world_or_mixed_blueprint_without_a_sweep_is_incomplete_and_an_asset_is_not_held_to_it(self):
        with tempfile.TemporaryDirectory() as td:
            for scope in ("scene", "world", "mixed"):
                result = self.run_script(self.write(td, scope=scope, drop_sweep=True))
                self.assertEqual(result.returncode, 1, scope)
                self.assertIn("INCOMPLETE object sweep missing", result.stdout)
                self.assertIn("vehicle", result.stdout)                                    # it names the classes to address
            self.assertEqual(self.run_script(self.write(td, scope="asset", drop_sweep=True)).returncode, 0)

    def test_a_pending_scene_may_lack_the_sweep_but_a_sweep_that_is_there_is_always_checked(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self.run_script(self.write(td, status="pending_approval", drop_sweep=True), "--allow-pending").returncode, 0)
            broken = sweep({"vehicle": ["car_1"], "plant": ["tree_1"]})[:-1]               # a class left out
            result = self.run_script(self.write(td, status="pending_approval", object_sweep=broken), "--allow-pending")
            self.assertEqual(result.returncode, 1)
            self.assertIn("class other is not addressed", result.stdout)

    def test_each_inconsistency_is_refused_in_words(self):
        cases = {
            "a class addressed twice": (sweep({"vehicle": ["car_1"], "plant": ["tree_1"]}) + [sweep()[0]], "addressed more than once"),
            "present with no component": (sweep({"vehicle": ["car_1"], "plant": []}), "marked present but names no component"),
            "a component that does not exist": (sweep({"vehicle": ["car_1"], "plant": ["tree_1", "ghost"]}), "ghost, which no element"),
            "absent but naming components": ([dict(e, component_ids=["tree_1"]) if e["object_class"] == "sign" else e for e in sweep({"vehicle": ["car_1"], "plant": ["tree_1"]})], "marked absent but names components"),
            "a component listed under the wrong class": (sweep({"vehicle": ["car_1", "tree_1"], "plant": []}), "tree_1 is listed under vehicle but declares the class plant"),
        }
        for label, (object_sweep, message) in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as td:
                result = self.run_script(self.write(td, object_sweep=object_sweep))
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(message, result.stdout)

    def test_a_component_that_declares_a_class_the_sweep_calls_absent_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_script(self.write(td, object_sweep=sweep({"vehicle": ["car_1"]})))       # tree_1 says plant; the sweep says no plants
            self.assertEqual(result.returncode, 1)
            self.assertIn("tree_1 declares the class plant but the sweep does not list it there", result.stdout)

    def test_a_component_with_no_class_is_still_accepted_when_the_sweep_lists_it(self):
        with tempfile.TemporaryDirectory() as td:
            elements = [element(["door_1"], [None])]
            result = self.run_script(self.write(td, elements=elements, object_sweep=sweep({"opening": ["door_1"]})))
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_the_schema_requires_the_evidence_for_every_class_and_a_known_class(self):
        with tempfile.TemporaryDirectory() as td:
            no_evidence = sweep({"vehicle": ["car_1"], "plant": ["tree_1"]})
            del no_evidence[3]["evidence"]
            self.assertEqual(self.run_script(self.write(td, object_sweep=no_evidence)).returncode, 1)
            unknown = sweep({"vehicle": ["car_1"], "plant": ["tree_1"]})
            unknown[0]["object_class"] = "dragon"
            self.assertEqual(self.run_script(self.write(td, object_sweep=unknown)).returncode, 1)

    def test_the_class_lists_of_the_blueprint_the_sweep_and_the_cleanup_contract_are_one_list_and_the_master_names_each(self):
        blueprint = json.loads((ROOT / "schemas" / "mockup-blueprint.schema.json").read_text(encoding="utf-8"))
        from_component = blueprint["properties"]["elements"]["items"]["properties"]["separation_inventory"]["items"]["properties"]["object_class"]["enum"]
        from_sweep = blueprint["properties"]["object_sweep"]["items"]["properties"]["object_class"]["enum"]
        cleanup = json.loads((ROOT / "schemas" / "gamearts-cleanup.schema.json").read_text(encoding="utf-8"))
        from_cleanup = cleanup["properties"]["detached_components"]["items"]["properties"]["object_class"]["enum"]
        self.assertEqual(from_component, CLASSES)
        self.assertEqual(from_sweep, CLASSES)
        self.assertEqual(from_cleanup, CLASSES)
        master = next(ROOT.glob("GAME_ARTS_MASTER_STANDARD.md")).read_text(encoding="utf-8")
        section = master[master.index("**Object classes and the scene sweep.**"):]
        for name in CLASSES:
            self.assertIn(f"`{name}`", section[:3000], name)


if __name__ == "__main__":
    unittest.main()
