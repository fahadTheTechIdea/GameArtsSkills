"""Animation previews (plan P11.6): a strip PNG and a looping GIF per animation, as review aids that never become art."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit as kit
from test_animation_checks import build, frame

import render_preview as preview  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_preview.py"
KEY = (255, 0, 255)


class PreviewCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.out = self.root / "previews"

    def tearDown(self):
        self._tmp.cleanup()

    def sheet(self, frames=None, **kwargs):
        return build(self.root, frames or [frame(x) for x in (2, 3, 4, 5)], **kwargs)


class DrawingTests(PreviewCase):
    def test_the_key_colour_is_drawn_as_a_checkerboard_and_the_art_is_kept(self):
        shown = preview.show_key_as_checkerboard(frame(2))
        self.assertNotIn(KEY, {shown.getpixel((x, y)) for x in range(shown.width) for y in range(shown.height)})
        self.assertEqual(shown.getpixel((3, 12)), (40, 90, 160))
        self.assertNotEqual(shown.getpixel((0, 0)), shown.getpixel((8, 0)))  # the two checker tones alternate

    def test_pixel_art_is_enlarged_by_whole_numbers_without_blending(self):
        small = Image.new("RGB", (2, 1))
        small.putpixel((0, 0), (255, 0, 0))
        small.putpixel((1, 0), (0, 0, 255))
        big = preview.enlarge(small, 4, pixel_art=True)
        self.assertEqual(big.size, (8, 4))
        self.assertEqual({big.getpixel((x, 0)) for x in range(8)}, {(255, 0, 0), (0, 0, 255)})

    def test_other_looks_are_enlarged_smoothly(self):
        small = Image.new("RGB", (2, 1))
        small.putpixel((0, 0), (255, 0, 0))
        small.putpixel((1, 0), (0, 0, 255))
        self.assertGreater(len({preview.enlarge(small, 4, pixel_art=False).getpixel((x, 0)) for x in range(8)}), 2)

    def test_the_automatic_scale_makes_small_frames_readable_and_never_huge(self):
        small = [{"cell": Image.new("RGB", (16, 16))}]
        large = [{"cell": Image.new("RGB", (400, 300))}]
        tiny = [{"cell": Image.new("RGB", (2, 2))}]
        self.assertEqual(preview.automatic_scale(small), 8)
        self.assertEqual(preview.automatic_scale(large), 1)
        self.assertEqual(preview.automatic_scale(tiny), preview.MAX_AUTO_SCALE)

    def test_a_long_animation_wraps_onto_rows_instead_of_one_endless_strip(self):
        pictures = [Image.new("RGB", (200, 100), (i, i, i)) for i in range(30)]
        strip = preview.strip_picture(pictures)
        self.assertLessEqual(strip.width, preview.STRIP_WIDTH + 2 * preview.GAP)
        self.assertGreater(strip.height, 100 * 2)


class TimingTests(PreviewCase):
    def test_gif_timing_keeps_hundredths_and_says_which_frames_changed(self):
        frames = [{"name": "a", "duration_ms": 100}, {"name": "b", "duration_ms": 12}, {"name": "c", "duration_ms": 87}]
        durations, changed = preview.gif_timing(frames)
        self.assertEqual(durations, [100, 20, 90])
        self.assertEqual(changed, ["b", "c"])

    def test_exact_hundredths_are_not_reported_as_changed(self):
        _, changed = preview.gif_timing([{"name": "a", "duration_ms": 40}, {"name": "b", "duration_ms": 120}])
        self.assertEqual(changed, [])


class RenderTests(PreviewCase):
    def test_one_strip_and_one_gif_are_written_per_animation(self):
        sheet, atlas = self.sheet([frame(x) for x in (2, 3, 4, 5)], durations=[100, 100, 100, 100])
        summaries = preview.render(sheet, atlas, self.out)
        self.assertEqual(len(summaries), 1)
        one = summaries[0]
        self.assertEqual((one["action"], one["direction"], one["frames"], one["duration_ms"]), ("walk", "E", 4, 400))
        with Image.open(self.out / one["gif"]) as gif:
            self.assertEqual(gif.n_frames, 4)
            self.assertEqual(gif.info["loop"], 0)
            self.assertEqual(gif.info["duration"], 100)
            _, _, cell_w, cell_h = json.loads(atlas.read_text(encoding="utf-8"))["frames"][0]["rect"]
            self.assertEqual(gif.size, (cell_w * one["scale"], cell_h * one["scale"]))
        with Image.open(self.out / one["strip"]) as strip:
            self.assertGreater(strip.width, 4 * 24 * one["scale"])

    def test_the_gif_frames_follow_the_atlas_durations(self):
        sheet, atlas = self.sheet([frame(x) for x in (2, 3, 4)], durations=[60, 120, 200])
        one = preview.render(sheet, atlas, self.out)[0]
        seen = []
        with Image.open(self.out / one["gif"]) as gif:
            for index in range(gif.n_frames):
                gif.seek(index)
                seen.append(gif.info["duration"])
        self.assertEqual(seen, [60, 120, 200])

    def test_the_picture_shows_the_art_and_no_key_colour_by_default(self):
        sheet, atlas = self.sheet()
        one = preview.render(sheet, atlas, self.out, scale=2)[0]
        with Image.open(self.out / one["strip"]) as strip:
            colours = {c for _, c in strip.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertNotIn(KEY, colours)
        self.assertIn((40, 90, 160), colours)

    def test_the_key_colour_toggle_shows_the_key_as_it_is(self):
        sheet, atlas = self.sheet()
        one = preview.render(sheet, atlas, self.out, scale=2, show_key=True)[0]
        with Image.open(self.out / one["strip"]) as strip:
            colours = {c for _, c in strip.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertIn(KEY, colours)
        self.assertEqual(one["key_colour"], "shown as magenta")

    def test_every_direction_of_an_action_gets_its_own_files(self):
        with tempfile.TemporaryDirectory() as source:
            items = []
            for direction, xs in (("E", (2, 3, 4)), ("W", (6, 5, 4))):
                for index, x in enumerate(xs):
                    name = f"{direction}{index}.png"
                    frame(x).save(Path(source) / name)
                    items.append({"file": name, "name": f"walk_{direction}{index}", "direction": direction, "action": "walk", "pivot": [12, 15]})
            kit.build_sheet({"_input_dir": source, "name": "two", "asset_id": "anim", "columns": 3, "padding": 2, "frames": items}, self.root)
        summaries = preview.render(self.root / "two.png", self.root / "two.atlas.json", self.out)
        self.assertEqual({(s["direction"]) for s in summaries}, {"E", "W"})
        self.assertEqual(len({s["gif"] for s in summaries}), 2)
        only = preview.render(self.root / "two.png", self.root / "two.atlas.json", self.out, direction="W")
        self.assertEqual([s["direction"] for s in only], ["W"])

    def test_an_action_or_direction_that_is_not_on_the_sheet_is_refused(self):
        sheet, atlas = self.sheet()
        with self.assertRaisesRegex(ValueError, "No animation on this sheet matches action 'jump'"):
            preview.render(sheet, atlas, self.out, action="jump")
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_a_scale_below_one_and_an_enormous_preview_are_refused_with_the_reason(self):
        sheet, atlas = self.sheet()
        with self.assertRaisesRegex(ValueError, "whole number of at least 1"):
            preview.render(sheet, atlas, self.out, scale=0)
        with self.assertRaisesRegex(ValueError, "lower --scale"):
            preview.render(sheet, atlas, self.out, scale=100)  # 22 million pixels: over the limit, yet cheap if the limit were missing

    def test_a_sheet_with_a_broken_atlas_is_refused_not_guessed_at(self):
        sheet, atlas = self.sheet()
        broken = json.loads(atlas.read_text(encoding="utf-8"))
        del broken["frames"]
        atlas.write_text(json.dumps(broken), encoding="utf-8")
        with self.assertRaises(ValueError):
            preview.render(sheet, atlas, self.out)

    def test_rendering_again_replaces_the_previews_and_never_touches_the_sheet(self):
        sheet, atlas = self.sheet()
        before = (common.sha256_file(sheet), common.sha256_file(atlas))
        first = preview.render(sheet, atlas, self.out)[0]
        (self.out / first["gif"]).write_bytes(b"stale")
        again = preview.render(sheet, atlas, self.out)[0]
        with Image.open(self.out / again["gif"]) as gif:
            self.assertEqual(gif.n_frames, 4)
        self.assertEqual((common.sha256_file(sheet), common.sha256_file(atlas)), before)
        self.assertEqual([p.name for p in self.out.iterdir() if p.name.endswith(".tmp")], [])


class CommandTests(PreviewCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_the_command_writes_previews_and_labels_them_review_aids(self):
        sheet, atlas = self.sheet()
        done = self.run_script("--image", str(sheet), "--atlas", str(atlas), "--output-dir", str(self.out))
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertIn("Review aids only", report["note"])
        self.assertEqual(report["previews"][0]["scaling"], "nearest")
        self.assertTrue((self.out / report["previews"][0]["gif"]).is_file())

    def test_the_games_art_style_picks_smooth_scaling_for_painted_art(self):
        sheet, atlas = self.sheet()
        kit.write_settings(self.root, art_style={"id": "hand_painted"})
        done = self.run_script("--image", str(sheet), "--atlas", str(atlas), "--output-dir", str(self.out), "--game-root", str(self.root))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["previews"][0]["scaling"], "smooth")

    def test_an_explicit_scaling_wins_over_the_games_style(self):
        sheet, atlas = self.sheet()
        kit.write_settings(self.root, art_style={"id": "hand_painted"})
        done = self.run_script("--image", str(sheet), "--atlas", str(atlas), "--output-dir", str(self.out), "--game-root", str(self.root), "--scaling", "nearest")
        self.assertEqual(json.loads(done.stdout)["previews"][0]["scaling"], "nearest")

    def test_a_refusal_says_why_and_exits_one(self):
        sheet, atlas = self.sheet()
        done = self.run_script("--image", str(sheet), "--atlas", str(atlas), "--output-dir", str(self.out), "--action", "jump")
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)
        self.assertIn("jump", done.stderr)


if __name__ == "__main__":
    unittest.main()
