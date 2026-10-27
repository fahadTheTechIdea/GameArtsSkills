"""Style-conformance checks (plan P11.4): palette, colour count, pixel grid and integer scale, measured on synthetic pixel art."""
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageFilter

import gamearts_testkit as kit
from gamearts_testkit import settings, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_palette as palette  # noqa: E402
import gamearts_presets as presets  # noqa: E402
import validate_style_conformance as conformance  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_style_conformance.py"
INKS = [(20, 24, 46), (92, 64, 51), (201, 138, 74), (233, 213, 168), (74, 124, 89)]
KEY = (255, 0, 255, 255)


def pixel_art(size=(24, 24), margin=2, seed=7, inks=INKS):
    """Native-size pixel art: a random-looking but fixed pattern of `inks` inside a key-colour margin."""
    rng = random.Random(seed)
    image = Image.new("RGBA", size, KEY)
    for y in range(margin, size[1] - margin):
        for x in range(margin, size[0] - margin):
            image.putpixel((x, y), rng.choice(inks) + (255,))
    return image


def smooth_frame(size=(40, 40), margin=3):
    """Art with hundreds of colours that never come near the key colour: a gradient block, as a painted look would produce."""
    image = Image.new("RGBA", size, KEY)
    for y in range(margin, size[1] - margin):
        for x in range(margin, size[0] - margin):
            image.putpixel((x, y), (x * 5, y * 5, (x + y) * 3 % 200, 255))
    return image


def by_name(results):
    return {item["name"]: item for item in results}


def run(image, names, params=None, colours=None):
    return by_name(conformance.run_checks(image, names, params or {}, colours))


class ColourCountTests(unittest.TestCase):
    def test_native_pixel_art_is_within_its_limit_and_over_a_smaller_one(self):
        art = pixel_art()
        ok = run(art, ["colour_count_max"], {"colour_count_max": {"max_colours": 8}})["colour_count_max"]
        self.assertEqual((ok["status"], ok["measured"]["colours"]), ("passed", 5))
        over = run(art, ["colour_count_max"], {"colour_count_max": {"max_colours": 4}})["colour_count_max"]
        self.assertEqual(over["status"], "failed")

    def test_a_blurred_copy_has_far_more_colours(self):
        blurred = pixel_art().filter(ImageFilter.GaussianBlur(1.2))
        result = run(blurred, ["colour_count_max"], {"colour_count_max": {"max_colours": 8}})["colour_count_max"]
        self.assertEqual(result["status"], "failed")
        self.assertGreater(result["measured"]["colours"], 30)

    def test_the_key_colour_is_never_counted(self):
        flat = Image.new("RGBA", (10, 10), KEY)
        flat.putpixel((3, 3), (1, 2, 3, 255))
        self.assertEqual(run(flat, ["colour_count_max"], {"colour_count_max": {"max_colours": 1}})["colour_count_max"]["status"], "passed")

    def test_no_limit_set_means_untested_not_passed(self):
        self.assertEqual(run(pixel_art(), ["colour_count_max"])["colour_count_max"]["status"], "untested")


class PaletteTests(unittest.TestCase):
    def test_exact_means_every_art_pixel_uses_a_palette_colour(self):
        art = pixel_art()
        self.assertEqual(run(art, ["palette_exact"], colours=INKS)["palette_exact"]["status"], "passed")
        short = run(art, ["palette_exact"], colours=INKS[:4])["palette_exact"]
        self.assertEqual(short["status"], "failed")
        self.assertGreater(short["measured"]["off_palette_pixels"], 0)
        self.assertIn("#4A7C59", short["measured"]["examples"])

    def test_without_a_palette_the_palette_checks_are_untested_with_the_way_to_fix_it(self):
        results = run(pixel_art(), ["palette_exact", "palette_near"])
        for name in ("palette_exact", "palette_near"):
            self.assertEqual(results[name]["status"], "untested")
            self.assertIn("palette", results[name]["detail"])

    def test_near_tolerates_small_drift_and_rejects_large_drift(self):
        rng = random.Random(3)
        close, far = pixel_art(), pixel_art()
        for y in range(24):
            for x in range(24):
                if close.getpixel((x, y)) != KEY:
                    r, g, b, _ = close.getpixel((x, y))
                    close.putpixel((x, y), (min(255, r + rng.choice((0, 1, 2))), g, b, 255))
                    r, g, b, _ = far.getpixel((x, y))
                    far.putpixel((x, y), ((r + 70) % 256, (g + 70) % 256, b, 255))
        params = {"palette_near": {"max_lab_distance": 6}}
        self.assertEqual(run(close, ["palette_near"], params, INKS)["palette_near"]["status"], "passed")
        drifted = run(far, ["palette_near"], params, INKS)["palette_near"]
        self.assertEqual(drifted["status"], "failed")
        self.assertGreater(drifted["measured"]["off_share"], 0.5)

    def test_a_picture_with_too_many_colours_to_measure_is_untested_not_slow(self):
        rng = random.Random(1)
        wide = Image.new("RGBA", (200, 200), KEY)
        for y in range(200):
            for x in range(200):
                wide.putpixel((x, y), (rng.randrange(256), rng.randrange(256), rng.randrange(256), 255))
        result = run(wide, ["palette_near"], colours=INKS)["palette_near"]
        self.assertEqual(result["status"], "untested")
        self.assertIn("distinct colours", result["detail"])


class PixelGridTests(unittest.TestCase):
    def test_native_pixel_art_has_no_block_structure(self):
        result = run(pixel_art((64, 64), 4), ["pixel_grid"])["pixel_grid"]
        self.assertEqual((result["status"], result["measured"]["block_x"], result["measured"]["block_y"]), ("passed", 1, 1))

    def test_an_integer_upscale_is_found_with_its_block_size(self):
        art = pixel_art((64, 64), 4).resize((256, 256), Image.NEAREST)
        result = run(art, ["pixel_grid"])["pixel_grid"]
        self.assertEqual(result["status"], "failed")
        self.assertEqual((result["measured"]["block_x"], result["measured"]["block_y"]), (4, 4))
        self.assertIn("snap", result["detail"])

    def test_a_few_stray_pixels_do_not_hide_the_grid(self):
        art = pixel_art((64, 64), 4).resize((256, 256), Image.NEAREST)
        for point in ((101, 77), (13, 200), (180, 33)):
            art.putpixel(point, (250, 250, 250, 255))
        self.assertEqual(run(art, ["pixel_grid"])["pixel_grid"]["measured"]["block_x"], 4)

    def test_a_flat_picture_has_too_few_edges_to_tell(self):
        flat = Image.new("RGBA", (64, 64), KEY)
        flat.paste((9, 9, 9, 255), (10, 10, 30, 30))
        self.assertEqual(run(flat, ["pixel_grid"])["pixel_grid"]["status"], "untested")

    def test_a_soft_picture_has_no_grid_and_that_is_not_a_failure_of_this_check(self):
        soft = pixel_art((64, 64), 4).resize((256, 256), Image.BICUBIC)
        self.assertEqual(run(soft, ["pixel_grid"])["pixel_grid"]["measured"]["block_x"], 1)


class IntegerScaleTests(unittest.TestCase):
    def test_a_non_integer_upscale_is_found(self):
        art = pixel_art((64, 64), 4).resize((224, 224), Image.NEAREST)  # 3.5 times
        result = run(art, ["integer_scale"])["integer_scale"]
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["measured"]["pair"], [3, 4])

    def test_native_art_and_an_integer_upscale_both_pass_this_check(self):
        native = pixel_art((64, 64), 4)
        self.assertNotEqual(run(native, ["integer_scale"])["integer_scale"]["status"], "failed")
        self.assertNotEqual(run(native.resize((256, 256), Image.NEAREST), ["integer_scale"])["integer_scale"]["status"], "failed")

    def test_a_picture_with_too_few_long_runs_is_untested(self):
        self.assertEqual(run(pixel_art((16, 16), 2), ["integer_scale"])["integer_scale"]["status"], "untested")


class AggregationTests(unittest.TestCase):
    def test_overall_status_is_failed_untested_or_passed_in_that_order(self):
        passed, failed, untested = {"status": "passed"}, {"status": "failed"}, {"status": "untested"}
        self.assertEqual(conformance.overall([passed, failed, untested]), "failed")
        self.assertEqual(conformance.overall([passed, untested]), "untested")
        self.assertEqual(conformance.overall([passed, passed]), "passed")
        self.assertEqual(conformance.overall([]), "not_applicable")

    def test_an_unknown_check_name_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unknown style check"):
            conformance.run_checks(pixel_art(), ["sparkle"], {}, None)

    def test_an_animation_check_is_not_run_on_a_still_picture_and_says_where_it_belongs(self):
        for name in ("loop_seam", "pivot_drift", "clipping"):
            with self.subTest(name), self.assertRaisesRegex(ValueError, "animation check.*check_animation.py"):
                conformance.run_checks(pixel_art(), [name], {}, None)

    def test_the_presets_name_exactly_the_checks_the_framework_can_run(self):
        schema = json.loads((ROOT / "schemas" / "gamearts-style-preset.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"]["required_checks"]["items"]["enum"]), set(conformance.CHECKS))
        self.assertEqual(set(schema["properties"]["check_parameters"]["propertyNames"]["enum"]), set(conformance.CHECKS))
        used = {name for p in presets.style_presets().values() for name in p["required_checks"]}
        self.assertLessEqual(used, set(conformance.CHECKS))

    def test_every_still_image_check_has_a_function(self):
        for name in conformance.STILL_CHECKS:
            self.assertIn(name, conformance.CHECK_FUNCTIONS)


class SettingsDrivenTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_checks_and_numbers_come_from_the_games_preset(self):
        names, params = conformance.checks_for(settings(art_style={"id": "pixel_art", "preset": "pixel_mid"}))
        self.assertEqual(set(names), {"palette_exact", "colour_count_max", "pixel_grid", "integer_scale"})
        self.assertEqual(params["colour_count_max"]["max_colours"], 64)

    def test_a_game_without_a_preset_has_nothing_to_check(self):
        self.assertEqual(conformance.checks_for(settings()), ([], {}))
        self.assertEqual(conformance.checks_for(settings(art_style={"id": "pixel_art", "preset": "not-installed"})), ([], {}))

    def test_the_games_palette_file_is_used_for_the_palette_checks(self):
        art = pixel_art()
        image = self.root / "board.png"
        art.save(image)
        palette.extract(image, name="main", output_dir=self.root / ".gamearts" / "palette", max_colours=8, root=self.root)
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_mid", "palette_reference": ".gamearts/palette/main.palette.json"})
        report = conformance.check_file(self.root, image)
        self.assertEqual(by_name(report["checks"])["palette_exact"]["status"], "passed")
        self.assertEqual(report["status"], "untested" if any(c["status"] == "untested" for c in report["checks"]) else "passed")

    def test_a_missing_palette_file_leaves_the_palette_checks_untested_and_says_why(self):
        image = self.root / "a.png"
        pixel_art().save(image)
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_mid", "palette_reference": ".gamearts/palette/gone.palette.json"})
        report = conformance.check_file(self.root, image)
        self.assertEqual(by_name(report["checks"])["palette_exact"]["status"], "untested")
        self.assertIn("does not exist", by_name(report["checks"])["palette_exact"]["detail"])

    def test_the_command_line_prints_json_and_fails_when_a_check_fails(self):
        image = self.root / "soft.png"
        pixel_art((64, 64), 4).resize((256, 256), Image.NEAREST).save(image)
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_low"})
        done = subprocess.run([sys.executable, str(SCRIPT), "--game-root", str(self.root), "--image", str(image)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(by_name(result["checks"])["pixel_grid"]["status"], "failed")
        self.assertTrue(result["not_assessed"])


class TechnicalGateTests(unittest.TestCase):
    """The checks a game's preset lists are part of the technical artwork gate that register-asset and approve run."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def bundle(self, frame, name="art_v001"):
        folder = self.root / ".gamearts/outputs/assets/generated" / name
        folder.mkdir(parents=True)
        with tempfile.TemporaryDirectory() as frames:
            frame.save(Path(frames) / "frame.png")
            kit.build_sheet({"_input_dir": frames, "name": f"{name}_sheet", "asset_id": name, "columns": 1, "padding": 2,
                             "frames": [{"file": "frame.png", "name": "S0", "direction": "S", "pivot": [4, 20]}]}, folder)
        return folder

    def register(self, name="art_v001"):
        image, metadata = kit.make_mockup(self.root, "scene-a", "v001", "world")
        life.register_mockup(self.root, metadata, image)
        life.approve_mockup(self.root, "scene-a", "v001", "approved")
        return life.register_asset(self.root, name, "v001", f".gamearts/outputs/assets/generated/{name}", [("scene-a", "v001")])

    def test_clean_pixel_art_passes_the_gate_and_the_result_records_the_conformance(self):
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_mid"})
        self.bundle(pixel_art((40, 40), 3))
        result = self.register()
        self.assertEqual(result["technical_validation"], "passed")
        record = life.records(self.root, "assets")[0]
        self.assertIn(record["technical_validation"]["style_conformance"]["status"], ("passed", "untested"))
        self.assertEqual(record["technical_validation"]["style_conformance"]["preset"], "pixel_mid")

    def test_art_that_breaks_the_games_preset_fails_the_gate_and_cannot_be_approved(self):
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_mid"})
        self.bundle(smooth_frame())
        result = self.register()
        self.assertEqual(result["technical_validation"], "failed")
        self.assertTrue(any("colour_count_max" in issue for issue in result["technical_issues"]), result["technical_issues"])
        with self.assertRaisesRegex(ValueError, "Technical artwork gate failed"):
            life.approve_asset(self.root, "art_v001", "looks fine to me")

    def test_a_game_without_a_preset_is_not_held_to_style_checks(self):
        write_settings(self.root)
        self.bundle(smooth_frame())
        result = self.register()
        self.assertEqual(result["technical_validation"], "passed")
        record = life.records(self.root, "assets")[0]
        self.assertEqual(record["technical_validation"]["style_conformance"]["status"], "not_applicable")

    def test_unreadable_settings_make_the_style_checks_untested_and_say_so(self):
        write_settings(self.root)
        folder = self.bundle(pixel_art((40, 40), 3))
        technical = life.technical_check_bundle(folder, settings=None, settings_problem="project.json is damaged")
        self.assertEqual(technical["style_conformance"]["status"], "untested")
        self.assertIn("damaged", technical["style_conformance"]["reason"])
        self.assertEqual(technical["status"], "passed")


if __name__ == "__main__":
    unittest.main()
