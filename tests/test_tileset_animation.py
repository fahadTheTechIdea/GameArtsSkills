"""Animated tiles: a tile shown as several frames in turn. A frame takes the labels of the tile it animates, so an animation can never change what
terrain a tile is, and the frames must still line up with their neighbours."""
import json

import gamearts_testkit  # noqa: F401  (puts scripts/ on the path)
from test_tileset import ART, SIZE, TERRAINS, BuildCase, corner_art, paint, tileset_of  # noqa: E402

import build_tileset as builder  # noqa: E402
import export_exchange as exchange  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_tileset as rules  # noqa: E402
import unittest  # noqa: E402
import validate_tileset as validator  # noqa: E402

BASE = 0
FIRST_FRAME = 16  # the tiles of a wang_corner_16 set are 0 to 15; frames come after them


def frames(*pairs):
    return [{"tile": tile, "duration_ms": ms} for tile, ms in pairs]


class RuleTests(unittest.TestCase):
    def tileset(self, animations, extra=2):
        base = tileset_of("wang_corner_16", extra=[tileset_of("wang_corner_16")["tiles"][BASE]["neighbours"]] * extra)
        base["animations"] = animations
        return base

    def test_frame_tiles_are_the_ones_that_only_exist_to_animate_another(self):
        tileset = self.tileset([{"tile": BASE, "frames": frames((BASE, 200), (16, 200), (17, 200))}])
        self.assertEqual(rules.animation_frame_ids(tileset), {16, 17})

    def test_extra_copies_of_a_tile_are_a_repeat_unless_they_are_animation_frames(self):
        plain = self.tileset([])
        self.assertTrue(any("repeats tile 0" in problem for problem in rules.label_problems(plain)))
        animated = self.tileset([{"tile": BASE, "frames": frames((BASE, 200), (16, 200), (17, 200))}])
        self.assertEqual(rules.label_problems(animated), [])

    def test_a_tile_that_is_not_in_the_set_is_named(self):
        problems = rules.animation_problems(self.tileset([{"tile": BASE, "frames": frames((BASE, 100), (99, 100))}]))
        self.assertTrue(any("frame tile 99 is not in the tileset" in problem for problem in problems), problems)
        problems = rules.animation_problems(self.tileset([{"tile": 99, "frames": frames((99, 100), (BASE, 100))}]))
        self.assertTrue(any("tile 99 is not in the tileset" in problem for problem in problems), problems)

    def test_a_tile_has_one_animation_and_a_frame_belongs_to_one(self):
        twice = self.tileset([{"tile": BASE, "frames": frames((BASE, 100), (16, 100))}, {"tile": BASE, "frames": frames((BASE, 100), (17, 100))}])
        self.assertTrue(any("already has animation 1" in problem for problem in rules.animation_problems(twice)))
        shared = self.tileset([{"tile": BASE, "frames": frames((BASE, 100), (16, 100))}, {"tile": 1, "frames": frames((1, 100), (16, 100))}])
        self.assertTrue(any("tile 16 is already a frame of animation 1" in problem for problem in rules.animation_problems(shared)))

    def test_a_frame_cannot_be_animated_itself(self):
        nested = self.tileset([{"tile": BASE, "frames": frames((BASE, 100), (16, 100))}, {"tile": 16, "frames": frames((16, 100), (17, 100))}])
        self.assertTrue(any("also animated itself" in problem for problem in rules.animation_problems(nested)))

    def test_a_tileset_without_animations_is_judged_exactly_as_before(self):
        self.assertEqual(rules.animation_problems(tileset_of("wang_corner_16")), [])
        self.assertEqual(rules.animation_frame_ids(tileset_of("wang_corner_16")), set())

    def test_the_schema_wants_two_frames_and_a_positive_duration(self):
        for animation in ({"tile": 0, "frames": frames((0, 100))}, {"tile": 0, "frames": frames((0, 0), (16, 100))}, {"tile": 0, "frames": frames((0, 100), (16, 99999999))}):
            with self.subTest(animation=animation):
                tileset = {"schema_version": "1.0", "name": "x", "atlas": "x.atlas.json", "tile_size": [8, 8], "layout": "variants", "terrains": ["grass"],
                           "tiles": [{"id": 0, "terrain": "grass"}, {"id": 16, "terrain": "grass"}], "animations": [animation]}
                with self.assertRaises(ValueError):
                    common.validate_schema(tileset, "gamearts-tileset")


class AnimatedBuildCase(BuildCase):
    def animated_job(self, frame_count=2, durations=(200, 200, 200), draw_frame=None):
        job = self.job()
        base_labels = job["tiles"][BASE]["neighbours"]
        steps = [(BASE, durations[0])]
        for k in range(frame_count):
            image = (draw_frame or self.shifted)(base_labels, k)
            image.save(self.src / f"frame{k}.png")
            job["tiles"].append({"file": f"frame{k}.png"})
            steps.append((FIRST_FRAME + k, durations[k + 1]))
        job["animations"] = [{"tile": BASE, "frames": frames(*steps)}]
        return job

    @staticmethod
    def shifted(labels, k):
        """The same tile with a mark in the middle (away from every side), so each frame is a different picture that still lines up."""
        image = corner_art(labels)
        paint(image, (SIZE // 2 - 1, SIZE // 2 - 1, SIZE // 2 + 1, SIZE // 2 + 1), (200 - 40 * k, 200, 60, 255))
        return image


class BuildTests(AnimatedBuildCase):
    def test_a_set_with_animation_frames_builds_and_validates(self):
        png, atlas, tileset = builder.build(self.animated_job(), self.out)
        self.assertEqual(validator.validate(tileset), [])
        record = common.read_json(tileset)
        self.assertEqual(len(record["tiles"]), 18)
        self.assertEqual(record["animations"], self.animated_job()["animations"])
        self.assertEqual(len(common.read_json(atlas)["frames"]), 18)

    def test_a_frame_takes_the_labels_of_the_tile_it_animates(self):
        _, _, tileset = builder.build(self.animated_job(), self.out)
        record = common.read_json(tileset)
        self.assertEqual(record["tiles"][FIRST_FRAME]["neighbours"], record["tiles"][BASE]["neighbours"])
        self.assertEqual(record["tiles"][FIRST_FRAME]["terrain"], record["tiles"][BASE]["terrain"])

    def test_a_frame_that_brings_its_own_labels_is_refused_not_ignored(self):
        job = self.animated_job()
        job["tiles"][FIRST_FRAME]["neighbours"] = job["tiles"][1]["neighbours"]
        with self.assertRaisesRegex(ValueError, "takes that tile's labels"):
            builder.build(job, self.out)

    def test_a_frame_that_is_not_in_the_set_is_refused_by_name(self):
        job = self.animated_job()
        job["animations"][0]["frames"][1]["tile"] = 40
        with self.assertRaisesRegex(ValueError, "frame tile 40 is not in the tileset"):
            builder.build(job, self.out)

    def test_an_extra_tile_that_no_animation_uses_must_carry_its_own_labels(self):
        job = self.animated_job()
        del job["animations"]
        with self.assertRaisesRegex(ValueError, "tile 16: top_right is None"):
            builder.build(job, self.out)

    def test_a_failed_build_leaves_nothing_behind(self):
        job = self.animated_job()
        job["animations"][0]["frames"][1]["tile"] = 40
        with self.assertRaises(ValueError):
            builder.build(job, self.out)
        self.assertEqual(list(self.out.glob("*")) if self.out.exists() else [], [])


class ValidatorTests(AnimatedBuildCase):
    def test_a_frame_whose_edge_does_not_match_the_tile_it_animates_is_named(self):
        def wrong_edge(labels, _k):
            opposite = {side: ("water" if terrain == "grass" else "grass") for side, terrain in labels.items()}
            return corner_art(opposite)

        _, _, tileset = builder.build(self.animated_job(draw_frame=wrong_edge), self.out)
        issues = validator.validate(tileset)
        self.assertTrue(any("do not line up" in issue and "tile 16" in issue for issue in issues), issues)


class ExportTests(AnimatedBuildCase):
    def export(self, tileset):
        written = exchange.export_tileset(tileset)
        return json.loads(written.read_text(encoding="utf-8"))

    def test_tiled_gets_each_animation_with_its_durations_in_milliseconds(self):
        _, _, tileset = builder.build(self.animated_job(durations=(120, 140, 160)), self.out)
        data = self.export(tileset)
        self.assertEqual(data["tiles"], [{"id": BASE, "animation": [{"tileid": 0, "duration": 120}, {"tileid": 16, "duration": 140}, {"tileid": 17, "duration": 160}]}])
        self.assertEqual(data["tilecount"], 18)

    def test_a_frame_is_not_given_a_wang_id_of_its_own(self):
        _, _, tileset = builder.build(self.animated_job(), self.out)
        wangtiles = self.export(tileset)["wangsets"][0]["wangtiles"]
        self.assertEqual(sorted(tile["tileid"] for tile in wangtiles), list(range(16)))

    def test_a_tileset_without_animations_has_no_tiles_entry(self):
        _, _, tileset = builder.build(self.job(), self.out)
        self.assertNotIn("tiles", self.export(tileset))


if __name__ == "__main__":
    unittest.main()
