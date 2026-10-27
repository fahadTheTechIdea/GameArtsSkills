"""The matte (plan P12.4): true alpha from the image tool is split into the key-colour sheet and a coverage companion; the pair is checked, recorded in
the atlas, used by the runtime export, and refused for looks with hard edges."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)
from gamearts_testkit import settings as default_settings
from PIL import Image

import build_sheet_atlas as builder  # noqa: E402
import export_runtime as runtime_export  # noqa: E402
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_matte as matte_rules  # noqa: E402
import validate_sheet_atlas as sheet_validator  # noqa: E402

KEY = common.KEY_RGB
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_matte.py"


def soft_orb(size=(24, 20), colour=(40, 120, 220)):
    """A true-alpha picture: a disc whose coverage falls off smoothly, with fully transparent corners."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    cx, cy, radius = size[0] / 2, size[1] / 2, min(size) / 2
    for x in range(size[0]):
        for y in range(size[1]):
            distance = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
            coverage = max(0.0, min(1.0, (radius - distance) / 4))
            if coverage:
                image.putpixel((x, y), colour + (round(coverage * 255),))
    return image


class SplitTests(unittest.TestCase):
    def test_true_alpha_becomes_key_colour_art_and_a_matching_coverage(self):
        orb = soft_orb()
        key, matte = matte_rules.split(orb)
        self.assertEqual(matte.mode, "L")
        self.assertEqual(matte.tobytes(), orb.getchannel("A").tobytes())  # the softness is kept as drawn
        self.assertEqual(key.getpixel((0, 0))[:3], KEY)  # no coverage: the exact key colour
        self.assertEqual(key.getchannel("A").getextrema(), (255, 255))
        self.assertGreater(sum(1 for count in matte.histogram() if count), 3)
        self.assertEqual(matte_rules.problems(key, matte), [])

    def test_a_visible_pixel_that_is_exactly_the_key_colour_is_nudged_off_it(self):
        picture = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        picture.putpixel((1, 1), KEY + (200,))
        key, matte = matte_rules.split(picture)
        self.assertNotEqual(key.getpixel((1, 1))[:3], KEY)
        self.assertEqual(matte_rules.problems(key, matte), [])


class PairTests(unittest.TestCase):
    def test_each_kind_of_disagreement_is_named(self):
        key, matte = matte_rules.split(soft_orb())
        self.assertTrue(any("mode L" in p for p in matte_rules.problems(key, matte.convert("RGB"))))
        self.assertTrue(any("same size" in p for p in matte_rules.problems(key, matte.crop((0, 0, 10, 10)))))
        vanished = matte.copy()
        vanished.putpixel((12, 10), 0)  # art with no coverage
        self.assertTrue(any("art pixels have no coverage" in p for p in matte_rules.problems(key, vanished)))
        stray = matte.copy()
        stray.putpixel((0, 0), 90)  # coverage over the key colour
        self.assertTrue(any("key-colour pixels have coverage" in p for p in matte_rules.problems(key, stray)))


class BuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        soft_orb((24, 20)).save(self.src / "a.png")
        soft_orb((18, 22), (220, 90, 60)).save(self.src / "b.png")
        self.out = self.root / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, **overrides):
        job = {"_input_dir": str(self.src), "name": "glow", "asset_id": "glow", "soft_alpha": True, "padding": 2,
               "frames": [{"file": "a.png", "name": "a", "direction": "S"}, {"file": "b.png", "name": "b", "direction": "S"}]}
        job.update(overrides)
        return builder.build(job, self.out)


class BuildTests(BuildCase):
    def test_every_layout_delivers_the_key_sheet_and_a_matte_that_agree_and_are_recorded(self):
        for label, options in (("grid", {}), ("shelf", {"pack": "shelf"}), ("trim", {"pack": "shelf", "trim": True})):
            with self.subTest(label):
                png, atlas_path = self.build(name=f"glow_{label}", **options)
                atlas = common.read_json(atlas_path)
                matte_path = png.parent / matte_rules.matte_name(png.name)
                self.assertEqual(atlas["matte"], {"file": matte_path.name, "sha256": common.sha256_file(matte_path)})
                self.assertEqual(sheet_validator.validate(png, atlas_path), [])
                with Image.open(png) as sheet, Image.open(matte_path) as matte:
                    self.assertEqual(matte.size, sheet.size)
                    self.assertEqual(matte_rules.problems(sheet.convert("RGBA"), matte), [])
                    self.assertGreater(sum(matte.histogram()[1:255]), 0)  # soft coverage survived the packing

    def test_a_job_without_the_option_has_no_matte(self):
        opaque = self.root / "src2"
        opaque.mkdir()
        kit.key_image((10, 8), {(3, 3): (20, 50, 90, 255)}).save(opaque / "o.png")
        png, atlas_path = builder.build({"_input_dir": str(opaque), "name": "plain", "asset_id": "plain", "frames": [{"file": "o.png"}]}, self.out)
        self.assertNotIn("matte", common.read_json(atlas_path))
        self.assertFalse((png.parent / "plain.matte.png").exists())

    def test_a_missing_or_changed_matte_is_named_by_the_sheet_check(self):
        png, atlas_path = self.build()
        matte_path = png.parent / matte_rules.matte_name(png.name)
        with Image.open(matte_path) as opened:
            tampered = opened.point(lambda v: v // 2)  # every covered pixel changes
        tampered.save(matte_path)
        self.assertTrue(any("hash differs" in p for p in sheet_validator.validate(png, atlas_path)))
        matte_path.unlink()
        self.assertTrue(any("is missing" in p for p in sheet_validator.validate(png, atlas_path)))


class RuntimeExportTests(BuildCase):
    def test_the_runtime_copy_takes_its_alpha_from_the_matte_and_verifies(self):
        png, atlas_path = self.build()
        target = self.root / "runtime"
        manifest = runtime_export.export_sheet(png, atlas_path, target)
        self.assertEqual(sorted(entry["role"] for entry in manifest["files"]), ["atlas", "sheet"])
        with Image.open(target / png.name) as runtime, Image.open(png.parent / matte_rules.matte_name(png.name)) as matte:
            self.assertEqual(runtime.mode, "RGBA")
            self.assertEqual(runtime.getchannel("A").tobytes(), matte.tobytes())
        exported_atlas = common.read_json(target / atlas_path.name)
        self.assertNotIn("matte", exported_atlas)
        self.assertEqual(exported_atlas["runtime"]["source_matte_sha256"], common.read_json(atlas_path)["matte"]["sha256"])
        self.assertEqual(runtime_export.verify_export(target, png.parent), [])

    def test_a_doctored_alpha_is_found(self):
        png, atlas_path = self.build()
        target = self.root / "runtime"
        runtime_export.export_sheet(png, atlas_path, target)
        manifest = common.read_json(target / runtime_export.MANIFEST)
        sheet_entry = next(e for e in manifest["files"] if e["role"] == "sheet")
        with Image.open(target / png.name) as opened:
            doctored = opened.copy()
        doctored.putalpha(doctored.getchannel("A").point(lambda v: 255 if v else 0))
        doctored.save(target / png.name)
        sheet_entry["sha256"] = common.sha256_file(target / png.name)
        common.atomic_write_json(target / runtime_export.MANIFEST, manifest)
        self.assertTrue(any("alpha is not the coverage of the matte" in p for p in runtime_export.verify_export(target, png.parent)))

    def test_a_matte_changed_after_the_export_is_found(self):
        png, atlas_path = self.build()
        target = self.root / "runtime"
        runtime_export.export_sheet(png, atlas_path, target)
        matte_path = png.parent / matte_rules.matte_name(png.name)
        with Image.open(matte_path) as opened:
            changed = opened.point(lambda v: v // 2)
        changed.save(matte_path)
        self.assertTrue(any("matte" in p or "stale" in p for p in runtime_export.verify_export(target, png.parent)))


class LookTests(BuildCase):
    def gate(self, preset, identity):
        png, atlas_path = self.build(name=f"glow_{preset}")
        settings = default_settings()
        settings["art_style"] = dict(settings["art_style"], id=identity, preset=preset)
        return life.technical_check_bundle(png.parent, settings, root=self.root)

    def test_a_hard_edged_look_never_gets_a_matte_and_a_soft_one_may(self):
        refused = self.gate("pixel_mid", "pixel_art")
        self.assertTrue(any("never gets one" in issue for issue in refused["issues"]), refused["issues"])
        allowed = self.gate("painterly", "hand_painted")
        self.assertFalse(any("never gets one" in issue for issue in allowed["issues"]), allowed["issues"])


class CommandTests(unittest.TestCase):
    def run_script(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True)

    def test_split_writes_the_pair_and_check_agrees(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            soft_orb().save(folder / "orb.png")
            split = ["split", "--image", str(folder / "orb.png"), "--output-dir", str(folder / "out"), "--name", "orb"]
            done = self.run_script(*split)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(done.stdout)["problems"], [])
            checked = self.run_script("check", "--sheet", str(folder / "out" / "orb.png"), "--matte", str(folder / "out" / "orb.matte.png"))
            self.assertEqual(json.loads(checked.stdout)["status"], "passed")
            self.assertEqual(self.run_script(*split).returncode, 1)  # never overwrites


if __name__ == "__main__":
    unittest.main()
