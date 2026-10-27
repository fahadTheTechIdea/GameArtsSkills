"""Atlas depth (plan P12.3): animation tags, per-frame trimming and shelf packing, with today's output unchanged when none is asked for."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit as kit

import build_sheet_atlas as builder  # noqa: E402  (the testkit puts scripts/ on the path)
import check_animation as animation  # noqa: E402
import gamearts_atlas as atlas_rules  # noqa: E402
import gamearts_common as common  # noqa: E402
import validate_sheet_atlas as validator  # noqa: E402

KEY = (255, 0, 255, 255)
GOLDEN_PNG = "52540a3bde3c8d041cde06eef5e5ade6e7fbe1f23c4a0bd633b36005fc6b2f79"  # of the decoded pixels and size: the compressed bytes differ between zlib builds
GOLDEN_ATLAS = "46b7f85c013b3e9a432b2e6f7a203360c848a8842cc39c2863c603233d086ee6"  # of the atlas without the frames' source hashes: the test's own PNGs compress differently between zlib builds
BLOCKS = [  # (ink box x, y, w, h) in a 20 x 20 source frame, colour
    ((7, 5, 6, 8), (200, 40, 40, 255)),
    ((3, 12, 10, 4), (40, 120, 200, 255)),
    ((0, 0, 4, 4), (30, 160, 30, 255)),
    ((8, 8, 3, 3), (240, 220, 30, 255)),
]
PIVOT = [10, 19]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atlas_digest(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for frame in data["frames"]:
        frame.pop("source_sha256", None)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def pixel_digest(path):
    with Image.open(path) as opened:
        return hashlib.sha256(opened.convert("RGBA").tobytes() + str(opened.size).encode()).hexdigest()


def source_frame(box, colour, size=(20, 20)):
    image = Image.new("RGBA", size, KEY)
    x, y, w, h = box
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            image.putpixel((xx, yy), colour)
    return image


class BuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.out = self.root / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def job(self, blocks=BLOCKS, frame_edits=None, **overrides):
        """A job whose frames are the given blocks; `frame_edits` maps a frame index to extra keys for that frame (pivot, anchors, allow_empty)."""
        items = []
        for index, (box, colour) in enumerate(blocks):
            source_frame(box, colour).save(self.src / f"f{index}.png")
            items.append({"file": f"f{index}.png", "name": f"walk_{index}", "direction": "E", "action": "walk", "pivot": list(PIVOT), "duration_ms": 100,
                          **(frame_edits or {}).get(index, {})})
        job = {"_input_dir": str(self.src), "name": "depth", "asset_id": "depth", "padding": 2, "frames": items}
        job.update(overrides)
        return job

    def build(self, **overrides):
        png, atlas = builder.build(self.job(**overrides), self.out)
        return png, json.loads(atlas.read_text(encoding="utf-8")), atlas

    def sheet(self, png):
        with Image.open(png) as opened:
            return opened.convert("RGBA")


class UnchangedTests(unittest.TestCase):
    def test_a_job_without_the_new_options_builds_byte_for_byte_as_before(self):
        with tempfile.TemporaryDirectory() as folder:
            frames = Path(folder) / "src"
            frames.mkdir()
            specs = [("a.png", (12, 10), {(4, 5): (20, 50, 90, 255), (5, 5): (200, 40, 40, 255), (6, 6): (30, 160, 30, 255)}),
                     ("b.png", (14, 9), {(2, 2): (20, 50, 90, 255), (9, 4): (250, 250, 20, 255)}),
                     ("c.png", (10, 12), {(1, 1): (90, 20, 150, 255), (7, 9): (20, 200, 200, 255), (7, 10): (20, 200, 200, 255)})]
            for name, size, dots in specs:
                kit.key_image(size, dots).save(frames / name)
            job = {"_input_dir": str(frames), "name": "golden", "asset_id": "golden", "columns": 2, "padding": 2, "spacing": 3, "duration_ms": 90, "pixels_per_meter": 16,
                   "frames": [{"file": "a.png", "name": "walk_0", "direction": "E", "action": "walk", "pivot": [4, 9], "anchors": {"hand": [8, 3]}, "duration_ms": 100},
                              {"file": "b.png", "name": "walk_1", "direction": "E", "action": "walk", "pivot": [5, 8]},
                              {"file": "c.png", "name": "idle_0", "direction": "S", "action": "idle", "pivot": [3, 11], "anchors": {"hand": [2, 4], "head": [4, 1]}, "duration_ms": 250}]}
            png, atlas = builder.build(job, Path(folder) / "out")
            self.assertEqual(pixel_digest(png), GOLDEN_PNG)
            self.assertEqual(atlas_digest(atlas), GOLDEN_ATLAS)


class TagRuleTests(unittest.TestCase):
    def test_a_good_tag_list_has_no_problems(self):
        tags = [{"name": "walk", "from": 0, "to": 3, "direction": "forward"}, {"name": "hit", "from": 4, "to": 5, "direction": "pingpong", "repeat": 1}]
        self.assertEqual(atlas_rules.tag_problems(tags, 6), [])

    def test_every_kind_of_bad_tag_is_named(self):
        cases = [([{"name": "a", "from": 0, "to": 9, "direction": "forward"}], "frame 9"),
                 ([{"name": "a", "from": 3, "to": 1, "direction": "forward"}], "from 3 is after to 1"),
                 ([{"name": "a", "from": -1, "to": 1, "direction": "forward"}], "frame -1"),
                 ([{"name": "a", "from": 0, "to": 1, "direction": "sideways"}], "direction 'sideways'"),
                 ([{"name": "a", "from": 0, "to": 1, "direction": "forward"}, {"name": "a", "from": 2, "to": 3, "direction": "forward"}], "used twice"),
                 ([{"name": "", "from": 0, "to": 1, "direction": "forward"}], "needs a name"),
                 ([{"name": "a", "from": 0, "to": 1, "direction": "forward", "repeat": -1}], "repeat"),
                 ([{"name": "a", "from": 0, "to": 1, "direction": "forward", "repeat": 1.5}], "repeat"),
                 ([{"name": "a", "from": "0", "to": 1, "direction": "forward"}], "whole numbers")]
        for tags, expected in cases:
            with self.subTest(expected):
                problems = atlas_rules.tag_problems(tags, 4)
                self.assertTrue(any(expected in p for p in problems), problems)

    def test_the_four_directions_are_the_ones_aseprite_writes(self):
        self.assertEqual(atlas_rules.TAG_DIRECTIONS, ("forward", "reverse", "pingpong", "pingpong_reverse"))


class TagBuildTests(BuildCase):
    def test_tags_are_written_into_the_atlas_and_the_sheet_validates(self):
        tags = [{"name": "walk", "from": 0, "to": 3, "direction": "forward"}, {"name": "blink", "from": 1, "to": 2, "direction": "pingpong", "repeat": 2}]
        png, atlas, path = self.build(tags=tags)
        self.assertEqual(atlas["tags"], tags)
        self.assertEqual(validator.validate(png, path), [])

    def test_a_job_without_tags_writes_no_tags_key(self):
        _, atlas, _ = self.build()
        self.assertNotIn("tags", atlas)

    def test_a_bad_tag_stops_the_build_and_leaves_nothing_behind(self):
        with self.assertRaisesRegex(ValueError, "frame 9"):
            self.build(tags=[{"name": "walk", "from": 0, "to": 9, "direction": "forward"}])
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_the_validator_catches_a_tag_edited_into_the_atlas_afterwards(self):
        png, atlas, path = self.build(tags=[{"name": "walk", "from": 0, "to": 3, "direction": "forward"}])
        atlas["tags"][0]["to"] = 40
        path.write_text(json.dumps(atlas), encoding="utf-8")
        self.assertTrue(any("tag" in issue and "frame 40" in issue for issue in validator.validate(png, path)))

    def test_a_tag_the_schema_cannot_accept_is_reported_by_the_validator(self):
        png, atlas, path = self.build(tags=[{"name": "walk", "from": 0, "to": 3, "direction": "forward"}])
        atlas["tags"][0]["direction"] = "sideways"
        path.write_text(json.dumps(atlas), encoding="utf-8")
        self.assertTrue(validator.validate(png, path))


class TrimTests(BuildCase):
    def crop_box(self, box):
        """The source-space box that must be kept: the ink box joined with the pivot point."""
        x, y, w, h = box
        x0, y0 = min(x, PIVOT[0]), min(y, PIVOT[1])
        x1, y1 = max(x + w, PIVOT[0]), max(y + h, PIVOT[1])
        return x0, y0, x1 - x0, y1 - y0

    def test_each_cell_is_the_ink_joined_with_the_pivot_plus_the_padding(self):
        _, atlas, _ = self.build(trim=True, pack="shelf")
        for (box, _), frame in zip(BLOCKS, atlas["frames"]):
            x0, y0, w, h = self.crop_box(box)
            self.assertEqual(frame["rect"][2:], [w + 4, h + 4], frame["name"])
            self.assertEqual(frame["trim"], [x0, y0, w, h])

    def test_the_pixels_in_the_sheet_are_the_source_pixels_of_the_kept_box(self):
        png, atlas, _ = self.build(trim=True, pack="shelf")
        sheet = self.sheet(png)
        for index, frame in enumerate(atlas["frames"]):
            x0, y0, w, h = frame["trim"]
            source = Image.open(self.src / f"f{index}.png").convert("RGBA").crop((x0, y0, x0 + w, y0 + h))
            cell_x, cell_y = frame["rect"][:2]
            self.assertEqual(sheet.crop((cell_x + 2, cell_y + 2, cell_x + 2 + w, cell_y + 2 + h)).tobytes(), source.tobytes(), frame["name"])

    def test_the_pivot_stays_inside_its_cell_and_maps_back_to_the_source_pivot(self):
        _, atlas, path = self.build(trim=True, pack="shelf")
        for frame in atlas["frames"]:
            w, h = frame["rect"][2:]
            self.assertTrue(0 <= frame["pivot"][0] <= w and 0 <= frame["pivot"][1] <= h, frame)
            offset = frame["source_offset_in_cell"]
            self.assertEqual([frame["pivot"][0] - offset[0], frame["pivot"][1] - offset[1]], PIVOT)

    def test_a_pivot_above_and_left_of_the_art_stays_inside_its_cell(self):
        png, atlas, path = self.build(blocks=[((12, 14, 4, 4), (200, 40, 40, 255))], frame_edits={0: {"pivot": [5, 3]}}, trim=True, pack="shelf")
        frame = atlas["frames"][0]
        self.assertEqual(frame["trim"], [5, 3, 11, 15])  # the pivot joins the art: x 5 to 16, y 3 to 18
        self.assertEqual(frame["pivot"], [2, 2])
        self.assertEqual(validator.validate(png, path), [])

    def test_anchors_follow_the_same_offset_as_the_pivot(self):
        _, atlas, _ = self.build(trim=True, pack="shelf", frame_edits={0: {"anchors": {"hand": [9, 6]}}})
        frame = atlas["frames"][0]
        self.assertEqual(frame["anchors"]["hand"], [9 + frame["source_offset_in_cell"][0], 6 + frame["source_offset_in_cell"][1]])

    def test_a_trimmed_sheet_is_smaller_than_the_grid_and_passes_the_validator(self):
        png, atlas, path = self.build(trim=True, pack="shelf")
        self.assertEqual(validator.validate(png, path), [])
        plain_png, _ = builder.build(self.job(name="plain"), self.root / "plain_out")
        trimmed, plain = self.sheet(png), self.sheet(plain_png)
        self.assertLess(trimmed.width * trimmed.height, plain.width * plain.height)

    def test_a_blank_frame_keeps_a_cell_that_holds_its_pivot(self):
        png, atlas, path = self.build(blocks=BLOCKS + [((0, 0, 0, 0), KEY)], frame_edits={4: {"allow_empty": True}}, trim=True, pack="shelf")
        blank = atlas["frames"][-1]
        self.assertEqual(validator.validate(png, path), [])
        self.assertTrue(0 <= blank["pivot"][0] <= blank["rect"][2] and 0 <= blank["pivot"][1] <= blank["rect"][3])
        self.assertIsNone(blank["source_ink_bounds"])

    def test_the_trimmed_flag_is_true_only_where_the_kept_box_is_smaller_than_the_frame(self):
        _, atlas, _ = self.build(blocks=[((0, 0, 20, 20), (10, 10, 10, 255)), BLOCKS[0]], frame_edits={0: {"pivot": [10, 10]}}, trim=True, pack="shelf")
        self.assertEqual([f["trimmed"] for f in atlas["frames"]], [False, True])
        self.assertEqual(atlas["frames"][0]["trim"], [0, 0, 20, 20])

    def test_trim_needs_the_shelf_layout_because_a_grid_has_equal_cells(self):
        with self.assertRaisesRegex(ValueError, "trim needs pack 'shelf'"):
            self.build(trim=True)


class PackTests(BuildCase):
    def test_frames_keep_their_job_order_and_none_overlap(self):
        png, atlas, path = self.build(pack="shelf", trim=True)
        self.assertEqual([f["index"] for f in atlas["frames"]], [0, 1, 2, 3])
        self.assertEqual([f["name"] for f in atlas["frames"]], [f"walk_{i}" for i in range(4)])
        self.assertEqual(validator.validate(png, path), [])

    def test_a_shelf_layout_says_so_and_has_no_grid_fields(self):
        _, atlas, _ = self.build(pack="shelf", trim=True)
        self.assertEqual(atlas["layout"], "shelf")
        for key in ("cell_size", "columns", "rows"):
            self.assertNotIn(key, atlas)

    def test_the_default_layout_is_the_grid_and_an_old_atlas_has_no_layout_key(self):
        _, atlas, _ = self.build()
        self.assertNotIn("layout", atlas)
        self.assertIn("cell_size", atlas)
        for frame in atlas["frames"]:
            self.assertNotIn("trim", frame)
            self.assertNotIn("trimmed", frame)

    def test_the_same_job_packs_to_the_same_bytes_every_time(self):
        first, _, _ = self.build(pack="shelf", trim=True)
        first_hash = digest(first)
        self.out = self.root / "again"
        second, _, _ = self.build(pack="shelf", trim=True)
        self.assertEqual(digest(second), first_hash)

    def test_the_sheet_never_exceeds_max_width_and_wraps_onto_new_shelves(self):
        png, atlas, _ = self.build(pack="shelf", trim=True, max_width=30)
        self.assertLessEqual(self.sheet(png).width, 30)
        self.assertGreater(len({f["rect"][1] for f in atlas["frames"]}), 1)

    def test_frames_on_one_shelf_keep_the_requested_spacing(self):
        _, atlas, _ = self.build(pack="shelf", trim=True, spacing=5)
        rects = [f["rect"] for f in atlas["frames"]]
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                horizontal = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]))
                vertical = max(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
                self.assertGreaterEqual(max(horizontal, vertical), 5, (a, b))

    def test_a_frame_wider_than_max_width_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, "walk_0.*wider than max_width"):
            self.build(pack="shelf", trim=True, max_width=8)

    def test_columns_belong_to_the_grid_only(self):
        with self.assertRaisesRegex(ValueError, "columns applies to the grid"):
            self.build(pack="shelf", columns=2)

    def test_an_unknown_layout_is_refused_by_the_schema(self):
        with self.assertRaises(ValueError):
            self.build(pack="spiral")


class BlendTests(BuildCase):
    def test_the_six_modes_reach_the_atlas_as_advice(self):
        for mode in ("normal", "additive", "subtractive", "multiply", "screen", "premultiplied"):
            with self.subTest(mode):
                self.out = self.root / f"out_{mode}"
                png, atlas, path = self.build(blend_mode=mode, name=f"glow_{mode}")
                self.assertEqual(atlas["blend_mode"], mode)
                self.assertEqual(validator.validate(png, path), [])

    def test_a_sheet_that_names_no_mode_has_none_in_its_atlas(self):
        _, atlas, _ = self.build()
        self.assertNotIn("blend_mode", atlas)

    def test_the_pixels_are_not_changed_by_the_mode(self):
        plain_png, _, _ = self.build()
        self.out = self.root / "glow"
        glow_png, _, _ = self.build(blend_mode="additive")
        self.assertEqual(self.sheet(plain_png).tobytes(), self.sheet(glow_png).tobytes())

    def test_a_mode_nobody_knows_is_refused(self):
        with self.assertRaises(ValueError):
            self.build(blend_mode="overlay")

    def test_a_mode_edited_into_a_finished_atlas_is_caught_by_the_validator(self):
        png, atlas, path = self.build(blend_mode="additive")
        atlas["blend_mode"] = "dodge"
        path.write_text(json.dumps(atlas), encoding="utf-8")
        self.assertTrue(validator.validate(png, path))


class ConsumerTests(BuildCase):
    def test_animation_checks_agree_on_a_trimmed_sheet_and_an_untrimmed_one(self):
        blocks = [((x, 8, 4, 4), (40, 90, 160, 255)) for x in (2, 4, 6, 8, 6, 4)]
        plain_png, plain_atlas = builder.build(self.job(blocks, name="plain"), self.root / "plain")
        trimmed_png, trimmed_atlas = builder.build(self.job(blocks, name="trimmed", trim=True, pack="shelf"), self.root / "trimmed")
        first = animation.check_sheet(plain_png, plain_atlas, {})
        second = animation.check_sheet(trimmed_png, trimmed_atlas, {})
        self.assertEqual([(c["name"], c["status"]) for c in first["animations"][0]["checks"]],
                         [(c["name"], c["status"]) for c in second["animations"][0]["checks"]])
        self.assertEqual(second["animations"][0]["frames"], 6)

    def test_a_broken_loop_is_still_found_on_a_trimmed_sheet(self):
        blocks = [((x, 8, 4, 4), (40, 90, 160, 255)) for x in (2, 3, 4, 5, 6, 7)]
        png, atlas = builder.build(self.job(blocks, name="jump", trim=True, pack="shelf"), self.root / "jump")
        checks = {c["name"]: c for c in animation.check_sheet(png, atlas, {})["animations"][0]["checks"]}
        self.assertEqual(checks["loop_seam"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
