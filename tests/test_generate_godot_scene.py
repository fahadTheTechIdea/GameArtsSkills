"""Tests native scene generation with synthetic game project fixtures."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_godot_scene.py"
spec = importlib.util.spec_from_file_location("generate_godot_scene", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SceneGenerationTests(unittest.TestCase):
    def fixture(self, tmp):
        root = Path(tmp)
        addon = root / "addons" / "gamearts"
        addon.mkdir(parents=True)
        (addon / "game_arts_component.gd").write_text("extends Node2D\n")
        bundle = root / ".gamearts" / "outputs" / "assets" / "generated" / "art_v001" / "art_v001.bundle.json"
        bundle.parent.mkdir(parents=True)
        bundle.write_text(json.dumps({"asset_id": "art_v001", "directions": ["S", "E"],
                                      "component_order": ["base"]}))
        return root, bundle

    def test_generates_referencing_native_scene(self):
        with tempfile.TemporaryDirectory() as td:
            root, bundle = self.fixture(td)
            output = mod.generate(bundle, root)
            self.assertTrue(output.exists())
            data = output.read_text()
            self.assertIn('type="Node2D"', data)
            self.assertIn('res://addons/gamearts/game_arts_component.gd', data)
            self.assertIn('direction = "S"', data)
            self.assertIn('res://.gamearts/outputs/assets/generated/art_v001/art_v001.bundle.json', data)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root, bundle = self.fixture(td)
            mod.generate(bundle, root)
            with self.assertRaises(FileExistsError):
                mod.generate(bundle, root)

    def test_refuses_bundle_outside_project(self):
        with tempfile.TemporaryDirectory() as td:
            root, bundle = self.fixture(td)
            outer = root.parent / "external_fixture.bundle.json"
            # Create a separate project-relative-path attempt without touching outer path.
            with tempfile.TemporaryDirectory() as other:
                outside = Path(other) / "outside.bundle.json"
                outside.write_text(bundle.read_text())
                with self.assertRaisesRegex(ValueError, "inside"):
                    mod.generate(outside, root)


if __name__ == "__main__":
    unittest.main()
