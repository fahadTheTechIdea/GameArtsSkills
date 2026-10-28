"""The removal step of the mockup analyzer: objects with masks removed from the scene and their places reconstructed, as a draft; everything else untouched."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image  # noqa: E402

import gamearts_common as common  # noqa: E402
import remove_scene_objects as remover  # noqa: E402
from test_extract_scene_objects import OBJECTS, blueprint, mockup  # noqa: E402

SCRIPT = ROOT / "scripts" / "remove_scene_objects.py"
FILL = (1, 2, 3)

try:
    import cv2  # noqa: F401
    HAVE_CV = True
except ImportError:
    HAVE_CV = False


class FlatInpainter:
    """A stand-in: every masked pixel becomes one flat colour, so what was and was not removed is exact."""
    id = "flat-stand-in"

    def inpaint(self, image, mask):
        out = image.copy()
        out.paste(FILL, mask=mask)
        return out


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        mockup().save(self.root / "mock.png")
        import hashlib
        self.sha = hashlib.sha256((self.root / "mock.png").read_bytes()).hexdigest()
        self.out = self.root / "out"

    def write(self, masked=("hall", "oak", "door"), status="approved", mask_size=None, missing=()):
        data = blueprint(status=status, sha=self.sha if status == "approved" else None)
        (self.root / "masks").mkdir(exist_ok=True)
        for component in data["elements"][0]["separation_inventory"]:
            object_id = component["component_id"]
            if object_id not in masked:
                continue
            region = next(o for o in OBJECTS if o[0] == object_id)[2]
            component["removal_mask_ref"] = f"masks/{object_id}.png"
            if object_id in missing:
                (self.root / "masks" / f"{object_id}.png").unlink(missing_ok=True)
            else:
                Image.new("L", mask_size or (region[2], region[3]), 255).save(self.root / "masks" / f"{object_id}.png")
        path = self.root / "bp.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def remove(self, path=None, inpainter=None, **kw):
        return remover.remove(path or self.write(), self.root / "mock.png", kw.pop("out", self.out), inpainter or FlatInpainter(), **kw)

    def picture(self, name):
        with Image.open(self.out / name) as opened:
            opened.load()
            return opened.convert("RGB").copy()


class RemoveTests(Case):
    def test_the_pixels_of_objects_with_masks_are_replaced_and_every_other_pixel_is_untouched(self):
        report = self.remove(self.write(masked=("oak", "door")), grow=0, max_share=1.0)
        clean, source = self.picture("clean_parent_draft.png"), mockup()
        removed = [o for o in OBJECTS if o[0] in ("oak", "door")]
        inside = {(x, y) for _, _, (rx, ry, w, h), _ in removed for x in range(rx, rx + w) for y in range(ry, ry + h)}
        for x in range(100):
            for y in range(80):
                self.assertEqual(clean.getpixel((x, y)), FILL if (x, y) in inside else source.getpixel((x, y)), (x, y))
        self.assertEqual(report["removed"], ["door", "oak"])

    def test_an_object_with_no_mask_is_not_removed_and_is_listed(self):
        report = self.remove(grow=0, max_share=1.0)
        clean = self.picture("clean_parent_draft.png")
        self.assertEqual(sorted(report["not_removed"]["no_mask"]), ["car", "walker"])
        self.assertEqual(clean.getpixel((20, 60)), mockup().getpixel((20, 60)))                  # the car's pixels are still there

    def test_growing_the_masks_takes_in_a_margin_around_each_object(self):
        grown = self.picture_after(grow=2)
        flat = self.picture_after(grow=0, out="other")
        oak = next(o for o in OBJECTS if o[0] == "oak")[2]
        just_outside = (oak[0] + oak[2] + 1, oak[1] + 5)                                           # two pixels past the oak's right edge, on plain ground
        self.assertEqual(grown.getpixel(just_outside), FILL)
        self.assertEqual(flat.getpixel(just_outside), mockup().getpixel(just_outside))

    def picture_after(self, out="out", **kw):
        self.remove(out=self.root / out, max_share=1.0, **kw)
        with Image.open(self.root / out / "clean_parent_draft.png") as opened:
            opened.load()
            return opened.convert("RGB").copy()

    def test_each_object_gets_a_full_size_binary_removal_mask_in_its_class_folder(self):
        self.remove(grow=0, max_share=1.0)
        mask = self.picture("removal_masks/plant/oak.png").convert("L")
        self.assertEqual(mask.size, (100, 80))
        oak = next(o for o in OBJECTS if o[0] == "oak")[2]
        self.assertEqual((mask.getpixel((oak[0], oak[1])), mask.getpixel((oak[0] - 1, oak[1]))), (255, 0))
        self.assertTrue(set(mask.getdata()) <= {0, 255})
        self.assertFalse((self.out / "removal_masks" / "building").exists())                       # a building is an area class: never removed

    def test_the_share_reconstructed_and_the_overlapping_masks_are_reported(self):
        path = self.write(masked=("oak", "door", "walker"))
        report = self.remove(path, grow=0, max_share=1.0)
        door, oak, walker = (next(o for o in OBJECTS if o[0] == n)[2] for n in ("door", "oak", "walker"))
        covered = {(x, y) for rx, ry, w, h in (door, oak, walker) for x in range(rx, rx + w) for y in range(ry, ry + h)}
        self.assertEqual(report["reconstructed_share"], round(len(covered) / 8000, 4))
        self.assertEqual(report["overlapping_masks"], [["door", "walker"]])                          # the walker stands in front of the door

    def test_the_report_says_the_pixels_are_inferred_and_what_was_not_assessed(self):
        report = self.remove(max_share=1.0)
        self.assertEqual(report["inpainter"], "flat-stand-in")
        self.assertIn("inferred", report["pixel_status"])
        self.assertTrue(any("reviewed by a person" in line for line in report["not_assessed"]))
        self.assertFalse(report["provisional"])
        self.assertEqual(common.read_json(self.out / "removal_report.json")["mockup_sha256"], self.sha)


class PolicyTests(Case):
    def test_an_object_of_an_area_class_is_never_removed_however_small(self):
        report = self.remove(self.write(masked=("hall", "oak")), grow=0, max_share=1.0)
        self.assertEqual(report["removed"], ["oak"])
        self.assertEqual(report["not_removed"]["area_class"], ["hall"])
        self.assertEqual(self.picture("clean_parent_draft.png").getpixel((10, 10)), mockup().getpixel((10, 10)))      # the hall's pixels are still there

    def test_an_object_whose_mask_covers_too_much_of_the_picture_is_left_and_listed_with_the_reason(self):
        report = self.remove(self.write(masked=("oak", "door")), grow=0, max_share=0.05)               # the oak is 600 of 8000 pixels, the door 288
        self.assertEqual(report["removed"], ["door"])
        self.assertEqual(report["not_removed"]["too_large"], ["oak"])
        self.assertEqual(report["max_share"], 0.05)

    def test_a_share_outside_zero_to_one_is_refused(self):
        for index, bad in enumerate((0, -0.1, 1.5)):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "above 0 and at most 1"):
                self.remove(max_share=bad, out=self.root / f"share{index}")


class RefusalTests(Case):
    def test_an_unapproved_blueprint_needs_provisional_and_is_then_labelled(self):
        pending = self.write(status="pending_approval")
        with self.assertRaisesRegex(ValueError, "--provisional"):
            self.remove(pending)
        self.assertFalse(self.out.exists())
        self.assertTrue(self.remove(pending, provisional=True, max_share=1.0)["provisional"])

    def test_nothing_with_a_mask_a_mask_of_another_size_a_missing_mask_and_a_bad_grow_are_refused(self):
        with self.assertRaisesRegex(ValueError, "no object can be removed"):
            self.remove(self.write(masked=()))
        with self.assertRaisesRegex(ValueError, "the mask is 5 x 5 and the region is 20 x 30"):
            self.remove(self.write(masked=("oak",), mask_size=(5, 5)), out=self.root / "b", max_share=1.0)
        with self.assertRaisesRegex(ValueError, "is not beside the blueprint"):
            self.remove(self.write(masked=("oak",), missing=("oak",)), out=self.root / "c", max_share=1.0)
        with self.assertRaisesRegex(ValueError, "zero or more"):
            self.remove(grow=-1, out=self.root / "d")
        for name in "bcd":
            self.assertFalse((self.root / name).exists())

    def test_a_folder_with_something_in_it_a_bad_sweep_and_a_wrong_sized_result_are_refused(self):
        self.out.mkdir()
        (self.out / "old.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "is not empty"):
            self.remove(max_share=1.0)
        data = common.read_json(self.write())
        data["object_sweep"] = data["object_sweep"][:-1]
        (self.root / "bad.json").write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sweep is inconsistent"):
            self.remove(self.root / "bad.json", out=self.root / "e", max_share=1.0)

        class Wrong(FlatInpainter):
            def inpaint(self, image, mask):
                return Image.new("RGB", (5, 5))
        with self.assertRaisesRegex(ValueError, "another size"):
            self.remove(inpainter=Wrong(), out=self.root / "f", max_share=1.0)

    def test_the_command_refuses_an_unapproved_blueprint_in_words(self):
        path = self.write(status="pending_approval")
        done = subprocess.run([sys.executable, str(SCRIPT), "remove", "--blueprint", str(path), "--mockup", str(self.root / "mock.png"), "--output-dir", str(self.out)],
                              capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertTrue("--provisional" in done.stderr or "opencv-python" in done.stderr)


class DependencyTests(unittest.TestCase):
    def test_a_missing_opencv_is_a_refusal_that_says_what_to_install(self):
        code = "import sys; sys.modules['cv2'] = None; sys.path.insert(0, %r); import remove_scene_objects as r; r.TeleaInpainter()" % str(ROOT / "scripts")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("optional extra", done.stderr)


@unittest.skipUnless(HAVE_CV, "opencv-python is not installed: the real-inpainting test did NOT run")
class RealInpaintTests(unittest.TestCase):
    def test_the_real_inpainter_fills_a_hole_in_a_plain_surface_from_its_surroundings(self):
        image = Image.new("RGB", (60, 60), (100, 140, 90))
        image.paste((250, 0, 0), (20, 20, 40, 40))                       # an object on a flat green ground
        mask = Image.new("L", (60, 60), 0)
        mask.paste(255, (19, 19, 41, 41))
        filled = remover.TeleaInpainter().inpaint(image, mask)
        self.assertEqual(filled.size, (60, 60))
        r, g, b = filled.getpixel((30, 30))
        self.assertTrue(abs(r - 100) < 12 and abs(g - 140) < 12 and abs(b - 90) < 12, (r, g, b))     # the red is gone, the ground is back
        self.assertEqual(filled.getpixel((5, 5)), (100, 140, 90))                                       # outside the mask nothing moved


if __name__ == "__main__":
    unittest.main()
