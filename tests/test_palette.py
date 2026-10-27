"""The palette owner (plan P11.3): deterministic extraction, a contract, and the colour maths the checks share."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit as kit

import gamearts_common as common  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_palette as palette  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_palette.py"


def art(path, colours, size=(20, 20), rows=None):
    """A picture of horizontal stripes in `colours` (`rows` of each, equal by default) on a key-colour field."""
    image = Image.new("RGBA", size, (255, 0, 255, 255))
    rows = rows or [max(1, (size[1] - 4) // len(colours))] * len(colours)
    top = 2
    for colour, height in zip(colours, rows):
        for y in range(top, top + height):
            for x in range(2, size[0] - 2):
                image.putpixel((x, y), colour + (255,))
        top += height
    image.save(path)
    return Path(path)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def extract(self, image, **kwargs):
        return palette.extract(image, name=kwargs.pop("name", "main"), output_dir=self.root / "out", **kwargs)

    def test_a_picture_within_the_limit_yields_its_exact_colours_most_used_first(self):
        image = art(self.root / "a.png", [(10, 20, 30), (200, 100, 50), (1, 2, 3)], rows=[8, 5, 2])
        result = self.extract(image, max_colours=8)
        self.assertEqual(result["method"], "exact")
        self.assertEqual([c["hex"] for c in result["colours"]], ["#0A141E", "#C86432", "#010203"])
        self.assertAlmostEqual(sum(c["share"] for c in result["colours"]), 1.0, places=3)

    def test_the_key_colour_and_transparent_pixels_are_not_part_of_the_palette(self):
        image = art(self.root / "a.png", [(10, 20, 30)])
        rgba = Image.open(image).convert("RGBA")
        rgba.putpixel((0, 0), (99, 99, 99, 0))
        rgba.save(image)
        result = self.extract(image, max_colours=8)
        self.assertEqual([c["hex"] for c in result["colours"]], ["#0A141E"])

    def test_the_same_picture_always_gives_the_same_palette(self):
        image = art(self.root / "a.png", [(10, 20, 30), (200, 100, 50), (1, 2, 3)])
        first = self.extract(image, max_colours=8, name="one")
        second = self.extract(image, max_colours=8, name="two")
        self.assertEqual(first["colours"], second["colours"])

    def test_a_picture_with_more_colours_is_reduced_and_says_so(self):
        gradient = Image.new("RGB", (64, 16))
        for x in range(64):
            for y in range(16):
                gradient.putpixel((x, y), (x * 4, y * 8, (x + y) % 200))
        path = self.root / "grad.png"
        gradient.save(path)
        first = self.extract(path, max_colours=16, name="one")
        second = self.extract(path, max_colours=16, name="two")
        self.assertEqual(first["method"], "median_cut")
        self.assertLessEqual(len(first["colours"]), 16)
        self.assertGreater(len(first["colours"]), 4)
        self.assertEqual(first["colours"], second["colours"])
        self.assertNotIn("pillow_version", first)

    def test_the_two_files_are_written_and_the_gimp_text_is_well_formed(self):
        image = art(self.root / "a.png", [(10, 20, 30), (200, 100, 50)], rows=[9, 6])
        self.extract(image, max_colours=8)
        data = json.loads((self.root / "out" / "main.palette.json").read_text(encoding="utf-8"))
        common.validate_schema(data, "gamearts-palette")
        lines = (self.root / "out" / "main.gpl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "GIMP Palette")
        self.assertEqual(lines[1], "Name: main")
        self.assertEqual(lines[2:4], ["Columns: 8", "#"])
        self.assertEqual([l.split()[:3] for l in lines[4:]], [["10", "20", "30"], ["200", "100", "50"]])

    def test_the_source_is_recorded_by_name_and_hash(self):
        image = art(self.root / "a.png", [(10, 20, 30)])
        result = self.extract(image, max_colours=8)
        self.assertEqual(result["source"], {"file": "a.png", "sha256": common.sha256_file(image)})

    def test_an_existing_palette_is_never_overwritten(self):
        image = art(self.root / "a.png", [(10, 20, 30)])
        self.extract(image, max_colours=8)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.extract(image, max_colours=8)

    def test_a_picture_with_no_artwork_and_a_zero_limit_are_refused(self):
        blank = self.root / "blank.png"
        Image.new("RGBA", (8, 8), (255, 0, 255, 255)).save(blank)
        with self.assertRaisesRegex(ValueError, "no artwork"):
            self.extract(blank, max_colours=8)
        image = art(self.root / "a.png", [(10, 20, 30)])
        with self.assertRaisesRegex(ValueError, "at least 1"):
            self.extract(image, max_colours=0, name="zero")


class LoadingTests(unittest.TestCase):
    def test_a_saved_palette_loads_as_colours(self):
        with tempfile.TemporaryDirectory() as td:
            image = art(Path(td) / "a.png", [(10, 20, 30), (200, 100, 50)])
            palette.extract(image, name="main", output_dir=Path(td), max_colours=8)
            loaded = palette.load_palette(Path(td) / "main.palette.json")
            self.assertEqual(loaded, [(10, 20, 30), (200, 100, 50)])

    def test_a_palette_that_breaks_its_contract_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.palette.json"
            path.write_text(json.dumps({"schema_version": "1.0", "name": "bad", "method": "exact", "max_colours": 4, "colours": [], "source": {"file": "x", "sha256": "0" * 64}}))
            with self.assertRaisesRegex(ValueError, "contract violation"):
                palette.load_palette(path)

    def test_the_palette_a_project_points_at_is_found_inside_the_game_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / ".gamearts" / "palette"
            image = art(root / "a.png", [(10, 20, 30)])
            palette.extract(image, name="main", output_dir=folder, max_colours=8, root=root)
            settings = kit.settings(art_style={"id": "pixel_art", "palette_reference": ".gamearts/palette/main.palette.json"})
            self.assertEqual(palette.project_palette(root, settings), [(10, 20, 30)])
            self.assertIsNone(palette.project_palette(root, kit.settings(art_style={"id": "pixel_art", "palette_reference": "a warm cream and brown palette"})))
            self.assertIsNone(palette.project_palette(root, kit.settings()))
            outside = kit.settings(art_style={"id": "pixel_art", "palette_reference": "../elsewhere.palette.json"})
            with self.assertRaisesRegex(ValueError, "inside the game"):
                palette.project_palette(root, outside)


class ColourMathTests(unittest.TestCase):
    def test_lab_of_white_black_and_grey_is_what_the_standard_says(self):
        l, a, b = palette.rgb_to_lab((255, 255, 255))
        self.assertAlmostEqual(l, 100.0, places=1)
        self.assertAlmostEqual(a, 0.0, places=1)
        self.assertAlmostEqual(b, 0.0, places=1)
        self.assertEqual(palette.rgb_to_lab((0, 0, 0)), (0.0, 0.0, 0.0))
        l, a, b = palette.rgb_to_lab((119, 119, 119))
        self.assertAlmostEqual(l, 50.0, delta=0.6)
        self.assertAlmostEqual(a, 0.0, places=1)

    def test_a_colour_is_at_distance_zero_from_itself_and_the_distance_is_symmetric(self):
        self.assertEqual(palette.lab_distance((12, 200, 90), (12, 200, 90)), 0.0)
        self.assertAlmostEqual(palette.lab_distance((12, 200, 90), (200, 12, 90)), palette.lab_distance((200, 12, 90), (12, 200, 90)))
        self.assertGreater(palette.lab_distance((0, 0, 0), (255, 255, 255)), 90)

    def test_the_nearest_palette_colour_is_found_by_perceived_distance(self):
        colours = [(0, 0, 0), (255, 255, 255), (200, 40, 40)]
        self.assertEqual(palette.nearest((190, 50, 50), colours), (200, 40, 40))
        self.assertEqual(palette.nearest((20, 20, 20), colours), (0, 0, 0))
        self.assertEqual(palette.nearest((240, 240, 240), colours), (255, 255, 255))


class CommandLineTests(unittest.TestCase):
    def test_the_command_saves_the_palette_inside_the_game(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = art(root / "board.png", [(10, 20, 30), (200, 100, 50)])
            done = subprocess.run([sys.executable, str(SCRIPT), "extract", "--game-root", td, "--image", str(image), "--name", "main", "--max-colours", "8"],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout)
            self.assertEqual(result["palette_reference"], ".gamearts/palette/main.palette.json")
            self.assertTrue((root / ".gamearts" / "palette" / "main.palette.json").is_file())
            self.assertTrue((root / ".gamearts" / "palette" / "main.gpl").is_file())

    def test_a_blocked_command_says_why_and_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            done = subprocess.run([sys.executable, str(SCRIPT), "extract", "--game-root", td, "--image", str(Path(td) / "nothing.png"), "--name", "x"],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 1)
            self.assertIn("BLOCKED", done.stderr)


if __name__ == "__main__":
    unittest.main()
