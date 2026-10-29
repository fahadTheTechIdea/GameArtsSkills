"""Palette variants: a fixed colour-for-colour map, the key colour and transparency untouched, nothing overwritten, every run recorded."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import gamearts_testkit  # noqa: F401  (puts scripts/ on the path)

import gamearts_common as common  # noqa: E402
import gamearts_palette as palette  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_palette.py"
KEY = common.KEY_RGB
RED, GREEN, BLUE = (200, 30, 30), (30, 160, 40), (30, 40, 200)
GOLD, TEAL, VIOLET = (220, 190, 40), (20, 150, 160), (110, 40, 170)


def picture(path, pixels):
    """A one-row PNG whose pixels are the given colours (RGB or RGBA), left to right."""
    size = (len(pixels), 1)
    image = Image.frombytes("RGBA", size, bytes(b for p in pixels for b in (p if len(p) == 4 else (*p, 255))))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return Path(path)


def pixels_of(path):
    with Image.open(path) as image:
        data = image.convert("RGBA").tobytes()
    return [tuple(data[i:i + 4]) for i in range(0, len(data), 4)]


def hexed(colour):
    return "#{:02X}{:02X}{:02X}".format(*colour)


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.mapping = {RED: GOLD, GREEN: TEAL, BLUE: VIOLET}

    def source(self, name="hero.png", pixels=None):
        return picture(self.root / "frames" / name, pixels or [RED, GREEN, KEY, BLUE])


class ImageTests(Case):
    def test_colours_change_and_the_key_stays_exactly_as_it_was(self):
        out = self.root / "variant" / "hero.png"
        record = palette.recolour(self.root, self.mapping, [self.source()], out)
        self.assertEqual(pixels_of(out), [(*GOLD, 255), (*TEAL, 255), (*KEY, 255), (*VIOLET, 255)])
        self.assertEqual(record["files"][0]["pixels_changed"], 3)

    def test_transparent_pixels_are_untouched_and_soft_alpha_is_kept(self):
        source = self.source(pixels=[(*RED, 128), (*GREEN, 0), (*BLUE, 255), KEY])
        out = self.root / "variant" / "hero.png"
        palette.recolour(self.root, self.mapping, [source], out)
        self.assertEqual(pixels_of(out), [(*GOLD, 128), (*GREEN, 0), (*VIOLET, 255), (*KEY, 255)])

    def test_the_input_is_never_changed(self):
        source = self.source()
        before = common.sha256_file(source)
        palette.recolour(self.root, self.mapping, [source], self.root / "variant" / "hero.png")
        self.assertEqual(common.sha256_file(source), before)

    def test_the_record_ties_the_variant_to_the_exact_pictures_it_came_from(self):
        source, out = self.source(), self.root / "variant" / "hero.png"
        palette.recolour(self.root, self.mapping, [source], out)
        record = common.read_json(self.root / "variant" / "hero.png.recolour.json")
        common.validate_schema(record, "gamearts-recolour-record")
        entry = record["files"][0]
        self.assertEqual((entry["source_sha256"], entry["output_sha256"]), (common.sha256_file(source), common.sha256_file(out)))
        self.assertEqual(record["mapping"][hexed(RED)], hexed(GOLD))

    def test_a_colour_the_map_does_not_list_is_refused_by_name_and_nothing_is_written(self):
        source = self.source(pixels=[RED, (1, 2, 3), KEY, BLUE])
        out = self.root / "variant" / "hero.png"
        with self.assertRaisesRegex(ValueError, "#010203"):
            palette.recolour(self.root, self.mapping, [source], out)
        self.assertFalse(out.exists())

    def test_snapping_treats_a_stray_as_its_nearest_listed_colour_and_records_how_far(self):
        stray = (205, 35, 28)
        source = self.source(pixels=[RED, stray, KEY, BLUE])
        out = self.root / "variant" / "hero.png"
        record = palette.recolour(self.root, self.mapping, [source], out, snap=True)
        self.assertEqual(pixels_of(out)[1], (*GOLD, 255))
        self.assertEqual((record["snapped"][0]["colour"], record["snapped"][0]["treated_as"]), (hexed(stray), hexed(RED)))
        self.assertGreater(record["snapped"][0]["distance"], 0)

    def test_two_colours_may_not_share_a_target_unless_that_is_asked_for(self):
        merging = {RED: GOLD, GREEN: GOLD, BLUE: VIOLET}
        with self.assertRaisesRegex(ValueError, "lose the detail"):
            palette.recolour(self.root, merging, [self.source()], self.root / "variant" / "hero.png")
        record = palette.recolour(self.root, merging, [self.source()], self.root / "variant" / "hero.png", allow_merge=True)
        self.assertEqual(record["merged"], [{"target": hexed(GOLD), "sources": sorted([hexed(RED), hexed(GREEN)])}])

    def test_a_target_at_or_near_the_key_colour_is_refused(self):
        for target in (KEY, (250, 8, 250)):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "key colour"):
                    palette.recolour(self.root, {RED: target, GREEN: TEAL, BLUE: VIOLET}, [self.source()], self.root / "variant" / "hero.png")

    def test_an_existing_output_is_never_overwritten(self):
        out = picture(self.root / "variant" / "hero.png", [RED])
        before = common.sha256_file(out)
        with self.assertRaisesRegex(ValueError, "never overwrites"):
            palette.recolour(self.root, self.mapping, [self.source()], out)
        self.assertEqual(common.sha256_file(out), before)

    def test_an_output_outside_the_game_is_refused(self):
        outside = Path(tempfile.mkdtemp()) / "hero.png"
        self.addCleanup(lambda: outside.parent.rmdir() if outside.parent.exists() and not any(outside.parent.iterdir()) else None)
        with self.assertRaisesRegex(ValueError, "outside the game folder"):
            palette.recolour(self.root, self.mapping, [self.source()], outside)
        self.assertFalse(outside.exists())

    def test_an_empty_map_is_refused(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            palette.recolour(self.root, {}, [self.source()], self.root / "variant" / "hero.png")


class SpeedPathTests(Case):
    """The mask path (fast on a big sheet) and the pixel loop (the reference) must give the same bytes for the same table."""

    def mixed(self):
        pixels = [RED, GREEN, BLUE, KEY, (*RED, 128), (*GREEN, 0), (*KEY, 77), (9, 9, 9), GOLD, RED, BLUE, GREEN]
        return Image.frombytes("RGBA", (len(pixels), 1), bytes(b for p in pixels for b in (p if len(p) == 4 else (*p, 255))))

    def both(self, table):
        image = self.mixed()
        fast, fast_count = palette.recolour_image(image, table)
        slow, slow_count = palette._recolour_pixels(image.convert("RGBA"), table)
        self.assertEqual(fast.tobytes(), slow.tobytes())
        self.assertEqual(fast_count, slow_count)
        return fast

    def test_the_two_paths_agree_on_a_mixed_picture(self):
        self.both({RED: GOLD, GREEN: TEAL, BLUE: VIOLET, (9, 9, 9): (10, 10, 10), GOLD: GOLD})

    def test_a_swap_does_not_chain_through_the_first_replacement(self):
        swapped = self.both({RED: GREEN, GREEN: RED})
        self.assertEqual(list(swapped.tobytes()[:8]), [*GREEN, 255, *RED, 255])

    def test_a_table_that_lists_the_key_colour_leaves_key_pixels_alone(self):
        result = self.both({KEY: GOLD, RED: GOLD})
        data = result.tobytes()
        self.assertEqual(tuple(data[12:16]), (*KEY, 255))
        self.assertEqual(tuple(data[24:28]), (*KEY, 77))

    def test_above_the_limit_the_pixel_loop_is_used_and_gives_the_same_picture(self):
        table = {RED: GOLD, GREEN: TEAL, BLUE: VIOLET}
        expected, _ = palette.recolour_image(self.mixed(), table)
        with mock.patch.object(palette, "MASK_LIMIT", 0):
            looped, _ = palette.recolour_image(self.mixed(), table)
        self.assertEqual(looped.tobytes(), expected.tobytes())


class FolderTests(Case):
    def folder(self):
        self.source("a.png")
        self.source("walk/b.png", pixels=[BLUE, KEY, RED, GREEN])
        return self.root / "frames"

    def test_every_picture_is_recoloured_in_the_same_layout_with_one_record(self):
        out = self.root / "variant"
        record = palette.recolour(self.root, self.mapping, [self.folder()], out, folder=True)
        self.assertEqual(sorted(f["output"] for f in record["files"]), ["a.png", "walk/b.png"])
        self.assertEqual(pixels_of(out / "walk" / "b.png"), [(*VIOLET, 255), (*KEY, 255), (*GOLD, 255), (*TEAL, 255)])
        common.validate_schema(common.read_json(out / palette.RECOLOUR_RECORD), "gamearts-recolour-record")

    def test_one_bad_picture_stops_the_whole_run_before_anything_is_written(self):
        folder = self.folder()
        picture(folder / "walk" / "c.png", [(9, 9, 9), RED, KEY, BLUE])
        out = self.root / "variant"
        with self.assertRaisesRegex(ValueError, "c.png"):
            palette.recolour(self.root, self.mapping, [folder], out, folder=True)
        self.assertFalse(out.exists())

    def test_a_failure_part_way_takes_back_what_was_written(self):
        out = self.root / "variant"
        real = palette.recolour_image
        calls = []

        def fail_second(image, table):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(image, table)

        with mock.patch.object(palette, "recolour_image", fail_second):
            with self.assertRaises(OSError):
                palette.recolour(self.root, self.mapping, [self.folder()], out, folder=True)
        self.assertEqual([p for p in out.rglob("*") if p.is_file()], [])

    def test_a_folder_that_already_holds_files_is_refused(self):
        out = self.root / "variant"
        picture(out / "old.png", [RED])
        with self.assertRaisesRegex(ValueError, "never overwrites"):
            palette.recolour(self.root, self.mapping, [self.folder()], out, folder=True)

    def test_a_folder_with_no_pictures_is_refused(self):
        (self.root / "empty").mkdir()
        with self.assertRaisesRegex(ValueError, "no PNG"):
            palette.recolour(self.root, self.mapping, [self.root / "empty"], self.root / "variant", folder=True)


class MapTests(Case):
    def write(self, name, body):
        path = self.root / name
        path.write_text(json.dumps(body), encoding="utf-8")
        return path

    def palette_file(self, name, colours):
        return self.write(name, {"schema_version": "1.0", "name": name.split(".")[0], "method": "exact", "max_colours": len(colours),
                                 "colours": [{"hex": hexed(c), "share": round(1 / len(colours), 6)} for c in colours],
                                 "source": {"file": "x.png", "sha256": "a" * 64}})

    def test_a_map_file_loads(self):
        path = self.write("map.json", {"schema_version": "1.0", "colours": {hexed(RED): hexed(GOLD)}})
        self.assertEqual(palette.load_colour_map(path), {RED: GOLD})

    def test_a_map_that_breaks_its_contract_is_refused(self):
        with self.assertRaises(ValueError):
            palette.load_colour_map(self.write("bad.json", {"schema_version": "1.0", "colours": {"red": "#112233"}}))

    def test_the_same_source_colour_twice_is_refused_even_when_the_case_differs(self):
        path = self.write("dup.json", {"schema_version": "1.0", "colours": {"#aabbcc": "#112233", "#AABBCC": "#445566"}})
        with self.assertRaisesRegex(ValueError, "twice"):
            palette.load_colour_map(path)

    def test_two_palettes_of_the_same_size_pair_by_position(self):
        first = self.palette_file("a.palette.json", [RED, GREEN, BLUE])
        second = self.palette_file("b.palette.json", [GOLD, TEAL, VIOLET])
        self.assertEqual(palette.pair_palettes(first, second), {RED: GOLD, GREEN: TEAL, BLUE: VIOLET})

    def test_palettes_of_different_sizes_are_not_paired(self):
        first = self.palette_file("a.palette.json", [RED, GREEN, BLUE])
        second = self.palette_file("b.palette.json", [GOLD, TEAL])
        with self.assertRaisesRegex(ValueError, "same number"):
            palette.pair_palettes(first, second)


class CommandLineTests(Case):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "recolour", "--game-root", str(self.root), *map(str, args)], capture_output=True, text=True)

    def test_the_command_recolours_a_picture_and_says_what_comes_next(self):
        mapfile = self.root / "map.json"
        mapfile.write_text(json.dumps({"schema_version": "1.0", "colours": {hexed(k): hexed(v) for k, v in self.mapping.items()}}), encoding="utf-8")
        out = self.root / "variant" / "hero.png"
        done = self.run_cli("--image", self.source(), "--output", out, "--map", mapfile)
        self.assertEqual(done.returncode, 0, done.stderr)
        body = json.loads(done.stdout)
        self.assertEqual((body["files"], body["pixels_changed"]), (1, 3))
        self.assertIn("new art", body["next_step"])
        self.assertTrue(out.is_file())

    def test_a_blocked_run_exits_with_the_reason(self):
        mapfile = self.root / "map.json"
        mapfile.write_text(json.dumps({"schema_version": "1.0", "colours": {hexed(RED): hexed(GOLD)}}), encoding="utf-8")
        done = self.run_cli("--image", self.source(), "--output", self.root / "variant" / "hero.png", "--map", mapfile)
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)

    def test_a_picture_needs_its_own_output_and_a_folder_its_own(self):
        mapfile = self.root / "map.json"
        mapfile.write_text(json.dumps({"schema_version": "1.0", "colours": {hexed(RED): hexed(GOLD)}}), encoding="utf-8")
        done = self.run_cli("--image", self.source(), "--output-folder", self.root / "variant", "--map", mapfile)
        self.assertEqual(done.returncode, 1)
        self.assertIn("goes with", done.stderr)


if __name__ == "__main__":
    unittest.main()
