"""Cut-out timing (plan P12.6): per-keyframe interpolation and easing, with today's bundles unchanged when neither is used."""
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

import gamearts_testkit  # noqa: F401  (puts scripts/ on sys.path)

import build_component_bundle as engine  # noqa: E402
import validate_component_bundle as bundle_validator  # noqa: E402
from test_component_bundle import ComponentTests  # noqa: E402

GOLDEN_BUNDLE = "a62cae8b8a485d15f0f3d0d2bbbc59e530cbd716dada671640c5605f25f22677"


def keys(*pairs, **options):
    """Position-only keyframes [(time, x), ...]; `options` applies to every key but the last."""
    result = [{"time": t, "position": [x, 0]} for t, x in pairs]
    for key in result[:-1]:
        key.update(options)
    return result


def x_at(track, t, **kwargs):
    return engine.animate(track, t, "test", **kwargs)["position"][0]


class UnchangedTests(unittest.TestCase):
    def test_a_job_without_curve_fields_builds_a_byte_identical_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = ComponentTests().fixture(root)
            out = engine.build(config, root / "generated" / config["name"], root)
            raw = (out / f"{config['name']}.bundle.json").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), GOLDEN_BUNDLE)

    def test_linear_is_the_default_and_the_midpoint_is_the_mean(self):
        track = keys((0, 0), (1, 10))
        self.assertEqual(x_at(track, 0.5), 5.0)
        self.assertEqual(x_at(keys((0, 0), (1, 10), interpolation="linear", easing="linear"), 0.5), 5.0)


class EasingTests(unittest.TestCase):
    def test_the_named_curves_at_known_points(self):
        cases = {"ease_in": {0.25: 0.0625, 0.5: 0.25, 0.75: 0.5625},
                 "ease_out": {0.25: 0.4375, 0.5: 0.75, 0.75: 0.9375},
                 "ease_in_out": {0.25: 0.125, 0.5: 0.5, 0.75: 0.875}}
        for name, points in cases.items():
            for u, expected in points.items():
                with self.subTest(name=name, u=u):
                    self.assertAlmostEqual(x_at(keys((0, 0), (1, 100), easing=name), u) / 100, expected, places=9)

    def test_every_curve_starts_and_ends_exactly_on_its_keys(self):
        for name in ("linear", "ease_in", "ease_out", "ease_in_out"):
            track = keys((0, 3), (0.5, 9), (1, 4), easing=name)
            self.assertEqual(x_at(track, 0), 3)
            self.assertEqual(x_at(track, 0.5), 9)
            self.assertEqual(x_at(track, 1), 4)

    def test_easing_belongs_to_the_segment_that_starts_at_its_key(self):
        track = [{"time": 0, "position": [0, 0], "easing": "ease_in"}, {"time": 0.5, "position": [10, 0]}, {"time": 1, "position": [20, 0]}]
        self.assertAlmostEqual(x_at(track, 0.25), 2.5)  # first segment eased: half-way in time is a quarter of the way in value
        self.assertAlmostEqual(x_at(track, 0.75), 15.0)  # second segment has none: linear

    def test_rotation_and_scale_ease_as_well(self):
        track = [{"time": 0, "rotation_degrees": 0, "scale": [1, 1], "easing": "ease_in"}, {"time": 1, "rotation_degrees": 90, "scale": [3, 3]}]
        pose = engine.animate(track, 0.5, "test")
        self.assertAlmostEqual(pose["rotation_degrees"], 22.5)
        self.assertAlmostEqual(pose["scale"][0], 1.5)


class NearestTests(unittest.TestCase):
    def test_a_stepped_segment_holds_its_value_until_the_next_key(self):
        track = keys((0, 0), (0.5, 10), (1, 20), interpolation="nearest")
        self.assertEqual(x_at(track, 0.25), 0)
        self.assertEqual(x_at(track, 0.4999), 0)
        self.assertEqual(x_at(track, 0.5), 10)
        self.assertEqual(x_at(track, 0.75), 10)
        self.assertEqual(x_at(track, 1), 20)

    def test_steps_and_smooth_segments_can_follow_each_other(self):
        track = [{"time": 0, "position": [0, 0], "interpolation": "nearest"}, {"time": 0.5, "position": [10, 0]}, {"time": 1, "position": [20, 0]}]
        self.assertEqual(x_at(track, 0.4), 0)
        self.assertEqual(x_at(track, 0.75), 15)

    def test_a_step_cannot_also_ease(self):
        with self.assertRaisesRegex(ValueError, "nearest.*ease"):
            x_at(keys((0, 0), (1, 10), interpolation="nearest", easing="ease_in"), 0.5)


class CubicTests(unittest.TestCase):
    def test_a_cubic_segment_passes_through_every_key(self):
        track = keys((0, 0), (0.25, 7), (0.6, -3), (1, 5), interpolation="cubic")
        for t, expected in ((0, 0), (0.25, 7), (0.6, -3), (1, 5)):
            self.assertAlmostEqual(x_at(track, t), expected, places=9)

    def test_evenly_spaced_straight_data_stays_straight(self):
        track = keys((0, 0), (0.25, 5), (0.5, 10), (0.75, 15), (1, 20), interpolation="cubic")
        for t in (0.1, 0.3, 0.55, 0.9):
            self.assertAlmostEqual(x_at(track, t), 20 * t, places=9)

    def test_two_keys_are_a_straight_line(self):
        self.assertAlmostEqual(x_at(keys((0, 0), (1, 10), interpolation="cubic"), 0.3), 3.0, places=9)

    def test_a_known_curve_at_a_known_time(self):
        # keys 0, 10, 0 at 0, 0.5, 1: the first segment uses the one-sided tangent 10 at its start and 0 at its end,
        # so half-way along it the value is 0.5*0 + 0.125*10 + 0.5*10 + (-0.125)*0 = 6.25 (a straight line would give 5).
        track = keys((0, 0), (0.5, 10), (1, 0), interpolation="cubic")
        self.assertAlmostEqual(x_at(track, 0.25), 6.25, places=9)

    def test_a_symmetric_hump_is_symmetric_so_the_key_before_a_segment_counts_as_much_as_the_key_after(self):
        track = keys((0, 0), (0.5, 10), (1, 0), interpolation="cubic")
        self.assertAlmostEqual(x_at(track, 0.75), 6.25, places=9)
        for t in (0.1, 0.2, 0.3, 0.4):
            self.assertAlmostEqual(x_at(track, t), x_at(track, 1 - t), places=9)

    def test_cubic_can_leave_the_straight_line_between_keys_where_linear_cannot(self):
        smooth = keys((0, 0), (0.5, 10), (1, 0), interpolation="cubic")
        straight = keys((0, 0), (0.5, 10), (1, 0))
        self.assertNotAlmostEqual(x_at(smooth, 0.25), x_at(straight, 0.25))

    def test_the_shortest_arc_is_followed_through_a_cubic_rotation(self):
        track = [{"time": 0, "rotation_degrees": 350, "interpolation": "cubic"}, {"time": 0.5, "rotation_degrees": 10, "interpolation": "cubic"},
                 {"time": 1, "rotation_degrees": 30}]
        around = engine.animate(track, 0.25, "test", rotation_mode="shortest")["rotation_degrees"]
        self.assertAlmostEqual(around, 360.0, places=9)  # 350 -> 370 -> 390 is a straight run, so the quarter point is 360
        direct = engine.animate(track, 0.25, "test")["rotation_degrees"]
        self.assertNotAlmostEqual(direct, 360.0)  # without shortest, 350 -> 10 swings backwards through 180


class ValidationTests(unittest.TestCase):
    def test_an_unknown_easing_or_interpolation_names_itself_and_the_choices(self):
        with self.assertRaisesRegex(ValueError, "easing 'bouncy'.*ease_in_out"):
            x_at(keys((0, 0), (1, 10), easing="bouncy"), 0.5)
        with self.assertRaisesRegex(ValueError, "interpolation 'spline'.*cubic"):
            x_at(keys((0, 0), (1, 10), interpolation="spline"), 0.5)

    def test_curve_fields_on_the_last_keyframe_are_refused_because_nothing_follows_it(self):
        track = keys((0, 0), (1, 10))
        track[-1]["easing"] = "ease_in"
        with self.assertRaisesRegex(ValueError, "last keyframe.*no segment"):
            x_at(track, 0.5)

    def test_a_bad_curve_is_found_by_the_track_check_without_sampling_the_track(self):
        bad = keys((0, 0), (1, 10), easing="bouncy")
        with self.assertRaisesRegex(ValueError, "easing 'bouncy'"):
            engine.check_tracks({"default": {"*": bad}}, "default", ["S", "E"], "motion_tracks")

    def test_a_bad_curve_stops_a_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = ComponentTests().fixture(root)
            config["components"][2]["motion_tracks"]["default"]["*"][0]["easing"] = "bouncy"
            with self.assertRaisesRegex(ValueError, "easing 'bouncy'"):
                engine.build(config, root / "generated" / config["name"], root)


class BundleTests(unittest.TestCase):
    def poses(self, **first_key):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = ComponentTests().fixture(root)
            config["components"][2]["motion_tracks"]["default"]["*"][0].update(first_key)
            out = engine.build(config, root / "generated" / config["name"], root)
            data = json.loads((out / f"{config['name']}.bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle_validator.validate(out), [])
            return data

    @staticmethod
    def tip_position(data, direction, time):
        pose = next(p for p in data["sampled_poses"] if p["direction"] == direction and p["normalized_time"] == time)
        matrix = pose["nodes"]["tip"]["world_matrix_2d"]
        return matrix[0][2], matrix[1][2]

    def test_sampled_poses_honor_easing_so_they_stay_the_numeric_reference(self):
        plain, eased = self.poses(), self.poses(easing="ease_in")
        (px, py), (ex, ey) = self.tip_position(plain, "S", 0.5), self.tip_position(eased, "S", 0.5)
        # the tip's own motion goes 0 -> 1 along the joint's x axis; at half time linear is 0.5 and ease_in is 0.25, and the joint is turned 45 degrees there
        self.assertAlmostEqual(ex - px, -0.25 * math.cos(math.radians(45)), places=6)
        self.assertAlmostEqual(ey - py, -0.25 * math.sin(math.radians(45)), places=6)

    def test_the_curve_fields_travel_with_the_tracks_into_the_bundle_file(self):
        data = self.poses(easing="ease_in", interpolation="cubic")
        track = next(c for c in data["components"] if c["id"] == "tip")["motion_tracks"]["default"]["*"]
        self.assertEqual((track[0]["easing"], track[0]["interpolation"]), ("ease_in", "cubic"))

    def test_the_end_poses_do_not_depend_on_the_curve(self):
        plain, eased = self.poses(), self.poses(easing="ease_in_out")
        for time in (0, 1):
            self.assertEqual(self.tip_position(plain, "E", time), self.tip_position(eased, "E", time))


if __name__ == "__main__":
    unittest.main()
