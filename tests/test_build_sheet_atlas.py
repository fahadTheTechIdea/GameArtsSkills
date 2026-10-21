"""Tests for the actual sprite-sheet/atlas builder; run in CI with Pillow."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_sheet_atlas.py"
spec = importlib.util.spec_from_file_location("build_sheet_atlas", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
PINK = (255, 0, 255, 255)


class AtlasBuilderTests(unittest.TestCase):
    def create_frame(self, path, width, height, color, point):
        im = Image.new("RGBA", (width, height), PINK)
        im.putpixel(point, color)
        im.save(path)

    def make_manifest(self, root):
        self.create_frame(root / "south.png", 12, 10, (20, 50, 90, 255), (4, 5))
        self.create_frame(root / "east.png", 8, 14, (30, 90, 20, 255), (3, 8))
        return {
            "_input_dir": str(root),
            "name": "test_scene_asset_idle_v001",
            "asset_id": "test-asset",
            "columns": 2,
            "padding": 2,
            "frames": [
                {"file": "south.png", "name": "S", "direction": "S",
                 "pivot": [4, 9], "anchors": {"hinge": [2, 3]}, "duration_ms": 120},
                {"file": "east.png", "name": "E", "direction": "E",
                 "pivot": [3, 13], "anchors": {"hinge": [1, 5]}, "duration_ms": 150}
            ]
        }

    def test_generates_png_and_matching_atlas_with_stable_pivots(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = self.make_manifest(root)
            png, js = mod.build(manifest, root / "generated")
            self.assertTrue(png.exists() and js.exists())
            atlas = json.loads(js.read_text())
            with Image.open(png) as im:
                self.assertEqual(list(im.size), atlas["image_size"])
                self.assertEqual(im.convert("RGBA").getchannel("A").getextrema(), (255, 255))
                self.assertEqual(im.convert("RGBA").getpixel((0, 0)), PINK)
                self.assertEqual(im.convert("RGBA").getpixel((6, 11)), (20, 50, 90, 255))
            self.assertEqual(len(atlas["frames"]), 2)
            self.assertEqual(atlas["frames"][0]["pivot"], atlas["frames"][1]["pivot"])
            self.assertEqual(atlas["frames"][0]["anchors"]["hinge"], [4, 7])
            self.assertEqual(atlas["frames"][0]["duration_ms"], 120)
            self.assertEqual(atlas["frames"][1]["duration_ms"], 150)
            self.assertEqual(atlas["frames"][0]["source_ink_bounds"], [4, 5, 1, 1])
            self.assertEqual(atlas["validation"]["godot_runtime"], "not_tested")

    def test_refuses_accidental_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = self.make_manifest(root)
            mod.build(manifest, root / "generated")
            with self.assertRaises(FileExistsError):
                mod.build(manifest, root / "generated")

    def test_rejects_nonopaque_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = self.make_manifest(root)
            im = Image.new("RGBA", (12, 10), PINK)
            im.putpixel((1, 1), (0, 0, 0, 0))
            im.save(root / "south.png")
            with self.assertRaisesRegex(ValueError, "fully opaque"):
                mod.build(manifest, root / "generated")

    def test_rejects_missing_anchors_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = self.make_manifest(root)
            manifest["frames"][1]["anchors"] = {"hinge": "guess"}
            with self.assertRaisesRegex(ValueError, "anchor"):
                mod.build(manifest, root / "generated")

    def test_rejects_bad_slug(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = self.make_manifest(root)
            manifest["name"] = "../escape"
            with self.assertRaises(ValueError):
                mod.build(manifest, root / "generated")


if __name__ == "__main__":
    unittest.main()
