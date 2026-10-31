"""The pixel-grid snapper (plan P11.5): recover the native picture from one that was drawn large, or refuse and say why."""
import functools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageFilter

import gamearts_testkit as kit
from gamearts_testkit import write_settings

import gamearts_common as common  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_matte as matte  # noqa: E402
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


# ------------------------------------------------------------------------------------------------ clean: a soft picture on a soft background
SPRITE = [(30, 30, 40), (200, 160, 40), (40, 120, 60), (150, 150, 160)]  # outline, left body, right body, stripe
SPRITE_PALETTE = SPRITE + [(250, 250, 250), (110, 20, 110), (20, 60, 200)]  # the sprite's colours and three it does not use (one of them purple)
SOFT_SCALE = 7.3  # not a whole number, as the image tool's enlargements are


def sprite_native(hole=2):
    """A 60 x 36 native picture: a 50 x 26 sprite on the exact key, with an enclosed key-coloured gap of hole x hole pixels."""
    art = Image.new("RGB", (60, 36), KEY)
    for y in range(5, 31):
        for x in range(5, 55):
            edge = x in (5, 54) or y in (5, 30)
            art.putpixel((x, y), SPRITE[0] if edge else SPRITE[1] if x < 30 else SPRITE[2])
    for x in range(6, 54):
        art.putpixel((x, 18), SPRITE[3])
    for y in range(10, 10 + hole):
        for x in range(12, 12 + hole):
            art.putpixel((x, y), KEY)
    return art


@functools.lru_cache(maxsize=None)
def soft_picture(hole=2, blur=1.2, noise=3, specks=True):
    """What an image tool returns: the art enlarged by 7.3, blurred, noisy, on a background that is a soft magenta and never the exact key.
    Cached (the noise is slow to make): treat the picture as read-only."""
    art = sprite_native(hole)
    big = art.resize((round(art.width * SOFT_SCALE), round(art.height * SOFT_SCALE)), Image.NEAREST).filter(ImageFilter.GaussianBlur(blur))
    big = jitter(big, noise, seed=5)
    if specks:
        for point in ((8, 250), (400, 8), (420, 250)):
            big.putpixel(point, (200, 60, 200))
    return big


class CleanCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def clean(self, picture, **options):
        options.setdefault("target_long_side", 50)
        return snapper.clean(picture, SPRITE_PALETTE, **options)


class CleanRecoveryTests(CleanCase):
    def test_a_soft_picture_comes_back_at_the_asked_size_on_the_exact_key_with_palette_colours_only(self):
        art = sprite_native()
        picture = soft_picture()
        self.assertGreater(len(picture.getcolors(picture.width * picture.height)), 5000)  # a painting, nothing like a palette
        out, report = self.clean(picture)
        self.assertEqual(out.size, (50, 26))
        self.assertEqual(report["native_art_size"], [50, 26])
        art_colours = palette.art_colour_counts(out)
        self.assertTrue(set(art_colours) <= set(SPRITE_PALETTE), set(art_colours) - set(SPRITE_PALETTE))
        self.assertEqual(report["colours_after"], len(art_colours))
        self.assertGreater(report["colours_before"], 5000)
        rgba = out.convert("RGBA")
        self.assertEqual(common.key_policy_report(rgba)["issues"], [])
        self.assertEqual(common.mask_count(common.near_key_mask(rgba)), 0)
        crop = art.crop((5, 5, 55, 31))
        self.assertGreaterEqual(same_share(out, crop), 0.92)

    def test_no_pixel_next_to_the_background_keeps_the_keys_tint(self):
        """The outline is dark; where it was blended with the magenta the cell would come out purple. The palette has a purple to fall into."""
        out, report = self.clean(soft_picture())
        self.assertGreaterEqual(report["background"]["fringe_px"], 1)
        self.assertNotIn((110, 20, 110), palette.art_colour_counts(out))

    def test_a_key_coloured_gap_enclosed_by_art_is_background_too_and_counted(self):
        """Art is never within the key's distance, so a gap that size is background the art surrounds; left in, it would be averaged into the edges as pink."""
        out, report = self.clean(soft_picture(hole=2))
        self.assertEqual(report["background"]["gap_pieces"], 1)
        self.assertGreater(report["background"]["gap_pixels"], 100)
        self.assertEqual(out.getpixel((8, 6)), KEY)  # the one cell the 2 x 2 gap covers whole (the gap is at 12..13, 10..11 of the 60 x 36 original, the art starts at 5, 5)
        self.assertNotIn((110, 20, 110), palette.art_colour_counts(out))

    def test_a_cell_that_is_key_coloured_art_pixel_by_pixel_stays_key_though_no_single_gap_is_big_enough(self):
        """Key-coloured crumbs, each too small to be a gap, divided by thin lines of art: the cell's own colour is the key's, and art never is."""
        picture = soft_picture().copy()
        for y in range(90, 122):
            for x in range(110, 142):
                picture.putpixel((x, y), SPRITE[1] if x % 4 == 0 or y % 4 == 0 else KEY)
        out, report = self.clean(picture)
        self.assertGreaterEqual(report["cells"]["enclosed_background_keyed"], 1)
        self.assertEqual(report["background"]["gap_pieces"], 1)  # the crumbs are not gaps: only the sprite's own hole is
        self.assertEqual(common.mask_count(common.near_key_mask(out.convert("RGBA"))), 0)

    def test_specks_of_the_soft_background_do_not_stretch_the_art_box(self):
        art = sprite_native()
        out, report = self.clean(soft_picture(specks=True))
        self.assertEqual(report["background"]["speck_pieces"], 3)
        plain = self.clean(soft_picture(specks=False))[1]
        self.assertEqual(report["art_box"], plain["art_box"])
        self.assertLess(report["art_size_px"][0], round(art.width * SOFT_SCALE))

    def test_the_tolerance_is_read_from_the_pictures_own_border(self):
        """Only the background is made noisier, so the art cannot be what moves the figure."""
        quiet = soft_picture(noise=2, specks=False)
        far = common.key_distance(quiet).point(lambda v: 255 if v <= 10 else 0)
        noisy = Image.composite(jitter(quiet, 30, seed=9), quiet, far)
        measured = {name: matte.key_background(picture)[2]["tolerance"] for name, picture in (("quiet", quiet), ("noisy", noisy))}
        self.assertGreater(measured["noisy"], measured["quiet"])
        self.assertEqual(measured["quiet"], common.NEAR_KEY_TOLERANCE)  # never tighter than the near-key distance
        self.assertLessEqual(measured["noisy"], matte.MAX_KEY_TOLERANCE)

    def test_the_target_scale_and_the_target_long_side_agree(self):
        picture = soft_picture()
        by_side = self.clean(picture, target_long_side=50)[0]
        box = self.clean(picture, target_long_side=50)[1]["art_size_px"]
        by_scale = self.clean(picture, target_long_side=None, target_scale=box[0] / 50)[0]
        self.assertEqual(by_scale.size, by_side.size)
        self.assertEqual(same_share(by_scale, by_side), 1.0)

    def test_a_picture_with_a_grid_needs_no_size_and_the_grid_is_used(self):
        crisp = native(size=(40, 30), margin=6).resize((320, 240), Image.NEAREST)
        out, report = snapper.clean(crisp, None)
        self.assertEqual(report["scale"]["settled_by"], "the estimated grid")
        self.assertEqual(out.size, (28, 18))
        self.assertAlmostEqual(report["scale"]["source_px_per_native_px"][0], 8.0, places=1)

    def test_a_margin_of_key_is_kept_round_the_art(self):
        out, report = self.clean(soft_picture(), margin=2)
        self.assertEqual(out.size, (54, 30))
        self.assertEqual({out.getpixel((x, 0)) for x in range(out.width)}, {KEY})
        self.assertEqual(report["native_art_size"], [50, 26])

    def test_the_report_gives_the_numbers_the_owner_needs_to_judge_the_copy(self):
        out, report = self.clean(soft_picture())
        self.assertEqual(report["source_size"], [round(60 * SOFT_SCALE), round(36 * SOFT_SCALE)])
        self.assertEqual(report["scale"]["settled_by"], "the target long side, 50 native pixels")
        self.assertAlmostEqual(report["scale"]["source_px_per_native_px"][0], SOFT_SCALE, delta=0.2)
        self.assertGreater(report["colour_error"]["max_delta_e76"], 0)
        self.assertLess(report["colour_error"]["mean_delta_e76"], 8)
        self.assertIn("palette", report)

    def test_without_a_palette_the_colours_are_the_cells_own_and_still_clear_of_the_key(self):
        out, report = snapper.clean(soft_picture(), None, target_long_side=50)
        self.assertEqual(report["palette"], "none applied")
        self.assertEqual(common.mask_count(common.near_key_mask(out.convert("RGBA"))), 0)


class CleanRefusalTests(CleanCase):
    def test_a_picture_whose_border_is_not_key_coloured_is_refused_with_the_measure(self):
        picture = soft_picture(specks=False)
        white = Image.new("RGB", picture.size, (250, 250, 250))
        with self.assertRaisesRegex(ValueError, r"Only \d+% of the picture's border is within 64 of #FF00FF"):
            self.clean(white)
        with self.assertRaisesRegex(ValueError, "border"):
            self.clean(Image.blend(picture, white, 0.8))

    def test_a_picture_with_no_size_and_no_grid_is_refused_and_says_what_to_give(self):
        with self.assertRaisesRegex(ValueError, "give the native size yourself: --target-long-side"):
            snapper.clean(soft_picture(), SPRITE_PALETTE)

    def test_a_size_larger_than_the_art_would_enlarge_it_and_is_refused(self):
        with self.assertRaisesRegex(ValueError, "would have to be enlarged"):
            self.clean(soft_picture(), target_long_side=900)
        with self.assertRaisesRegex(ValueError, "must be at least 1"):
            self.clean(soft_picture(), target_long_side=None, target_scale=0.5)

    def test_a_wide_magenta_glow_round_the_art_is_refused_not_averaged_into_the_edges(self):
        art = sprite_native()
        big = art.resize((round(art.width * SOFT_SCALE), round(art.height * SOFT_SCALE)), Image.NEAREST).filter(ImageFilter.GaussianBlur(9))
        with self.assertRaisesRegex(ValueError, "still magenta-tinted"):
            self.clean(big)

    def test_a_picture_with_transparency_and_a_flat_picture_are_refused(self):
        with self.assertRaisesRegex(ValueError, "transparency"):
            self.clean(Image.new("RGBA", (64, 64), (255, 0, 255, 0)))
        with self.assertRaisesRegex(ValueError, "Nothing is left|No art lies"):
            self.clean(Image.new("RGB", (64, 64), (255, 0, 255)))

    def test_the_two_ways_to_give_a_size_exclude_each_other_and_a_palette_near_the_key_is_refused(self):
        picture = soft_picture()
        with self.assertRaisesRegex(ValueError, "not both"):
            self.clean(picture, target_scale=5.0)
        with self.assertRaisesRegex(ValueError, "too close to it"):
            snapper.clean(picture, [(250, 0, 250)], target_long_side=50)


class CleanFileTests(CleanCase):
    def setUp(self):
        super().setUp()
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_hd", "palette_reference": ".gamearts/palette/main.palette.json"})
        board = self.root / "board.png"
        Image.new("RGB", (len(SPRITE_PALETTE), 1)).save(board)
        for x, colour in enumerate(SPRITE_PALETTE):
            with Image.open(board) as opened:
                strip = opened.copy()
            strip.putpixel((x, 0), colour)
            strip.save(board)
        palette.extract(board, name="main", output_dir=self.root / ".gamearts" / "palette", max_colours=16, root=self.root)
        self.source = self.root / "soft.png"
        soft_picture().save(self.source)

    def run_clean(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "--clean", "--image", str(self.source), "--output", str(self.root / "native.cleaned.png"),
                               "--report", str(self.root / "native.cleaned.json"), "--game-root", str(self.root), *extra], capture_output=True, text=True)

    def test_the_command_writes_a_labelled_copy_a_report_and_the_checks_it_passes(self):
        before = common.sha256_file(self.source)
        done = self.run_clean("--target-long-side", "50")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(common.sha256_file(self.source), before)
        saved = json.loads((self.root / "native.cleaned.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["source"], {"file": "soft.png", "sha256": before})
        self.assertIn("working copy", saved["kind"])
        self.assertIn(saved["checks"]["status"], ("passed", "untested"), saved["checks"])  # a 50 x 26 sprite has too few edges for the grid check to say
        results = {item["name"]: item["status"] for item in saved["checks"]["style"]}
        self.assertEqual(results["palette_exact"], "passed")
        self.assertEqual(results["colour_count_max"], "passed")
        self.assertNotIn("failed", results.values())
        self.assertEqual(saved["checks"]["key_policy"]["issues"], [])
        with Image.open(self.root / "native.cleaned.png") as shown:
            self.assertEqual((shown.mode, shown.size), ("RGBA", (50, 26)))
            self.assertEqual(shown.getchannel("A").getextrema(), (255, 255))

    def test_an_existing_output_is_never_overwritten(self):
        (self.root / "native.cleaned.png").write_bytes(b"mine")
        done = self.run_clean("--target-long-side", "50")
        self.assertEqual(done.returncode, 1)
        self.assertIn("already exists", done.stderr)
        self.assertEqual((self.root / "native.cleaned.png").read_bytes(), b"mine")

    def test_a_refused_picture_blocks_with_the_reason_and_writes_nothing(self):
        done = self.run_clean()  # no size and no grid
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)
        self.assertIn("--target-long-side", done.stderr)
        self.assertFalse((self.root / "native.cleaned.png").exists())
        self.assertFalse((self.root / "native.cleaned.json").exists())

    def test_the_size_options_belong_to_clean(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "--image", str(self.source), "--output", str(self.root / "x.png"), "--target-long-side", "50"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("belong to --clean", done.stderr)


if __name__ == "__main__":
    unittest.main()
