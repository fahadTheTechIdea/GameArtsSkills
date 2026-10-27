"""The style-exploration contact sheet (plan P11.2): candidate mockups side by side under letters, as a review aid that is never art."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

import gamearts_testkit as kit
from gamearts_testkit import write_settings

import build_contact_sheet as sheet  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_contact_sheet.py"
RED, BLUE, GREEN = (200, 30, 30), (30, 30, 200), (30, 160, 30)


class SheetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        write_settings(self.root, art_style={"id": "pixel_art"})

    def tearDown(self):
        self._tmp.cleanup()

    def register(self, mockup_id, picture=None, revision="v001", scope="style"):
        image, metadata = kit.make_mockup(self.root, mockup_id, revision, scope, picture_image=picture or Image.new("RGB", (64, 40), RED))
        life.register_mockup(self.root, metadata, image)
        return image

    def make(self, count, **kwargs):
        for index in range(count):
            self.register(f"look-{index}", Image.new("RGB", (64, 40), (40 * index + 20, 60, 90)))
        return sheet.build(self.root, [f"look-{i}:v001" for i in range(count)], **kwargs)

    def picture(self, result):
        return Image.open(self.root / result["sheet"]).convert("RGB")


class LayoutTests(SheetCase):
    def test_one_to_six_candidates_get_letters_in_order(self):
        for count in (1, 2, 4, 6):
            with self.subTest(count):
                result = self.make(count) if count == 1 else sheet.build(self.root, [f"look-{i}:v001" for i in range(count)])
                self.assertEqual([c["letter"] for c in result["candidates"]], list("ABCDEF")[:count])
                self.assertEqual([c["mockup_id"] for c in result["candidates"]], [f"look-{i}" for i in range(count)])
            if count == 1:
                for index in range(1, 6):
                    self.register(f"look-{index}", Image.new("RGB", (64, 40), (40 * index + 20, 60, 90)))

    def test_none_and_more_than_six_are_refused(self):
        with self.assertRaisesRegex(ValueError, "1 to 6 candidates; 0 were given"):
            sheet.build(self.root, [])
        for index in range(7):
            self.register(f"look-{index}")
        with self.assertRaisesRegex(ValueError, "1 to 6 candidates; 7 were given"):
            sheet.build(self.root, [f"look-{i}:v001" for i in range(7)])

    def test_the_sheet_is_a_grid_of_three_columns(self):
        for index in range(5):
            self.register(f"look-{index}")
        one = sheet.build(self.root, ["look-0:v001"], name="one")
        five = sheet.build(self.root, [f"look-{i}:v001" for i in range(5)], name="five")
        with self.picture(one) as a, self.picture(five) as b:
            self.assertEqual(a.width, sheet.DEFAULT_CELL[0] + 2 * sheet.GAP)
            self.assertEqual(b.width, 3 * sheet.DEFAULT_CELL[0] + 4 * sheet.GAP)
            self.assertEqual(b.height, 2 * (sheet.DEFAULT_CELL[1] + sheet.LABEL_HEIGHT) + 3 * sheet.GAP)

    def test_labels_sit_below_the_art_and_never_over_it(self):
        self.register("look-0", Image.new("RGB", (64, 40), RED))
        result = sheet.build(self.root, ["look-0:v001"], cell=(320, 200))
        with self.picture(result) as shown:
            art_box = (sheet.GAP, sheet.GAP, sheet.GAP + 320, sheet.GAP + 200)
            art = shown.crop(art_box)
            self.assertEqual(art.getcolors(maxcolors=10)[0][1], RED)  # 64x40 enlarged 5x fills the 320x200 area exactly: only the art is there
            label = shown.crop((sheet.GAP, sheet.GAP + 200, sheet.GAP + 320, sheet.GAP + 200 + sheet.LABEL_HEIGHT))
            self.assertGreater(max(max(c) for _, c in label.getcolors(maxcolors=1 << 16)), 200)  # light text was drawn in the band
            below_art = shown.crop((0, sheet.GAP + 200, shown.width, shown.height))
            above_art = shown.crop((0, 0, shown.width, sheet.GAP))
            self.assertEqual(above_art.getcolors(maxcolors=4), [(above_art.width * above_art.height, sheet.BACKGROUND)])
            self.assertGreater(len(below_art.getcolors(maxcolors=1 << 16)), 2)

    def test_proportions_are_kept_and_the_picture_is_centred_in_its_area(self):
        self.register("wide", Image.new("RGB", (100, 20), BLUE))
        result = sheet.build(self.root, ["wide:v001"], cell=(300, 200), scaling="smooth")
        with self.picture(result) as shown:
            area = shown.crop((sheet.GAP, sheet.GAP, sheet.GAP + 300, sheet.GAP + 200))
            box = ImageChops.difference(area, Image.new("RGB", area.size, sheet.BACKGROUND)).getbbox()
            self.assertEqual(box[2] - box[0], 300)
            self.assertAlmostEqual((box[3] - box[1]), 60, delta=1)
            self.assertAlmostEqual(box[1], (200 - 60) / 2, delta=2)


class ScalingTests(SheetCase):
    def test_pixel_art_is_enlarged_by_whole_numbers_without_new_colours(self):
        small = Image.new("RGB", (16, 10), RED)
        small.putpixel((3, 3), BLUE)
        self.register("tiny", small)
        result = sheet.build(self.root, ["tiny:v001"], cell=(160, 100))
        with self.picture(result) as shown:
            area = shown.crop((sheet.GAP, sheet.GAP, sheet.GAP + 160, sheet.GAP + 100))
            self.assertEqual({c for _, c in area.getcolors(maxcolors=100)}, {RED, BLUE})
            self.assertEqual(area.getpixel((35, 35)), BLUE)

    def test_the_same_picture_is_scaled_smoothly_for_other_looks(self):
        small = Image.new("RGB", (16, 10), RED)
        small.putpixel((3, 3), BLUE)
        self.register("tiny", small)
        result = sheet.build(self.root, ["tiny:v001"], cell=(160, 100), scaling="smooth")
        with self.picture(result) as shown:
            self.assertGreater(len(shown.crop((sheet.GAP, sheet.GAP, sheet.GAP + 160, sheet.GAP + 100)).getcolors(maxcolors=10000)), 2)

    def test_a_large_pixel_picture_is_averaged_when_it_has_to_shrink(self):
        checker = Image.new("RGB", (640, 400))
        for y in range(400):
            for x in range(640):
                checker.putpixel((x, y), (255, 255, 255) if (x + y) % 2 else (0, 0, 0))
        self.register("fine", checker)
        result = sheet.build(self.root, ["fine:v001"], cell=(160, 100))
        with self.picture(result) as shown:
            middle = shown.getpixel((sheet.GAP + 80, sheet.GAP + 50))
            self.assertTrue(100 < middle[0] < 160, middle)  # an average, not a lucky black or white pixel


class RefusalTests(SheetCase):
    def test_an_unregistered_mockup_is_refused(self):
        with self.assertRaisesRegex(ValueError, "ghost v001 is not a registered mockup"):
            sheet.build(self.root, ["ghost:v001"])

    def test_a_revoked_mockup_is_never_shown(self):
        self.register("old")
        life.revoke(self.root, "mockups", "old", "not the look", "v001")
        with self.assertRaisesRegex(ValueError, "revoked"):
            sheet.build(self.root, ["old:v001"])

    def test_a_mockup_whose_image_changed_is_refused(self):
        image = self.register("edited")
        Image.new("RGB", (64, 40), GREEN).save(image)
        located = next(p for p in (self.root / ".gamearts/outputs/mockups").rglob("*edited_mockup_v001.png"))
        Image.new("RGB", (64, 40), GREEN).save(located)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            sheet.build(self.root, ["edited:v001"])

    def test_a_missing_image_is_refused(self):
        self.register("gone")
        for path in (self.root / ".gamearts/outputs/mockups").rglob("*gone_mockup_v001.png"):
            path.unlink()
        with self.assertRaisesRegex(ValueError, "image file is missing"):
            sheet.build(self.root, ["gone:v001"])

    def test_a_reference_without_a_revision_says_how_to_write_it(self):
        for text in ("look-0", "look-0:1", "look-0:latest"):
            with self.subTest(text), self.assertRaisesRegex(ValueError, "mockup-id:revision"):
                sheet.build(self.root, [text])

    def test_a_bad_sheet_name_or_tiny_area_is_refused(self):
        self.register("look-0")
        with self.assertRaisesRegex(ValueError, "letters, digits"):
            sheet.build(self.root, ["look-0:v001"], name="../escape")
        with self.assertRaisesRegex(ValueError, "at least 64"):
            sheet.build(self.root, ["look-0:v001"], cell=(10, 10))
        self.assertFalse((self.root / sheet.EXPLORATION).exists())


class ReviewAidTests(SheetCase):
    def test_the_sheet_is_written_outside_the_outputs_and_the_records_do_not_change(self):
        self.register("look-0")
        before = common.sha256_file(self.root / ".gamearts/outputs/manifests/mockups.json")
        result = sheet.build(self.root, ["look-0:v001"])
        self.assertTrue(result["sheet"].startswith(".gamearts/system/exploration/"))
        self.assertEqual(common.sha256_file(self.root / ".gamearts/outputs/manifests/mockups.json"), before)
        self.assertEqual(list((self.root / ".gamearts/outputs").rglob("candidates*")), [])
        self.assertIn("never registered", result["note"])

    def test_the_letter_map_is_saved_beside_the_picture_with_hashes(self):
        self.register("look-0")
        self.register("look-1", Image.new("RGB", (64, 40), BLUE))
        result = sheet.build(self.root, ["look-1:v001", "look-0:v001"])
        saved = json.loads((self.root / result["map"]).read_text(encoding="utf-8"))
        self.assertEqual([(c["letter"], c["mockup_id"]) for c in saved["candidates"]], [("A", "look-1"), ("B", "look-0")])
        record = next(r for r in common.mockup_records(self.root) if r["mockup_id"] == "look-1")
        self.assertEqual(saved["candidates"][0]["sha256"], record["sha256"])

    def test_building_again_replaces_the_sheet_and_leaves_no_temporary_file(self):
        self.register("look-0")
        sheet.build(self.root, ["look-0:v001"])
        sheet.build(self.root, ["look-0:v001"])
        self.assertEqual(sorted(p.name for p in (self.root / sheet.EXPLORATION).iterdir()), ["candidates.json", "candidates.png"])

    def test_unreadable_settings_are_reported_and_smooth_scaling_is_used(self):
        self.register("look-0")
        (self.root / ".gamearts" / "project.json").write_text("{not json", encoding="utf-8")
        result = sheet.build(self.root, ["look-0:v001"])
        self.assertEqual(result["scaling"], "smooth")
        self.assertIn("could not be read", result["warning"])


class CommandTests(SheetCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--game-root", str(self.root), *args], capture_output=True, text=True)

    def test_the_command_builds_the_sheet_from_repeated_mockup_arguments(self):
        self.register("look-0")
        self.register("look-1", Image.new("RGB", (64, 40), BLUE))
        done = self.run_script("--mockup", "look-0:v001", "--mockup", "look-1:v001", "--name", "round-one")
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(len(report["candidates"]), 2)
        self.assertTrue((self.root / report["sheet"]).is_file())

    def test_a_refusal_says_why_and_exits_one(self):
        done = self.run_script("--mockup", "ghost:v001")
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)
        self.assertIn("not a registered mockup", done.stderr)


if __name__ == "__main__":
    unittest.main()
