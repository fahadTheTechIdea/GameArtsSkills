"""Animation checks (plan P11.6): loop seam, pivot drift and clipping, measured from a sheet and its atlas."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit as kit

import check_animation as animation  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_animation.py"
KEY = (255, 0, 255, 255)


def frame(x, bottom=14, size=(24, 16), ink=(40, 90, 160, 255), width=4, height=4):
    """A key-colour frame with a small block whose left edge is at `x` and whose bottom row is `bottom`."""
    image = Image.new("RGBA", size, KEY)
    for yy in range(bottom - height + 1, bottom + 1):
        for xx in range(x, x + width):
            if 0 <= xx < size[0] and 0 <= yy < size[1]:
                image.putpixel((xx, yy), ink)
    return image


def build(folder, frames, action="walk", direction="E", durations=None, name="anim_sheet", pivot=(12, 15)):
    """Build a real sheet and atlas from `frames`; returns (sheet path, atlas path)."""
    with tempfile.TemporaryDirectory() as source:
        items = []
        for index, image in enumerate(frames):
            image.save(Path(source) / f"f{index}.png")
            item = {"file": f"f{index}.png", "name": f"{action}_{index}", "direction": direction, "action": action, "pivot": list(pivot)}
            if durations:
                item["duration_ms"] = durations[index]
            items.append(item)
        kit.build_sheet({"_input_dir": source, "name": name, "asset_id": "anim", "columns": len(frames), "padding": 2, "frames": items}, Path(folder))
    return Path(folder) / f"{name}.png", Path(folder) / f"{name}.atlas.json"


class AnimationCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def results(self, frames, params=None, **kwargs):
        sheet, atlas = build(self.root, frames, **kwargs)
        report = animation.check_sheet(sheet, atlas, params or {})
        self.assertEqual(len(report["animations"]), 1, report)
        return {item["name"]: item for item in report["animations"][0]["checks"]}, report


class LoopSeamTests(AnimationCase):
    def test_a_cycle_that_returns_to_where_it_began_passes(self):
        checks, _ = self.results([frame(x) for x in (2, 3, 4, 5, 4, 3)])
        self.assertEqual(checks["loop_seam"]["status"], "passed", checks["loop_seam"])
        self.assertLessEqual(checks["loop_seam"]["measured"]["ratio"], 1.5)

    def test_a_run_that_jumps_back_at_the_end_fails_with_the_measured_ratio(self):
        checks, _ = self.results([frame(x) for x in (2, 3, 4, 5, 6, 7)])
        self.assertEqual(checks["loop_seam"]["status"], "failed")
        self.assertGreater(checks["loop_seam"]["measured"]["ratio"], 3)

    def test_the_limit_comes_from_the_games_parameters(self):
        frames = [frame(x) for x in (2, 3, 4, 5, 6, 7)]
        checks, _ = self.results(frames, {"loop_seam": {"max_ratio": 99}})
        self.assertEqual(checks["loop_seam"]["status"], "passed")

    def test_fewer_than_three_frames_cannot_be_judged(self):
        checks, _ = self.results([frame(2), frame(4)])
        self.assertEqual(checks["loop_seam"]["status"], "untested")
        self.assertIn("least 3", checks["loop_seam"]["detail"])

    def test_identical_frames_are_reported_instead_of_dividing_by_zero(self):
        checks, report = self.results([frame(2)] * 4)
        self.assertEqual(checks["loop_seam"]["status"], "untested")
        self.assertIn("identical", checks["loop_seam"]["detail"])
        self.assertEqual(report["animations"][0]["duplicate_frames"], ["walk_1", "walk_2", "walk_3"])


class PivotDriftTests(AnimationCase):
    def test_feet_that_stay_on_the_line_pass(self):
        checks, _ = self.results([frame(x) for x in (2, 4, 6, 8)])
        self.assertEqual(checks["pivot_drift"]["status"], "passed")
        self.assertEqual(checks["pivot_drift"]["measured"]["drift_px"], 0)

    def test_a_frame_whose_feet_sit_lower_fails(self):
        checks, _ = self.results([frame(2), frame(4), frame(6, bottom=14 - 5), frame(8)])
        self.assertEqual(checks["pivot_drift"]["status"], "failed")
        self.assertEqual(checks["pivot_drift"]["measured"]["drift_px"], 5)

    def test_a_small_drift_within_the_limit_passes(self):
        checks, _ = self.results([frame(2), frame(4, bottom=13), frame(6)], {"pivot_drift": {"max_px": 2}})
        self.assertEqual(checks["pivot_drift"]["status"], "passed")


class ClippingTests(AnimationCase):
    def test_art_that_touches_the_edge_of_its_source_frame_is_reported(self):
        checks, _ = self.results([frame(2), frame(0), frame(6)])
        self.assertEqual(checks["clipping"]["status"], "failed")
        self.assertEqual(checks["clipping"]["measured"]["frames"], ["walk_1"])

    def test_art_clear_of_the_edge_passes(self):
        checks, _ = self.results([frame(2), frame(4), frame(6)])
        self.assertEqual(checks["clipping"]["status"], "passed")


class GroupingTests(AnimationCase):
    def test_frames_are_grouped_by_action_and_direction(self):
        sheet_a, atlas_a = build(self.root, [frame(2), frame(4), frame(6)], action="walk", direction="E", name="walk_e")
        report = animation.check_sheet(sheet_a, atlas_a, {})
        self.assertEqual([(g["action"], g["direction"], g["frames"]) for g in report["animations"]], [("walk", "E", 3)])

    def test_a_sheet_with_two_actions_gives_two_animations(self):
        with tempfile.TemporaryDirectory() as source:
            items = []
            for index, (action, x) in enumerate((("walk", 2), ("walk", 4), ("walk", 6), ("jump", 2), ("jump", 6), ("jump", 10))):
                frame(x).save(Path(source) / f"f{index}.png")
                items.append({"file": f"f{index}.png", "name": f"{action}_{index}", "direction": "E", "action": action, "pivot": [12, 15]})
            kit.build_sheet({"_input_dir": source, "name": "two", "asset_id": "a", "columns": 3, "padding": 2, "frames": items}, self.root)
        report = animation.check_sheet(self.root / "two.png", self.root / "two.atlas.json", {})
        self.assertEqual(sorted(g["action"] for g in report["animations"]), ["jump", "walk"])

    def test_frames_with_no_action_are_one_animation_in_atlas_order(self):
        with tempfile.TemporaryDirectory() as source:
            items = []
            for index, x in enumerate((2, 4, 6)):
                frame(x).save(Path(source) / f"f{index}.png")
                items.append({"file": f"f{index}.png", "name": f"f{index}", "pivot": [12, 15]})
            kit.build_sheet({"_input_dir": source, "name": "plain", "asset_id": "a", "columns": 3, "padding": 2, "frames": items}, self.root)
        report = animation.check_sheet(self.root / "plain.png", self.root / "plain.atlas.json", {})
        self.assertEqual(len(report["animations"]), 1)
        self.assertIsNone(report["animations"][0]["action"])

    def test_the_total_duration_is_reported_from_the_atlas(self):
        _, report = self.results([frame(x) for x in (2, 4, 6)], durations=[100, 150, 250])
        self.assertEqual(report["animations"][0]["duration_ms"], 500)

    def test_the_report_names_what_it_did_not_assess(self):
        _, report = self.results([frame(x) for x in (2, 4, 6)])
        joined = " ".join(report["not_assessed"])
        self.assertIn("whether the motion looks right", joined)


class RegistryTests(unittest.TestCase):
    def test_the_check_names_are_the_ones_the_presets_can_require(self):
        schema = json.loads((ROOT / "schemas" / "gamearts-style-preset.schema.json").read_text(encoding="utf-8"))
        allowed = set(schema["properties"]["required_checks"]["items"]["enum"])
        self.assertLessEqual(set(animation.CHECK_NAMES), allowed)

    def test_an_unknown_check_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unknown animation check"):
            animation.check_sheet(Path("x"), Path("y"), {}, names=["sparkle"])


class CommandLineTests(AnimationCase):
    def test_the_command_prints_json_and_fails_on_a_failed_check(self):
        sheet, atlas = build(self.root, [frame(x) for x in (2, 3, 4, 5, 6, 7)])
        done = subprocess.run([sys.executable, str(SCRIPT), "--image", str(sheet), "--atlas", str(atlas)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "failed")

    def test_the_command_exits_zero_when_everything_passes(self):
        sheet, atlas = build(self.root, [frame(x) for x in (2, 3, 4, 5, 4, 3)])
        done = subprocess.run([sys.executable, str(SCRIPT), "--image", str(sheet), "--atlas", str(atlas)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
