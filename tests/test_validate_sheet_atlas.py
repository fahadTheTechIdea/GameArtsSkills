"""The sheet and atlas validator: geometry plus the exact-key and near-key pixel contract."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gamearts_testkit import build_sheet, key_image, make_sheet

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_sheet_atlas.py"
sys.path.insert(0, str(SCRIPT.parent))
import validate_sheet_atlas as validator  # noqa: E402


class SheetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        files = make_sheet(self.folder, "sheet", "asset-1")
        self.image, self.atlas = self.folder / files[0], self.folder / files[1]

    def tearDown(self):
        self._tmp.cleanup()

    def issues(self):
        return validator.validate(self.image, self.atlas)

    def edit_atlas(self, change):
        data = json.loads(self.atlas.read_text())
        change(data)
        self.atlas.write_text(json.dumps(data))

    def edit_image(self, change):
        picture = Image.open(self.image).convert("RGBA")
        change(picture)
        picture.save(self.image)

    def gutter_x(self):
        return json.loads(self.atlas.read_text())["cell_size"][0] + 1


class PixelContractTests(SheetCase):
    def test_a_sheet_built_by_the_builder_validates(self):
        self.assertEqual(self.issues(), [])

    def test_a_stray_pixel_outside_every_frame_fails(self):
        self.edit_image(lambda p: p.putpixel((self.gutter_x(), 0), (1, 2, 3, 255)))
        self.assertTrue(any("not exact #FF00FF" in i for i in self.issues()))

    def test_a_near_key_fringe_pixel_inside_a_frame_fails(self):
        self.edit_image(lambda p: p.putpixel((2, 2), (250, 6, 252, 255)))
        self.assertTrue(any("near-#FF00FF" in i for i in self.issues()))

    def test_the_tolerance_is_a_stated_parameter(self):
        self.edit_image(lambda p: p.putpixel((2, 2), (240, 0, 255, 255)))  # distance 15
        self.assertTrue(any("near-" in i for i in validator.validate(self.image, self.atlas, tolerance=24)))
        self.assertEqual(validator.validate(self.image, self.atlas, tolerance=10), [])

    def test_a_transparent_pixel_fails(self):
        self.edit_image(lambda p: p.putpixel((2, 2), (255, 0, 255, 0)))
        self.assertTrue(any("alpha" in i for i in self.issues()))

    def test_an_atlas_that_allows_near_key_accepts_it(self):
        self.edit_image(lambda p: p.putpixel((2, 2), (250, 6, 252, 255)))
        self.edit_atlas(lambda a: a.update(allow_near_key=True))
        self.assertEqual(self.issues(), [])

    def test_a_full_bleed_sheet_may_be_painted_edge_to_edge(self):
        painted = Image.new("RGBA", (30, 20), (40, 90, 30, 255))
        painted.save(self.folder / "tile.png")
        build_sheet({"_input_dir": str(self.folder), "name": "bleed", "asset_id": "tile", "columns": 1, "full_bleed": True,
                     "frames": [{"file": "tile.png", "name": "t", "pivot": [0, 0]}]}, self.folder)
        self.assertEqual(validator.validate(self.folder / "bleed.png", self.folder / "bleed.atlas.json"), [])

    def test_the_builder_refuses_what_the_validator_would_flag(self):
        key_image((6, 6), {(1, 1): (250, 6, 252, 255)}).save(self.folder / "fringe.png")
        with self.assertRaisesRegex(ValueError, "near-#FF00FF"):
            build_sheet({"_input_dir": str(self.folder), "name": "bad", "asset_id": "x", "columns": 1,
                         "frames": [{"file": "fringe.png", "name": "f"}]}, self.folder)
        self.assertFalse((self.folder / "bad.png").exists())


class GeometryTests(SheetCase):
    def test_a_rectangle_outside_the_image_fails(self):
        self.edit_atlas(lambda a: a["frames"][0].update(rect=[0, 0, 9999, 9999]))
        self.assertTrue(any("out of bounds" in i for i in self.issues()))

    def test_a_pivot_outside_its_cell_fails(self):
        self.edit_atlas(lambda a: a["frames"][0].update(pivot=[500, 1]))
        self.assertTrue(any("pivot" in i and "outside" in i for i in self.issues()))

    def test_overlapping_frames_fail(self):
        def overlap(a):
            a["frames"][1]["rect"] = list(a["frames"][0]["rect"])
        self.edit_atlas(overlap)
        self.assertTrue(any("overlap" in i for i in self.issues()))

    def test_an_atlas_that_names_a_different_image_fails(self):
        self.edit_atlas(lambda a: a.update(image="other.png"))
        self.assertTrue(any("names image" in i for i in self.issues()))

    def test_an_image_whose_size_disagrees_with_the_atlas_fails(self):
        self.edit_atlas(lambda a: a.update(image_size=[1, 1]))
        self.assertTrue(any("image_size" in i for i in self.issues()))

    def test_a_missing_image_is_reported(self):
        self.image.unlink()
        self.assertTrue(any("missing" in i for i in self.issues()))

    def test_an_invalid_atlas_is_a_contract_failure_not_a_crash(self):
        self.edit_atlas(lambda a: a.pop("frames"))
        self.assertTrue(any("atlas contract" in i for i in self.issues()))
        self.atlas.write_text("{not json")
        self.assertTrue(any("atlas contract" in i for i in self.issues()))

    def test_a_non_png_sheet_is_reported(self):
        Image.open(self.image).convert("RGB").save(self.image, format="BMP")
        self.assertTrue(any("not PNG" in i for i in self.issues()))


class CommandLineTests(SheetCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)

    def test_exit_status_and_honest_wording(self):
        ok = self.run_cli(self.image, self.atlas)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("NOT assessed", ok.stdout)
        self.edit_image(lambda p: p.putpixel((self.gutter_x(), 0), (1, 2, 3, 255)))
        bad = self.run_cli(self.image, self.atlas)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("FAIL", bad.stdout)

    def test_the_tolerance_option_reaches_the_check(self):
        self.edit_image(lambda p: p.putpixel((2, 2), (240, 0, 255, 255)))
        self.assertEqual(self.run_cli(self.image, self.atlas).returncode, 1)
        self.assertEqual(self.run_cli(self.image, self.atlas, "--tolerance", 10).returncode, 0)


if __name__ == "__main__":
    unittest.main()
