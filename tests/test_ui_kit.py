"""UI kit metadata (plan P12.2): nine-slice margins, the full state set of a control, and icon sets that share a size."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit  # noqa: F401  (puts scripts/ on sys.path)

import build_sheet_atlas as builder  # noqa: E402
import gamearts_atlas as rules  # noqa: E402
import validate_sheet_atlas as validator  # noqa: E402

KEY = (255, 0, 255, 255)
STATES = ["normal", "hover", "pressed", "disabled"]


def frame(name, size=(24, 16), control=None, state=None, nine=None, group=None, offset=(2, 2)):
    entry = {"index": 0, "name": name, "rect": [0, 0, size[0] + 4, size[1] + 4], "pivot": [0, 0], "anchors": {}, "duration_ms": 100,
             "source_size": list(size), "source_offset_in_cell": list(offset)}
    for key, value in (("control", control), ("state", state), ("nine_slice", nine), ("set", group)):
        if value is not None:
            entry[key] = value
    return entry


def atlas_of(frames, controls=None):
    for index, entry in enumerate(frames):
        entry["index"] = index
    result = {"frames": frames}
    if controls is not None:
        result["controls"] = controls
    return result


def button_kit(**changes):
    frames = [frame(f"button_{s}", control="button", state=s, nine=[6, 6, 6, 6]) for s in STATES]
    return atlas_of(frames, [{"name": "button", "states": list(STATES)}])


class RuleTests(unittest.TestCase):
    def test_a_complete_button_kit_has_no_problems(self):
        self.assertEqual(rules.ui_problems(button_kit()), [])

    def test_an_atlas_with_no_ui_fields_has_no_problems(self):
        self.assertEqual(rules.ui_problems(atlas_of([frame("a"), frame("b")])), [])

    def test_margins_that_leave_no_centre_are_named(self):
        for nine, expected in (([12, 2, 12, 2], "left + right"), ([2, 8, 2, 8], "top + bottom"), ([30, 1, 1, 1], "left + right")):
            with self.subTest(nine):
                problems = rules.ui_problems(atlas_of([frame("panel", nine=nine)]))
                self.assertTrue(any("panel" in p and expected in p for p in problems), problems)

    def test_zero_margins_are_allowed_and_negative_or_fractional_ones_are_not(self):
        self.assertEqual(rules.ui_problems(atlas_of([frame("panel", nine=[0, 0, 0, 0])])), [])
        for nine in ([-1, 2, 2, 2], [1.5, 2, 2, 2], [1, 2, 2], "6"):
            with self.subTest(nine):
                self.assertTrue(rules.ui_problems(atlas_of([frame("panel", nine=nine)])))

    def test_a_trimmed_nine_slice_frame_is_refused_because_its_margins_are_measured_from_the_whole_frame(self):
        entry = frame("panel", nine=[4, 4, 4, 4])
        entry["trimmed"] = True
        self.assertTrue(any("trimmed" in p for p in rules.ui_problems(atlas_of([entry]))))

    def test_a_missing_state_is_named_with_its_control(self):
        kit_ = button_kit()
        kit_["frames"] = [f for f in kit_["frames"] if f["state"] != "pressed"]
        problems = rules.ui_problems(kit_)
        self.assertTrue(any("button" in p and "pressed" in p and "no frame" in p for p in problems), problems)

    def test_a_control_must_declare_a_normal_state(self):
        frames = [frame("b_hover", control="b", state="hover")]
        problems = rules.ui_problems(atlas_of(frames, [{"name": "b", "states": ["hover"]}]))
        self.assertTrue(any("normal" in p for p in problems), problems)

    def test_a_frame_with_an_undeclared_control_or_state_is_named(self):
        frames = [frame("x", control="ghost", state="normal")]
        self.assertTrue(any("ghost" in p and "not declared" in p for p in rules.ui_problems(atlas_of(frames, []))))
        kit_ = button_kit()
        kit_["controls"][0]["states"] = ["normal", "hover", "pressed"]
        self.assertTrue(any("disabled" in p and "not declared" in p for p in rules.ui_problems(kit_)))

    def test_a_declared_control_with_no_frames_is_named(self):
        problems = rules.ui_problems(atlas_of([frame("a")], [{"name": "slider", "states": ["normal"]}]))
        self.assertTrue(any("slider" in p and "no frames" in p for p in problems), problems)

    def test_a_state_needs_a_control_and_a_control_needs_a_state(self):
        self.assertTrue(any("state" in p and "control" in p for p in rules.ui_problems(atlas_of([frame("a", state="normal")]))))
        self.assertTrue(any("control" in p and "state" in p for p in rules.ui_problems(atlas_of([frame("a", control="c")], [{"name": "c", "states": ["normal"]}]))))

    def test_two_frames_for_one_state_are_named(self):
        kit_ = button_kit()
        kit_["frames"].append(frame("button_normal_again", control="button", state="normal", nine=[6, 6, 6, 6]))
        self.assertTrue(any("button" in p and "normal" in p and "twice" in p for p in rules.ui_problems(kit_)))

    def test_states_of_one_control_must_share_size_and_margins(self):
        kit_ = button_kit()
        kit_["frames"][1]["source_size"] = [26, 16]
        self.assertTrue(any("button_hover" in p and "size" in p for p in rules.ui_problems(kit_)))
        kit_ = button_kit()
        kit_["frames"][2]["nine_slice"] = [5, 6, 6, 6]
        self.assertTrue(any("button_pressed" in p and "nine_slice" in p for p in rules.ui_problems(kit_)))

    def test_an_icon_set_shares_one_size_and_one_padding(self):
        icons = [frame("save", (16, 16), group="icons"), frame("load", (16, 16), group="icons"), frame("quit", (16, 16), group="icons")]
        self.assertEqual(rules.ui_problems(atlas_of(icons)), [])
        icons[1]["source_size"] = [20, 16]
        self.assertTrue(any("icons" in p and "load" in p and "size" in p for p in rules.ui_problems(atlas_of(icons))))
        icons[1]["source_size"] = [16, 16]
        icons[2]["source_offset_in_cell"] = [3, 2]
        self.assertTrue(any("icons" in p and "quit" in p and "padding" in p for p in rules.ui_problems(atlas_of(icons))))

    def test_the_states_are_the_ones_ui_toolkits_name(self):
        self.assertEqual(rules.UI_STATES, ("normal", "hover", "pressed", "disabled", "focus"))


class BuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def picture(self, name, size, fill):
        image = Image.new("RGBA", size, KEY)
        for y in range(2, size[1] - 2):
            for x in range(2, size[0] - 2):
                image.putpixel((x, y), fill)
        image.save(self.src / name)

    def job(self, drop=(), **overrides):
        frames = []
        for index, state in enumerate(STATES):
            self.picture(f"button_{state}.png", (24, 16), (40 + 40 * index, 90, 160, 255))
            frames.append({"file": f"button_{state}.png", "name": f"button_{state}", "control": "button", "state": state, "nine_slice": [6, 6, 6, 6], "pivot": [0, 0]})
        for name in ("save", "load"):
            self.picture(f"{name}.png", (16, 16), (200, 160, 40, 255))
            frames.append({"file": f"{name}.png", "name": name, "set": "icons", "pivot": [0, 0]})
        job = {"_input_dir": str(self.src), "name": "ui", "asset_id": "ui", "padding": 2, "columns": 3, "frames": frames,
               "controls": [{"name": "button", "states": list(STATES)}]}
        job.update(overrides)
        for key in drop:
            del job[key]
        return job

    def build(self, **overrides):
        png, atlas = builder.build(self.job(**overrides), self.root / "out")
        return png, json.loads(atlas.read_text(encoding="utf-8")), atlas


class BuildTests(BuildCase):
    def test_the_ui_fields_reach_the_atlas_and_the_sheet_validates(self):
        png, atlas, path = self.build()
        by_name = {f["name"]: f for f in atlas["frames"]}
        self.assertEqual(by_name["button_hover"]["state"], "hover")
        self.assertEqual(by_name["button_hover"]["control"], "button")
        self.assertEqual(by_name["button_hover"]["nine_slice"], [6, 6, 6, 6])
        self.assertEqual(by_name["save"]["set"], "icons")
        self.assertEqual(atlas["controls"], [{"name": "button", "states": STATES}])
        self.assertEqual(validator.validate(png, path), [])

    def test_a_frame_without_ui_fields_gets_none(self):
        self.picture("plain.png", (10, 10), (1, 2, 3, 255))
        _, atlas, _ = self.build(drop=("controls", "columns"), frames=[{"file": "plain.png", "name": "plain"}])
        self.assertNotIn("controls", atlas)
        for key in ("nine_slice", "state", "control", "set"):
            self.assertNotIn(key, atlas["frames"][0])

    def test_a_missing_state_stops_the_build_and_names_it(self):
        job = self.job()
        job["frames"] = [f for f in job["frames"] if f.get("state") != "disabled"]
        with self.assertRaisesRegex(ValueError, "button.*disabled.*no frame"):
            builder.build(job, self.root / "out")
        self.assertFalse((self.root / "out").exists() and any((self.root / "out").iterdir()))

    def test_margins_larger_than_the_frame_stop_the_build(self):
        job = self.job()
        job["frames"][0]["nine_slice"] = [14, 6, 14, 6]
        with self.assertRaisesRegex(ValueError, "button_normal.*left \\+ right"):
            builder.build(job, self.root / "out")

    def test_a_nine_slice_frame_keeps_every_pixel_even_when_the_sheet_is_trimmed(self):
        png, atlas, path = self.build(drop=("columns",), trim=True, pack="shelf")
        by_name = {f["name"]: f for f in atlas["frames"]}
        self.assertFalse(by_name["button_normal"]["trimmed"])
        self.assertEqual(by_name["button_normal"]["trim"], [0, 0, 24, 16])
        self.assertTrue(by_name["save"]["trimmed"])
        self.assertEqual(validator.validate(png, path), [])

    def test_the_validator_catches_a_state_removed_from_a_finished_atlas(self):
        png, atlas, path = self.build()
        atlas["frames"] = [f for f in atlas["frames"] if f.get("state") != "hover"]
        for index, entry in enumerate(atlas["frames"]):
            entry["index"] = index
        path.write_text(json.dumps(atlas), encoding="utf-8")
        self.assertTrue(any("hover" in issue and "button" in issue for issue in validator.validate(png, path)))

    def test_a_state_the_schema_does_not_know_is_refused(self):
        job = self.job()
        job["frames"][1]["state"] = "hovering"
        with self.assertRaises(ValueError):
            builder.build(job, self.root / "out")


if __name__ == "__main__":
    unittest.main()
