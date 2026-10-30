"""Tests for cutting a generated strip into measured frames (scripts/slice_generated_strip.py)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
KEY = (255, 0, 255, 255)
BODY = (40, 60, 160, 255)
SKIN = (200, 150, 100, 255)


def run(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True)


def figure(draw, x, foot=90, height=60, arm=None):
    """A little person: body, head, feet on `foot`; `arm` = (dx, dy, w, h) beside the body."""
    draw.rectangle((x, foot - height + 1, x + 40, foot), fill=BODY)
    draw.rectangle((x + 10, foot - height - 19, x + 30, foot - height), fill=SKIN)
    if arm:
        draw.rectangle((x + arm[0], foot - height + arm[1], x + arm[0] + arm[2], foot - height + arm[1] + arm[3]), fill=SKIN)


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def strip(self, xs, size=(400, 100), alpha=False, feet=None, heights=None, name="strip.png", **more):
        image = Image.new("RGBA", size, (0, 0, 0, 0) if alpha else KEY)
        draw = ImageDraw.Draw(image)
        for number, x in enumerate(xs):
            figure(draw, x, foot=(feet or {}).get(number, 90), height=(heights or {}).get(number, 60), arm=more.get("arms", {}).get(number))
        path = self.dir / name
        image.save(path)
        return path

    def cut(self, path, frames, *extra, out="out", name="t_clap_e"):
        return run("slice_generated_strip.py", "--source", path, "--frames", frames, "--out", self.dir / out, "--name", name, *extra)

    def loaded(self, path):
        with Image.open(path) as opened:
            return opened.convert("RGBA")

    def size_of(self, path):
        with Image.open(path) as opened:
            return opened.size

    def blocked(self, result, text):
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("BLOCKED", result.stderr)
        self.assertRegex(result.stderr, text)
        self.assertEqual(result.stdout, "")


class CutTests(Case):
    def test_a_strip_becomes_equal_frames_with_one_pivot_that_the_sheet_builder_takes(self):
        source = self.strip([20, 120, 220, 320], arms={2: (40, 10, 20, 8)})
        before = source.read_bytes()
        result = self.cut(source, 4, "--direction", "E", "--action", "clap", "--planted")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "cut")
        self.assertEqual(report["warnings"], [])
        frames = sorted((self.dir / "out").glob("t_clap_e_*.png"))
        self.assertEqual(len(frames), 4)
        self.assertEqual({self.size_of(f) for f in frames}, {tuple(report["frame_size"])})  # one frame size
        job = json.loads((self.dir / "out" / "t_clap_e.job.json").read_text(encoding="utf-8"))
        self.assertEqual({tuple(f["pivot"]) for f in job["frames"]}, {tuple(report["pivot"])})  # one pivot
        self.assertEqual([(f["direction"], f["action"]) for f in job["frames"]], [("E", "clap")] * 4)
        self.assertEqual(source.read_bytes(), before)  # the source is never changed
        built = run("build_sheet_atlas.py", self.dir / "out" / "t_clap_e.job.json", "--output-dir", self.dir / "sheet")
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        checked = run("validate_sheet_atlas.py", self.dir / "sheet" / "t_clap_e.png", self.dir / "sheet" / "t_clap_e.atlas.json")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_a_figure_keeps_its_pixels_and_stands_on_the_shared_baseline_and_root(self):
        source = self.strip([20, 120, 220, 320], arms={1: (40, 10, 20, 8)})
        self.assertEqual(self.cut(source, 4).returncode, 0)
        sheet = [self.loaded(self.dir / "out" / f"t_clap_e_{n:02d}.png") for n in range(4)]
        job = json.loads((self.dir / "out" / "t_clap_e.job.json").read_text(encoding="utf-8"))
        for frame, entry in zip(sheet, job["frames"]):
            pivot = tuple(entry["pivot"])
            self.assertNotEqual(frame.getpixel((pivot[0], pivot[1] - 1)), KEY)  # the sole stands on the pivot
            self.assertEqual(frame.getpixel((pivot[0], pivot[1])), KEY)         # and the pivot is the first empty row under the feet
            self.assertEqual(frame.getpixel((pivot[0], pivot[1] - 5)), BODY)    # pixels as drawn
            body = [x for x in range(frame.width) if frame.getpixel((x, pivot[1] - 5)) == BODY]
            self.assertLessEqual(abs((pivot[0] - body[0]) - (body[-1] + 1 - pivot[0])), 1)  # the sole is centred on the pivot, give or take half a pixel
        self.assertEqual(sheet[0].getpixel((0, 0)), KEY)

    def test_uneven_gaps_are_cut_at_the_gutters_not_at_equal_slices(self):
        # an equal slice would cut at x=100, 200, 300: through the figures at 90 and 190
        source = self.strip([10, 90, 190, 330])
        result = self.cut(source, 4)
        self.assertEqual(result.returncode, 0, result.stderr)
        measured = json.loads(result.stdout)["measured"]
        self.assertEqual([m["size"] for m in measured], [[41, 80]] * 4)  # every figure whole

    def test_true_alpha_strips_give_alpha_frames_and_a_soft_alpha_job(self):
        source = self.strip([20, 120, 220, 320], alpha=True)
        self.assertEqual(self.cut(source, 4).returncode, 0)
        frame = self.loaded(self.dir / "out" / "t_clap_e_00.png")
        self.assertEqual(frame.getpixel((0, 0))[3], 0)
        self.assertTrue(json.loads((self.dir / "out" / "t_clap_e.job.json").read_text(encoding="utf-8"))["soft_alpha"])
        built = run("build_sheet_atlas.py", self.dir / "out" / "t_clap_e.job.json", "--output-dir", self.dir / "sheet")
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)

    def test_a_grid_is_cut_in_reading_order(self):
        image = Image.new("RGBA", (200, 220), KEY)
        draw = ImageDraw.Draw(image)
        for foot, height in ((90, 60), (200, 40)):  # the first row's figures are taller
            for x in (20, 120):
                figure(draw, x, foot=foot, height=height)
        image.save(self.dir / "grid.png")
        result = self.cut(self.dir / "grid.png", 4, "--columns", 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(m["index"], m["size"][1]) for m in json.loads(result.stdout)["measured"]], [(0, 80), (1, 80), (2, 60), (3, 60)])


class RefusalTests(Case):
    def test_no_gutter_is_refused_with_the_place_and_the_count(self):
        source = self.strip([20, 120, 220, 320], arms={1: (40, 10, 100, 8), 2: (-100, 10, 100, 8)})  # arms bridge both neighbours
        self.blocked(self.cut(source, 4), r"no transparent gutter near \d+ \(the emptiest place, \d+, holds \d+ art pixels\)")
        self.assertFalse((self.dir / "out").exists())

    def test_stray_specks_in_a_gutter_are_reported_and_more_are_refused(self):
        image = self.loaded(self.strip([20, 120, 220, 320]))
        draw = ImageDraw.Draw(image)
        draw.line((55, 5, 119, 5), fill=SKIN)  # one speck row over the first gutter: 1 art pixel in every column
        image.save(self.dir / "specks.png")
        result = self.cut(self.dir / "specks.png", 4)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(json.loads(result.stdout)["warnings"][0], r"no clear gutter near 100; cut at \d+, where 1 stray pixel")
        for y in range(5, 15):
            draw.line((55, y, 119, y), fill=SKIN)  # ten art pixels in every column of that gutter
        image.save(self.dir / "dirty.png")
        self.blocked(self.cut(self.dir / "dirty.png", 4, out="out2"), "no transparent gutter near 100")

    def test_a_figure_touching_the_edge_was_clipped_and_is_refused(self):
        self.blocked(self.cut(self.strip([0, 120, 220, 320]), 4), "frame 0: the figure touches the picture's edge")
        self.blocked(self.cut(self.strip([20, 120, 220, 320], feet={3: 99}, size=(400, 100)), 4, out="out2"), "frame 3: the figure touches the picture's edge")

    def test_a_picture_that_is_not_on_the_key_or_alpha_says_so_instead_of_asking_for_wider_gaps(self):
        image = Image.new("RGBA", (400, 100), (250, 10, 250, 255))  # a tool's near-magenta background: not the exact key, fully opaque
        figure(ImageDraw.Draw(image), 20)
        image.save(self.dir / "blurred.png")
        self.blocked(self.cut(self.dir / "blurred.png", 1), r"neither on an exact #FF00FF background \(0 exact-key pixels of 40000\) nor true alpha.*snap_to_pixel_grid\.py --clean")

    def test_a_cell_with_no_figure_is_refused(self):
        self.blocked(self.cut(self.strip([20, 120, 220]), 4), "frame 3: its cell holds no artwork")

    def test_frames_that_do_not_fit_the_columns_are_refused(self):
        self.blocked(self.cut(self.strip([20, 120, 220, 320]), 4, "--columns", 3), "do not fit 3 columns")

    def test_an_output_folder_with_files_is_never_written_into(self):
        (self.dir / "out").mkdir()
        (self.dir / "out" / "mine.txt").write_text("keep", encoding="utf-8")
        self.blocked(self.cut(self.strip([20, 120, 220, 320]), 4), "already holds files")
        self.assertEqual((self.dir / "out" / "mine.txt").read_text(encoding="utf-8"), "keep")


class MeasuredScaleTests(Case):
    def reference(self, height):
        image = Image.new("RGBA", (60, height + 30), KEY)
        figure(ImageDraw.Draw(image), 10, foot=height + 25, height=height - 20)
        path = self.dir / "ref.png"
        image.save(path)
        return path

    def test_one_scale_that_fits_every_frame_is_reported_not_applied(self):
        source = self.strip([20, 120, 220, 320])  # every figure 80 px tall
        result = self.cut(source, 4, "--reference", self.reference(160))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertAlmostEqual(json.loads(result.stdout)["scale"], 2.0, places=2)
        self.assertEqual(self.size_of(self.dir / "out" / "t_clap_e_00.png")[1], 84)  # frames are never resized

    def test_a_strip_that_needs_a_different_scale_per_frame_is_refused(self):
        source = self.strip([20, 120, 220, 320], heights={2: 40})  # one figure a quarter shorter
        self.blocked(self.cut(source, 4, "--reference", self.reference(160)), "no single scale brings every frame within 5%")

    def test_planted_feet_that_move_or_a_figure_that_grows_are_refused_only_when_asked(self):
        moving = self.strip([20, 120, 220, 320], feet={2: 80}, size=(400, 100))
        self.assertEqual(self.cut(moving, 4).returncode, 0)
        self.blocked(self.cut(moving, 4, "--planted", out="out2"), "frame 2: the planted feet move 10 px")
        growing = self.strip([20, 120, 220, 320], heights={3: 70}, name="grow.png", size=(400, 120), feet={0: 100, 1: 100, 2: 100, 3: 100})
        self.blocked(self.cut(growing, 4, "--planted", out="out3"), "frame 3: the figure's height changes")


if __name__ == "__main__":
    unittest.main()
