"""The pixel-grid snapper (plan P11.5): recover the native picture from one that was drawn large, or refuse and say why."""
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit as kit
from gamearts_testkit import write_settings

import gamearts_common as common  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_palette as palette  # noqa: E402
import gamearts_pixelgrid as grid  # noqa: E402
import snap_to_pixel_grid as snapper  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "snap_to_pixel_grid.py"
INKS = [(20, 24, 46), (92, 64, 51), (201, 138, 74), (233, 213, 168), (74, 124, 89)]
KEY = (255, 0, 255)


def native(size=(24, 24), margin=2, seed=7):
    rng = random.Random(seed)
    image = Image.new("RGB", size, KEY)
    for y in range(margin, size[1] - margin):
        for x in range(margin, size[0] - margin):
            image.putpixel((x, y), rng.choice(INKS))
    return image


def jitter(image, amount=3, seed=1):
    rng = random.Random(seed)
    out = image.copy()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b = out.getpixel((x, y))
            out.putpixel((x, y), tuple(max(0, min(255, c + rng.randint(-amount, amount))) for c in (r, g, b)))
    return out


def same_share(a, b):
    assert a.size == b.size, (a.size, b.size)
    equal = sum(1 for y in range(a.height) for x in range(a.width) if a.getpixel((x, y)) == b.getpixel((x, y)))
    return equal / (a.width * a.height)


class RecoveryTests(unittest.TestCase):
    def test_an_integer_enlargement_gives_back_the_exact_native_picture(self):
        art = native()
        out, report = snapper.snap(art.resize((192, 192), Image.NEAREST))
        self.assertEqual(out.size, (24, 24))
        self.assertEqual(same_share(out, art), 1.0)
        self.assertAlmostEqual(report["cell_px"][0], 8.0, places=1)
        self.assertEqual(report["output_size"], [24, 24])

    def test_a_non_integer_enlargement_is_recovered_too(self):
        art = native()
        out, report = snapper.snap(art.resize((175, 175), Image.NEAREST))  # about 7.29 times
        self.assertEqual(out.size, (24, 24))
        self.assertGreaterEqual(same_share(out, art), 0.98)
        self.assertAlmostEqual(report["cell_px"][0], 175 / 24, delta=0.2)

    def test_a_long_non_integer_enlargement_does_not_drift_off_its_grid(self):
        art = native((64, 64), 4, seed=11)
        out, report = snapper.snap(art.resize((467, 467), Image.NEAREST))  # about 7.3 times, 64 cells
        self.assertEqual(out.size, (64, 64))
        self.assertGreaterEqual(same_share(out, art), 0.98)
        self.assertGreater(report["grid_score"][0], 0.9)

    def test_a_rectangular_picture_keeps_its_proportions(self):
        art = native((40, 20), 2)
        out, _ = snapper.snap(art.resize((320, 160), Image.NEAREST))
        self.assertEqual(out.size, (40, 20))
        self.assertEqual(same_share(out, art), 1.0)

    def test_noise_inside_the_cells_is_averaged_away(self):
        art = native()
        noisy = jitter(art.resize((192, 192), Image.NEAREST), 3)
        out, report = snapper.snap(noisy)
        self.assertEqual(out.size, (24, 24))
        for y in range(24):
            for x in range(24):
                self.assertTrue(all(abs(a - b) <= 3 for a, b in zip(out.getpixel((x, y)), art.getpixel((x, y)))), (x, y))  # the noise is at most 3
        self.assertGreater(report["uniform_cells_share"], 0.9)

    def test_a_stray_line_through_a_cell_does_not_change_its_colour(self):
        art = native()
        big = art.resize((192, 192), Image.NEAREST)
        for y in range(5 * 8, 6 * 8):  # a one-pixel white line down the middle of cell (5, 5): about a quarter of its middle half
            big.putpixel((5 * 8 + 4, y), (255, 255, 255))
        out, report = snapper.snap(big)
        self.assertEqual(out.getpixel((5, 5)), art.getpixel((5, 5)))
        self.assertEqual(same_share(out, art), 1.0)
        self.assertLess(report["uniform_cells_share"], 1.0)

    def test_with_the_games_palette_the_result_is_exact_even_from_noisy_input(self):
        art = native()
        out, report = snapper.snap(jitter(art.resize((192, 192), Image.NEAREST), 4), INKS + [KEY])
        self.assertEqual(same_share(out, art), 1.0)
        self.assertIn("palette", report["palette"])

    def test_the_key_colour_background_survives_exactly(self):
        art = native()
        out, _ = snapper.snap(art.resize((192, 192), Image.NEAREST))
        self.assertEqual(out.getpixel((0, 0)), KEY)
        self.assertEqual(out.getpixel((23, 23)), KEY)

    def test_a_noisy_key_background_becomes_exact_key_again_with_or_without_a_palette(self):
        noisy = jitter(native().resize((192, 192), Image.NEAREST), 4)
        for colours in (None, INKS):
            out, _ = snapper.snap(noisy, colours)
            self.assertEqual(out.getpixel((0, 0)), KEY)
            self.assertEqual(out.getpixel((23, 0)), KEY)
            self.assertEqual(out.getpixel((0, 23)), KEY)

    def test_the_snapped_picture_passes_the_pixel_grid_check_the_enlarged_one_failed(self):
        import validate_style_conformance as conformance
        big = native((64, 64), 4).resize((256, 256), Image.NEAREST)
        out, _ = snapper.snap(big)
        before = conformance.run_checks(big, ["pixel_grid"], {}, None)[0]
        after = conformance.run_checks(out, ["pixel_grid"], {}, None)[0]
        self.assertEqual((before["status"], after["status"]), ("failed", "passed"))


class RefusalTests(unittest.TestCase):
    def test_a_picture_with_no_grid_is_refused_with_the_measured_reason(self):
        rng = random.Random(5)
        noise = Image.new("RGB", (96, 96))
        for y in range(96):
            for x in range(96):
                noise.putpixel((x, y), (rng.randrange(256), rng.randrange(256), rng.randrange(256)))
        with self.assertRaisesRegex(ValueError, "no consistent pixel grid"):
            snapper.snap(noise)

    def test_a_picture_already_at_its_native_size_is_refused_not_shrunk_further(self):
        with self.assertRaisesRegex(ValueError, "no consistent pixel grid"):
            snapper.snap(native((48, 48), 3))

    def test_a_picture_with_transparency_is_refused(self):
        art = native().convert("RGBA")
        art.putpixel((3, 3), (1, 2, 3, 0))
        with self.assertRaisesRegex(ValueError, "transparency"):
            snapper.snap(art.resize((192, 192), Image.NEAREST))

    def test_a_picture_whose_two_halves_have_different_grids_is_refused(self):
        left = native((12, 24), 2, seed=3).resize((96, 192), Image.NEAREST)
        right = native((12, 24), 2, seed=4).resize((84, 168), Image.NEAREST)
        both = Image.new("RGB", (180, 192), KEY)
        both.paste(left, (0, 0))
        both.paste(right, (96, 0))
        with self.assertRaisesRegex(ValueError, "no consistent pixel grid.*explains only"):
            snapper.snap(both)

    def test_a_flat_picture_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no consistent pixel grid"):
            snapper.snap(Image.new("RGB", (64, 64), (10, 20, 30)))


class GridDetectionTests(unittest.TestCase):
    def test_the_period_and_phase_of_a_regular_grid_are_found(self):
        profile = [0] * 99
        for position in range(5, 100, 10):
            profile[position - 1] = 255
        period, phase, score = grid.detect_period(profile)
        self.assertAlmostEqual(period, 10.0, delta=0.1)
        self.assertAlmostEqual(phase, 5.0, delta=0.3)
        self.assertGreater(score, 0.95)

    def test_a_fraction_of_the_true_period_does_not_win(self):
        profile = [0] * 159
        for position in range(0, 160, 16):
            if 0 < position < 160:
                profile[position - 1] = 255
        period, _, _ = grid.detect_period(profile)
        self.assertGreater(period, 14)

    def test_edges_that_skip_every_other_grid_line_do_not_double_the_period(self):
        profile = [0] * 219
        for position in range(20, 220, 20):  # strong edges on every second line of a 10-pixel grid
            profile[position - 1] = 255
        for position in (10, 30, 50):  # a few on the lines in between
            profile[position - 1] = 255
        period, _, score = grid.detect_period(profile)
        self.assertAlmostEqual(period, 10.0, delta=0.2)
        self.assertGreater(score, 0.9)

    def test_missing_edges_do_not_bias_the_period(self):
        period = 7.3  # a non-whole enlargement; neighbouring cells of one colour leave no edge between them
        ideal = [round(5 + n * period) for n in range(120)]
        kept = [e for i, e in enumerate(ideal) if not (i + 1 < len(ideal) and ideal[i + 1] - e == 7 and i % 2 == 0)]
        self.assertLess(len(kept), 0.7 * len(ideal))
        profile = [0] * (ideal[-1] + 5)
        for position in kept:
            profile[position - 1] = 255
        found, _, score = grid.detect_period(profile)
        self.assertAlmostEqual(found, period, delta=0.05)
        self.assertGreater(score, 0.9)

    def test_edges_displaced_by_a_few_pixels_are_not_a_grid(self):
        rng = random.Random(4)
        profile = [0] * 400
        for n in range(1, 25):
            profile[n * 16 + rng.randint(-4, 4) - 1] = 255
        found = grid.detect_period(profile)
        self.assertTrue(found is None or found[2] < 0.6, found)

    def test_random_edges_have_no_period(self):
        rng = random.Random(9)
        profile = [255 if rng.random() < 0.5 else 0 for _ in range(300)]
        found = grid.detect_period(profile)
        self.assertTrue(found is None or found[2] < 0.9, found)

    def test_block_sizes_come_from_the_edge_positions(self):
        self.assertEqual(grid.block_size(list(range(4, 100, 4)), 0.98, 16), 4)
        self.assertEqual(grid.block_size(list(range(1, 60)), 0.98, 16), 1)
        self.assertIsNone(grid.block_size([4, 8], 0.98, 16))


class FileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def source(self):
        path = self.root / "large.png"
        native().resize((192, 192), Image.NEAREST).save(path)
        return path

    def test_the_original_is_never_changed_and_the_copy_is_labelled_in_its_report(self):
        source = self.source()
        before = common.sha256_file(source)
        report = snapper.snap_file(source, self.root / "native.snapped.png", report_path=self.root / "native.snapped.json")
        self.assertEqual(common.sha256_file(source), before)
        saved = json.loads((self.root / "native.snapped.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["source"], {"file": "large.png", "sha256": before})
        self.assertEqual(saved["kind"], "working copy; the original is untouched")
        self.assertEqual(report["output_size"], [24, 24])
        with Image.open(self.root / "native.snapped.png") as shown:
            self.assertEqual(shown.size, (24, 24))

    def test_an_existing_output_is_never_overwritten(self):
        source = self.source()
        (self.root / "out.png").write_bytes(b"mine")
        with self.assertRaisesRegex(ValueError, "already exists"):
            snapper.snap_file(source, self.root / "out.png")
        self.assertEqual((self.root / "out.png").read_bytes(), b"mine")

    def test_the_output_may_not_replace_the_input(self):
        source = self.source()
        with self.assertRaisesRegex(ValueError, "already exists"):
            snapper.snap_file(source, source)

    def test_a_refused_picture_leaves_no_output_behind(self):
        flat = self.root / "flat.png"
        Image.new("RGB", (64, 64), (1, 2, 3)).save(flat)
        with self.assertRaises(ValueError):
            snapper.snap_file(flat, self.root / "never.png")
        self.assertFalse((self.root / "never.png").exists())

    def test_the_games_palette_is_used_when_the_command_is_given_the_game(self):
        write_settings(self.root, art_style={"id": "pixel_art", "palette_reference": ".gamearts/palette/main.palette.json"})
        board = self.root / "board.png"
        native().save(board)
        palette.extract(board, name="main", output_dir=self.root / ".gamearts" / "palette", max_colours=8, root=self.root)
        noisy = self.root / "noisy.png"
        jitter(native().resize((192, 192), Image.NEAREST), 4).save(noisy)
        done = subprocess.run([sys.executable, str(SCRIPT), "--image", str(noisy), "--output", str(self.root / "clean.png"), "--game-root", str(self.root)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        with Image.open(self.root / "clean.png") as shown:
            self.assertEqual(same_share(shown.convert("RGB"), native()), 1.0)
        self.assertIn("palette", json.loads(done.stdout)["palette"])

    def test_a_blocked_command_says_why_and_exits_one(self):
        flat = self.root / "flat.png"
        Image.new("RGB", (64, 64), (1, 2, 3)).save(flat)
        done = subprocess.run([sys.executable, str(SCRIPT), "--image", str(flat), "--output", str(self.root / "x.png")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)
        self.assertIn("no consistent pixel grid", done.stderr)


if __name__ == "__main__":
    unittest.main()
