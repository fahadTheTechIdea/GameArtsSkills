"""Tests for the directional prompt packets (scripts/gamearts_direction_prompt.py): build, turnaround, plan, inbetween, repair, respace and fix."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gamearts_testkit import write_settings

import gamearts_direction_prompt as dp

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_direction_prompt.py"
FACINGS = {"S": "SOUTH", "SW": "SOUTHWEST", "W": "WEST", "NW": "NORTHWEST", "N": "NORTH", "NE": "NORTHEAST", "E": "EAST", "SE": "SOUTHEAST"}


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def world(profile, camera):
    return {"grid": "orthogonal_square", "camera_profile": profile, "object_camera": camera, "logical_tile_m": [1, 1], "ground_tile_px": [64, 64], "pixels_per_meter": 64, "construction_snap_m": 1}


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "game"
        self.root.mkdir()
        write_settings(self.root)
        for name in ("turnaround.png", "e_neutral.png", "clap_timeline.png", "strip.png", "keys.png"):
            Image.new("RGBA", (64, 32), (10, 20, 30, 255)).save(self.root / name)

    def settings(self, **overrides):
        write_settings(self.root, **overrides)

    def build(self, facing="E", frames=8, **more):
        more.setdefault("kind", "vehicle")
        return dp.build(self.root, facing, frames, more.pop("action", "clap"), **more)

    def blocked(self, result, text):
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stderr, "BLOCKED")
        self.assertRegex(result.stderr, text)
        self.assertEqual(result.stdout, "")

    def cli(self, *args):
        result = run(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)


class KindTests(Case):
    """Each kind of subject shows different parts from each facing, so each has its own words and none is guessed."""

    PARTS = {
        "human": {"S": "the whole face and front of the body show", "N": "show ONLY the back of the head, the back of the body and the heels", "E": "both feet pointing screen right", "SE": "NOT horizontally to the right"},
        "animal": {"S": "its FRONT (the face, the chest and both front legs) faces the camera", "N": "only its REAR (the tail, the hindquarters", "E": "the head toward screen RIGHT", "SE": "FRONT (the face, the chest and both front legs) shows on the screen-right part"},
        "vehicle": {"S": "its FRONT (the grille, the headlights", "N": "only its REAR (the rear lights, the rear doors or tailgate", "E": "both wheels on that side) flat to the camera, the front toward screen RIGHT", "SE": "FRONT (the grille, the headlights, the windscreen and the bonnet) shows on the screen-right part"},
        "building": {"S": "its main FRONT facade with the entrance faces the camera", "N": "only its BACK wall shows", "E": "the front facade at the RIGHT end of it", "SE": "main FRONT facade with the entrance shows on the screen-right part"},
        "structure": {"S": "its long axis points straight TOWARD the viewer", "N": "its long axis points straight AWAY from the viewer", "E": "its long axis runs left-right across the screen", "SE": "the near END face shows at the lower right"},
        "plant": {"S": "its chosen FRONT side faces the viewer", "N": "its BACK side faces the viewer", "E": "its right-hand side faces the viewer in profile", "SE": "its front-right side faces the viewer"},
    }

    def test_every_kind_has_all_eight_facings_in_its_own_words(self):
        self.assertEqual(set(self.PARTS), set(dp.KINDS))
        for kind, wanted in self.PARTS.items():
            table = dp.facings_for(kind)
            self.assertEqual(set(table), set(FACINGS))
            for facing, words in wanted.items():
                with self.subTest(kind=kind, facing=facing):
                    self.assertIn(words, table[facing])
                    self.assertIn(words, self.build(facing, kind=kind)["prompt"])
            with self.subTest(kind=kind, check="all eight differ"):
                self.assertEqual(len(set(table.values())), 8)

    def test_no_two_kinds_share_the_words_for_a_facing(self):
        for facing in FACINGS:
            with self.subTest(facing=facing):
                self.assertEqual(len({dp.facings_for(kind)[facing] for kind in dp.KINDS}), len(dp.KINDS))

    def test_every_sentence_starts_with_a_capital(self):
        import re
        for kind in dp.KINDS:
            for facing, text in dp.facings_for(kind).items():
                with self.subTest(kind=kind, facing=facing):
                    self.assertIsNone(re.search(r"[.!] [a-z]", text), text)

    def test_a_kind_never_borrows_another_kinds_parts(self):
        for kind, forbidden in (("vehicle", "the tail"), ("vehicle", "the face"), ("animal", "the grille"), ("building", "wheels"), ("plant", "the face"), ("structure", "the face")):
            with self.subTest(kind=kind, forbidden=forbidden):
                self.assertNotIn(forbidden, " ".join(dp.facings_for(kind).values()))

    def test_the_kind_is_never_guessed(self):
        with self.assertRaisesRegex(ValueError, "say what kind of subject this is, because each shows different parts from each facing: human \\(a person or humanoid\\), animal"):
            dp.build(self.root, "E", 8, "clap")
        with self.assertRaisesRegex(ValueError, "say what kind of subject"):
            dp.build(self.root, "E", 8, "clap", kind="robot")
        for command in (("build", "--facing", "E", "--frames", 8, "--action", "x"), ("turnaround", "--subject", "x"), ("inbetween", "--facing", "E", "--keyposes", "keys.png", "--keyframes", 4, "--action", "x"),
                        ("repair", "--facing", "SE", "--target", "strip.png", "--turnaround", "turnaround.png", "--problem", "x", "--degrees", 35, "--turn", "toward-viewer")):
            with self.subTest(command=command[0]):
                result = run(command[0], "--game-root", self.root, *command[1:])
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("--kind", result.stderr)
        self.assertEqual(run("build", "--game-root", self.root, "--facing", "E", "--frames", 8, "--action", "x", "--kind", "robot").returncode, 2)

    def test_a_side_camera_gives_every_kind_only_its_two_sides_and_no_top(self):
        self.settings(world=world("side", "side-view orthographic"), directions=["E", "W", "N"])
        for kind in dp.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(set(dp.Game(self.root, kind).facings), {"E", "W"})
                with self.assertRaisesRegex(ValueError, "a side camera has no N facing here"):
                    self.build("N", kind=kind)
        self.assertIn("No top surface shows.", self.build("E", kind="building")["prompt"])
        self.assertNotIn("from the elevated camera", self.build("E", kind="vehicle")["prompt"])

    def test_only_a_subject_with_a_head_is_judged_by_its_head_width(self):
        for kind in dp.KINDS:
            packet = self.build("E", kind=kind, turnaround="turnaround.png", facing_reference="e_neutral.png")
            has_head = kind in ("human", "animal")
            with self.subTest(kind=kind):
                self.assertEqual("--crown 30" in packet["slice"], has_head)
                self.assertEqual("Keep the head the same size in every frame, not the posed bounding box" in packet["prompt"], has_head)
                self.assertEqual("Keep the whole subject the same size in every frame" in packet["prompt"], not has_head)
                self.assertEqual(any("validated on an upright human" in note for note in packet["not_assessed"]), kind == "animal")
        inbetween = dp.inbetween(self.root, "E", "keys.png", 4, "run", kind="vehicle")["prompt"]
        self.assertIn("Keep the whole subject the same size in every frame", inbetween)
        self.assertIn("Keep the head the same size in every frame", dp.inbetween(self.root, "E", "keys.png", 4, "run", kind="human")["prompt"])

    def test_an_elevated_camera_adds_the_top_of_each_kind(self):
        self.assertIn("Its roof shows from the elevated camera.", self.build("E", kind="vehicle")["prompt"])
        self.assertIn("Its back shows from the elevated camera.", self.build("E", kind="animal")["prompt"])
        self.assertIn("The top of the crown shows from the elevated camera.", self.build("E", kind="plant")["prompt"])


class BuildTests(Case):
    ANCHORS = {"turnaround": "turnaround.png", "turnaround_view_text": "bottom row, third figure", "facing_reference": "e_neutral.png", "timeline_reference": "clap_timeline.png"}

    def test_every_anchor_is_attached_in_order_and_given_its_job(self):
        packet = self.build("E", subject="a green tanker truck", **self.ANCHORS)
        self.assertEqual([(r["role"], r["path"]) for r in packet["references"]], [("turnaround", "turnaround.png"), ("facing", "e_neutral.png"), ("timeline", "clap_timeline.png")])
        self.assertTrue(all(len(r["sha256"]) == 64 for r in packet["references"]))
        prompt = packet["prompt"]
        self.assertIn("Input 1 is the APPROVED turnaround", prompt)
        self.assertIn("Match bottom row, third figure of it exactly", prompt)
        self.assertIn("Input 2 is the approved neutral picture of THIS facing", prompt)
        self.assertRegex(prompt, r"Input 3 is ONLY the approved action timeline.*Do NOT inherit its camera or facing")
        self.assertIn("a green tanker truck doing clap", prompt)
        self.assertEqual(packet["warnings"], [])

    def test_the_view_of_the_turnaround_is_named_from_the_arrangement_the_turnaround_command_asks_for(self):
        expected = {"E": "the top row, first figure", "NE": "the top row, second figure", "N": "the top row, third figure", "NW": "the top row, fourth figure",
                    "W": "the bottom row, first figure", "SW": "the bottom row, second figure", "S": "the bottom row, third figure", "SE": "the bottom row, fourth figure"}
        for facing, words in expected.items():
            with self.subTest(facing=facing):
                self.assertIn(f"Match {words} of it exactly", self.build(facing, turnaround="turnaround.png", turnaround_view_text="auto")["prompt"])

    def test_the_facing_is_worded_and_the_action_may_never_turn_it(self):
        for facing, word in FACINGS.items():
            with self.subTest(facing=facing):
                prompt = self.build(facing)["prompt"]
                self.assertIn("FACING FOR THIS ENTIRE SHEET: " + word, prompt)
                self.assertIn("Keep this facing throughout; an action must never turn into a different viewing direction.", prompt)

    def test_the_saved_camera_is_repeated_and_never_isometric(self):
        prompt = self.build("SE")["prompt"]
        self.assertIn("CAMERA: elevated orthographic oblique.", prompt)
        self.assertIn("THE CAMERA NEVER MOVES; only the subject turns", prompt)
        self.assertIn("NEVER an isometric or diamond view", prompt)

    def test_a_grid_uses_the_canvas_an_image_tool_returns_and_states_the_numbers_twice(self):
        packet = self.build("E", 8)
        layout = packet["layout"]
        self.assertEqual({k: v for k, v in layout.items() if k != "note"}, {"frames": 8, "columns": 4, "rows": 2, "canvas": [1536, 1024], "cell": [384, 512], "neutral_height": 358, "ground_line": 456, "gutter": 46})
        prompt = packet["prompt"]
        self.assertIn("EXACTLY 8 complete figures, in 2 rows of 4", prompt)
        self.assertIn("The canvas is 1536x1024 pixels: equal invisible cells about 384x512", prompt)
        self.assertIn("at least 46 pixels (12% of the cell width)", prompt)
        self.assertIn("about 358 pixels tall (70% of the cell height)", prompt)
        self.assertIn("the line 456 pixels (89%) below the top of each cell", prompt)
        self.assertIn("Never resize a figure between frames", prompt)
        self.assertIn("Keep the whole subject the same size in every frame", prompt)

    def test_a_short_strip_uses_the_wide_canvas_and_a_long_cycle_uses_a_grid_of_at_most_six_a_row(self):
        short = self.build("E", 4)["layout"]
        self.assertEqual((short["canvas"], short["cell"], short["rows"]), ([2172, 724], [543, 724], 1))
        self.assertIn("in ONE horizontal row", self.build("E", 4)["prompt"])
        long = self.build("E", 18)["layout"]
        self.assertEqual((long["canvas"], long["cell"], long["rows"], long["columns"]), ([1536, 1024], [256, 341], 3, 6))
        self.assertEqual(self.build("E", 6)["layout"]["columns"], 6)

    def test_a_count_that_cannot_be_laid_out_in_rows_is_refused(self):
        with self.assertRaisesRegex(ValueError, "7 frames do not divide into rows of 2 to 6"):
            self.build("E", 7)
        with self.assertRaisesRegex(ValueError, "8 frames do not fit 3 columns"):
            self.build("E", 8, columns=3)

    def test_a_size_the_tool_was_not_seen_to_return_and_a_crowded_row_are_warned_about(self):
        odd = "\n".join(self.build("E", 4, canvas=(1536, 320))["warnings"])
        self.assertIn("1536x320 is not a size an image tool was seen to return", odd)
        crowded = "\n".join(self.build("E", 8, columns=8)["warnings"])
        self.assertIn("8 figures in one row came back clipped", crowded)
        self.assertNotIn("not a size", crowded)

    def test_the_neutral_height_and_ground_line_can_be_set_and_must_be_consistent(self):
        self.assertIn("about 300 pixels tall (59% of the cell height)", self.build("E", 8, neutral_height=300, ground_line=450)["prompt"])
        with self.assertRaisesRegex(ValueError, "must be above the ground line"):
            self.build("E", 8, neutral_height=480, ground_line=450)

    def test_a_loop_returns_to_the_neutral_pose_closes_as_a_cycle_or_is_neither(self):
        neutral = self.build("E", **self.ANCHORS)["prompt"]
        self.assertIn("The FIRST and LAST figures are identical copies of the approved neutral pose", neutral)
        cycle = self.build("E", loop="cycle")["prompt"]
        self.assertIn("ONE seamless cycle sampled at 8 equally spaced successive phases", cycle)
        self.assertIn("the end point is NOT duplicated", cycle)
        self.assertNotIn("FIRST and LAST", cycle)
        none = self.build("E", loop="none")["prompt"]
        self.assertNotIn("FIRST and LAST", none)
        self.assertNotIn("seamless cycle", none)
        with self.assertRaisesRegex(ValueError, "loop must be one of"):
            self.build("E", loop="forever")

    def test_a_walker_alternates_its_legs_with_a_near_and_a_far_limb(self):
        prompt = self.build("E", kind="human", loop="cycle", paired_limbs=True)["prompt"]
        self.assertIn("Alternate the leading leg and the opposite arm", prompt)
        self.assertIn("NEAR leg and the other the FAR leg", prompt)
        self.assertIn("far-side limbs are very slightly darker", prompt)
        self.assertNotIn("NEAR leg", self.build("E", kind="human")["prompt"])

    def test_every_frame_can_be_described_in_order(self):
        poses = [f"pose number {n}" for n in range(1, 9)]
        prompt = self.build("E", poses=poses)["prompt"]
        self.assertIn("THE POSES, in reading order: (1) pose number 1 (2) pose number 2", prompt)
        self.assertIn("(8) pose number 8", prompt)
        with self.assertRaisesRegex(ValueError, "3 poses were given for 8 frames"):
            self.build("E", poses=poses[:3])

    def test_the_background_follows_the_chosen_policy(self):
        self.assertIn("solid pure #FF00FF background", self.build("E")["prompt"])
        self.assertIn("genuine transparent alpha", self.build("E", background="alpha")["prompt"])
        with self.assertRaisesRegex(ValueError, "background must be key"):
            self.build("E", background="white")

    def test_missing_anchors_are_warned_about_not_silently_accepted(self):
        warnings = "\n".join(self.build("E")["warnings"])
        self.assertIn("no approved turnaround is attached", warnings)
        self.assertIn("make and approve the turnaround first", warnings)
        self.assertIn("no approved E picture is attached", warnings)
        self.assertIn("no neutral picture of this facing is attached to copy", warnings)
        unnamed = "\n".join(self.build("E", turnaround="turnaround.png")["warnings"])
        self.assertIn("the turnaround's view is not named", unnamed)
        self.assertNotIn("no neutral picture", "\n".join(self.build("E", loop="cycle")["warnings"]))

    def test_an_opposite_facing_is_offered_as_a_mirror_where_the_art_stays_correct(self):
        self.assertTrue(any("may be a mirror of an approved E" in w for w in self.build("W")["warnings"]))
        self.assertFalse(any("mirror" in w for w in self.build("E")["warnings"]))

    def test_the_slice_command_carries_the_strip_numbers_and_the_neutral_ends_check_into_the_cut(self):
        command = self.build("E", **self.ANCHORS)["slice"]
        self.assertIn("--frames 8 --columns 4", command)
        self.assertIn("--direction E --action clap", command)
        self.assertIn("--reference <the approved neutral picture of this facing> --neutral-ends", command)
        self.assertNotIn("--neutral-ends", self.build("E", loop="cycle", **self.ANCHORS)["slice"])

    def test_every_packet_carries_the_check_that_runs_after_every_generation_without_being_asked(self):
        packet = self.build("SE", kind="human", loop="neutral", turnaround="turnaround.png", turnaround_view_text="auto", facing_reference="e_neutral.png")
        after = packet["after_generation"]
        self.assertIn("never wait to be asked", after["when"])
        self.assertIn("before it is shown to anyone", after["when"])
        self.assertIn("--check-only", after["run"])
        self.assertIn("--frames 8 --columns 4", after["run"])
        self.assertIn("--neutral-ends", after["run"])
        self.assertIn("--crown 30", after["run"])
        self.assertIn("keeping the failed picture as a rejected candidate", after["on_refusal"])
        self.assertIn("compare the picture with the bottom row, fourth figure of the turnaround", " ".join(after["then_report"]))
        self.assertIn("is it the SE facing", " ".join(after["then_report"]))
        self.assertIn("is the camera elevation the same", " ".join(after["then_report"]))
        self.assertIn("gamearts_candidates.py review", after["review"])
        self.assertIn("--finding elevation=", after["review"])
        self.assertIn("only a passing review lets it be selected", " ".join(after["then_report"]))
        self.assertNotIn("--out", after["run"])
        vehicle = self.build("E", kind="vehicle", loop="cycle")["after_generation"]["run"]
        self.assertNotIn("--crown", vehicle)
        self.assertNotIn("--neutral-ends", vehicle)
        between = dp.inbetween(self.root, "E", "keys.png", 4, "run", kind="human")["after_generation"]["run"]
        self.assertIn("--frames 8", between)
        self.assertIn("--check-only", between)

    def test_the_prompt_is_written_from_the_saved_style(self):
        self.settings(art_style={"id": "pixel_art", "outline_policy": "Selective outline.", "shading_policy": "Many tones."})
        self.assertIn("STYLE (saved, do not change): pixel_art. Selective outline. Many tones.", self.build("E")["prompt"])

    def test_the_command_line_builds_one_packet(self):
        poses = [item for letter in "abcdefgh" for item in ("--pose", letter)]
        packet = self.cli("build", "--game-root", self.root, "--facing", "SE", "--frames", 8, "--action", "walk", "--kind", "human", "--loop", "cycle", "--paired-limbs", "--turnaround", "turnaround.png",
                          "--turnaround-view", "auto", "--canvas", "1536x1024", *poses)
        self.assertIn("Match the bottom row, fourth figure of it exactly", packet["prompt"])
        self.assertIn("(8) h", packet["prompt"])
        self.blocked(run("build", "--game-root", self.root, "--facing", "E", "--frames", 8, "--action", "walk", "--kind", "vehicle", "--canvas", "big"), "must be WIDTHxHEIGHT")


class CameraTests(Case):
    def view(self, profile, camera, facing, directions=None, **more):
        extra = {"directions": directions} if directions else {}
        self.settings(world=world(profile, camera), **extra)
        return self.build(facing, **more)["prompt"]

    def test_a_camera_without_facing_words_is_refused_not_guessed(self):
        self.settings(world=world("custom", "a hand-written camera"))
        with self.assertRaisesRegex(ValueError, "has no facing words in this builder"):
            self.build("E")

    def test_a_side_view_names_its_camera(self):
        prompt = self.view("side", "side-view orthographic", "E", ["E", "W", "N"])
        self.assertIn("CAMERA: side-view orthographic. THE CAMERA NEVER MOVES. Side-view orthographic", prompt)
        self.assertIn("pure SIDE view (profile)", self.build("W", kind="human")["prompt"])

    def test_an_isometric_camera_keeps_its_own_angle_and_names_facings_on_the_screen(self):
        prompt = self.view("isometric_3_4", "isometric 3/4 orthographic, 2:1 diamond grid", "SE")
        self.assertIn("CAMERA: isometric 3/4 orthographic, 2:1 diamond grid.", prompt)
        self.assertIn("ground axes recede diagonally in a fixed diamond", prompt)
        self.assertIn("direction the subject points on the SCREEN", prompt)
        self.assertNotIn("NEVER an isometric", prompt)

    def test_a_top_down_camera_shows_only_top_surfaces_whatever_the_kind(self):
        for kind in dp.KINDS:
            prompt = self.view("top_down", "top-down orthographic", "NE", kind=kind)
            self.assertIn("FACING FOR THIS ENTIRE SHEET: pointing toward the top-right of the screen, seen from directly above", prompt)
            self.assertIn("Directly overhead orthographic: only top surfaces show", prompt)
            self.assertIn("no side, front or rear faces", prompt)

    def test_a_facing_outside_the_games_directions_is_refused(self):
        self.settings(directions=["S", "W", "N", "E"])
        with self.assertRaisesRegex(ValueError, r"SE is not one of this game's directions \(S, W, N, E\)"):
            self.build("SE")

    def test_unconfirmed_settings_are_refused_by_every_command(self):
        self.settings(settings_status="needs_review")
        self.blocked(run("build", "--game-root", self.root, "--facing", "E", "--frames", 8, "--action", "x", "--kind", "vehicle"), "settings must be owner_confirmed")
        self.blocked(run("plan", "--game-root", self.root), "settings must be owner_confirmed")
        self.blocked(run("turnaround", "--game-root", self.root, "--subject", "x", "--kind", "vehicle"), "settings must be owner_confirmed")

    def test_a_picture_that_is_missing_or_outside_the_game_is_refused(self):
        with self.assertRaisesRegex(ValueError, "is not a picture file"):
            self.build("E", turnaround="nothing.png")
        with self.assertRaisesRegex(ValueError, "the turnaround picture must stay inside its folder"):
            self.build("E", turnaround="../outside.png")
        (self.root / "notes.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "is not a picture file"):
            self.build("E", facing_reference="notes.txt")


class TurnaroundTests(Case):
    def turnaround(self, subject="a green tanker truck", master=None, **more):
        more.setdefault("kind", "vehicle")
        return dp.turnaround(self.root, subject, master, **more)

    def test_the_model_sheet_lists_every_facing_in_the_arrangement_later_prompts_name(self):
        packet = self.turnaround(master="e_neutral.png")
        self.assertEqual(packet["rows"], [["E", "NE", "N", "NW"], ["W", "SW", "S", "SE"]])
        prompt = packet["prompt"]
        self.assertIn("seen from 8 facings, one figure per cell, 2 row(s) of up to 4", prompt)
        self.assertIn("1536x1024 canvas (equal invisible cells about 384x512)", prompt)
        self.assertIn("TOP ROW, FIRST FIGURE: EAST", prompt)
        self.assertIn("TOP ROW, THIRD FIGURE: NORTH", prompt)
        self.assertIn("BOTTOM ROW, THIRD FIGURE: SOUTH", prompt)
        self.assertIn("BOTTOM ROW, FOURTH FIGURE: SOUTHEAST", prompt)
        self.assertIn("Input 1 is the APPROVED design of the subject", prompt)
        self.assertEqual([(r["role"], r["path"]) for r in packet["references"]], [("identity", "e_neutral.png")])
        self.assertIn("same neutral standing pose in every cell", prompt)
        self.assertEqual(packet["warnings"], [])

    def test_the_names_it_gives_each_figure_are_the_names_build_uses(self):
        for facing, words in self.turnaround()["views"].items():
            with self.subTest(facing=facing):
                self.assertIn(f"Match {words} of it exactly", self.build(facing, turnaround="turnaround.png", turnaround_view_text="auto")["prompt"])

    def test_a_turnaround_with_no_design_picture_says_so(self):
        self.assertTrue(any("no approved design picture" in w for w in self.turnaround()["warnings"]))

    def test_each_kind_gets_its_own_figures(self):
        self.assertIn("NO face, cheek or front of the chest", self.turnaround("a footballer", kind="human")["prompt"])
        self.assertIn("the tail, the hindquarters", self.turnaround("a horse", kind="animal")["prompt"])
        self.assertIn("long axis runs left-right", self.turnaround("a bridge", kind="structure")["prompt"])

    def test_a_game_with_four_directions_gets_one_row(self):
        self.settings(directions=["S", "W", "N", "E"])
        packet = self.turnaround("x")
        self.assertEqual(packet["rows"], [["E", "N", "W", "S"]])
        self.assertIn("2172x724 canvas", packet["prompt"])
        self.assertEqual(packet["views"]["E"], "the only row, first figure")

    def test_the_command_line_writes_the_sheet_prompt(self):
        packet = self.cli("turnaround", "--game-root", self.root, "--subject", "the hero", "--master", "e_neutral.png", "--kind", "human", "--background", "alpha")
        self.assertIn("genuine transparent alpha", packet["prompt"])
        self.assertEqual(packet["views"]["SE"], "the bottom row, fourth figure")


class PlanTests(Case):
    def test_five_facings_are_drawn_and_three_are_mirrors_and_the_east_is_drawn_first(self):
        packet = self.cli("plan", "--game-root", self.root)
        self.assertEqual(packet["draw"], ["S", "N", "NE", "E", "SE"])
        self.assertEqual(packet["mirror"], {"SW": "SE", "W": "E", "NW": "NE"})
        self.assertEqual(packet["pilot"], "E")
        self.assertIn("make and approve the turnaround", packet["steps"][0])
        self.assertIn("draw the E strip first", packet["steps"][1])
        self.assertIn("have the owner compare it with the turnaround", packet["steps"][1])
        self.assertIn("mirror SW from SE, W from E, NW from NE only where the art stays correct", packet["steps"][3])

    def test_a_facing_whose_source_is_not_in_the_game_must_be_drawn(self):
        self.settings(directions=["S", "W", "N"])
        packet = dp.plan(self.root)
        self.assertEqual((packet["draw"], packet["mirror"], packet["pilot"]), (["S", "W", "N"], {}, "S"))
        self.settings(directions=["S", "W", "N", "E"])
        self.assertEqual((dp.plan(self.root)["draw"], dp.plan(self.root)["mirror"]), (["S", "N", "E"], {"W": "E"}))


class InbetweenTests(Case):
    def test_every_other_frame_is_a_keypose_and_the_loop_seam_gets_an_in_between(self):
        packet = dp.inbetween(self.root, "E", "keys.png", 4, "run", kind="human", turnaround="turnaround.png", turnaround_view_text="auto")
        prompt = packet["prompt"]
        self.assertEqual([r["role"] for r in packet["references"]], ["keyposes", "turnaround"])
        self.assertIn("Input 1 contains 4 APPROVED keyposes", prompt)
        self.assertIn("Produce 8 sequential frames", prompt)
        self.assertIn("INCLUDING between the last keypose and the first (the loop seam)", prompt)
        self.assertIn("Frame 1 = input keypose 1, unchanged.", prompt)
        self.assertIn("Frame 2 = the pose halfway between keypose 1 and keypose 2", prompt)
        self.assertIn("Frame 7 = input keypose 4, unchanged.", prompt)
        self.assertIn("Frame 8 = the pose halfway between keypose 4 and keypose 1", prompt)
        self.assertIn("Match the top row, first figure", prompt)
        self.assertIn("The cycle has no duplicated endpoint", prompt)
        self.assertEqual(packet["layout"]["frames"], 8)
        self.assertNotIn("FIRST and LAST", prompt)

    def test_it_needs_at_least_two_keyposes_and_a_picture_of_them(self):
        with self.assertRaisesRegex(ValueError, "keyframes must be a whole number of at least 2"):
            dp.inbetween(self.root, "E", "keys.png", 1, "run", kind="human")
        with self.assertRaisesRegex(ValueError, "is not a picture file"):
            dp.inbetween(self.root, "E", "none.png", 4, "run", kind="human")

    def test_the_command_line_builds_the_in_between_prompt(self):
        packet = self.cli("inbetween", "--game-root", self.root, "--facing", "E", "--keyposes", "keys.png", "--keyframes", 3, "--action", "run", "--kind", "human", "--paired-limbs")
        self.assertEqual(packet["layout"]["frames"], 6)
        self.assertIn("Frame 6 = the pose halfway between keypose 3 and keypose 1", packet["prompt"])


class RepairTests(Case):
    def repair(self, **more):
        args = dict(facing="SE", target="strip.png", turnaround="turnaround.png", problem="it is too close to a right side profile", degrees=35, turn="toward-viewer", kind="vehicle")
        args.update(more)
        return dp.repair(self.root, args.pop("facing"), args.pop("target"), args.pop("turnaround"), args.pop("problem"), args.pop("degrees"), args.pop("turn"), **args)

    def test_a_wrong_facing_is_repaired_by_an_edit_against_the_turnaround_with_the_angle_in_degrees(self):
        packet = self.repair(turnaround_view_text="auto", frames=18)
        self.assertEqual([(r["role"], r["path"]) for r in packet["references"]], [("edit-target", "strip.png"), ("turnaround", "turnaround.png")])
        prompt = packet["prompt"]
        self.assertIn("Use case: precise-object-edit.", prompt)
        self.assertIn("required viewing-angle reference, matching the bottom row, fourth figure", prompt)
        self.assertIn("Correct ONLY the facing/camera relationship for all 18 figures", prompt)
        self.assertIn("The current result is wrong: it is too close to a right side profile", prompt)
        self.assertIn("about 35 degrees toward the viewer", prompt)
        self.assertIn("SOUTHEAST, a three-quarter FRONT view", prompt)
        self.assertIn("THE CAMERA NEVER MOVES", prompt)
        self.assertIn("Change nothing else", prompt)
        self.assertIn("playback or measurement logs are not facing acceptance", packet["not_assessed"][0])

    def test_a_human_repair_uses_the_feature_words(self):
        self.assertIn("The centre of the face points diagonally toward the lower right", self.repair(kind="human")["prompt"])

    def test_a_repair_needs_the_turnaround_the_angle_and_the_fault(self):
        for more, text in (({"degrees": 0}, "degrees must be a whole number from 1 to 90"), ({"degrees": 120}, "degrees must be a whole number from 1 to 90"), ({"problem": "  "}, "say what is wrong"),
                           ({"turnaround": "gone.png"}, "is not a picture file"), ({"facing": "ZZ"}, "ZZ is not one of this game's directions"), ({"turn": "sideways"}, "turn must be one of")):
            with self.subTest(more=more), self.assertRaisesRegex(ValueError, text):
                self.repair(**more)

    def test_the_command_line_repairs_a_facing_and_refuses_a_missing_turnaround(self):
        packet = self.cli("repair", "--game-root", self.root, "--facing", "SE", "--target", "strip.png", "--turnaround", "turnaround.png", "--problem", "x", "--degrees", 35, "--turn", "toward-viewer", "--kind", "vehicle")
        self.assertIn("about 35 degrees", packet["prompt"])
        self.assertEqual(run("repair", "--game-root", self.root, "--facing", "SE", "--target", "strip.png", "--problem", "x", "--degrees", 35, "--turn", "toward-viewer", "--kind", "vehicle").returncode, 2)


class RespaceTests(Case):
    def test_only_the_spacing_is_corrected_with_one_factor_for_every_figure(self):
        packet = dp.respace(self.root, "strip.png", 4, baseline=24)
        prompt = packet["prompt"]
        self.assertEqual([(r["role"], r["path"]) for r in packet["references"]], [("edit-target", "strip.png")])
        self.assertIn("Repair ONLY layout and cut-out spacing", prompt)
        self.assertIn("Keep the EXACT original 64x32 canvas and true alpha transparency", prompt)
        self.assertIn("Divide it into 4 equal invisible columns of width 16", prompt)
        self.assertIn("Uniformly reduce EVERY whole figure to 70% of its present size (the same factor for all 4)", prompt)
        self.assertIn("centre each figure horizontally in its OWN column", prompt)
        self.assertIn("on the line y=24", prompt)
        self.assertIn("at least 18 pixels from its cell's vertical borders", prompt)
        self.assertIn("Do NOT scale individual limbs or heads", prompt)
        self.assertIn("THE CAMERA NEVER MOVES", prompt)

    def test_a_grid_is_divided_into_rows_and_a_different_share_and_margin_can_be_asked_for(self):
        prompt = dp.respace(self.root, "strip.png", 4, columns=2, percent=60, margin=10)["prompt"]
        self.assertIn("and 2 rows", prompt)
        self.assertIn("to 60% of its present size", prompt)
        self.assertIn("at least 10 pixels", prompt)
        self.assertIn("one common baseline", dp.respace(self.root, "strip.png", 4)["prompt"])

    def test_the_share_and_the_margin_must_be_sensible(self):
        with self.assertRaisesRegex(ValueError, "percent must be a whole number from 30 to 95"):
            dp.respace(self.root, "strip.png", 4, percent=20)
        with self.assertRaisesRegex(ValueError, "margin must be a whole number of pixels"):
            dp.respace(self.root, "strip.png", 4, margin=0)

    def test_the_command_line_writes_the_spacing_edit(self):
        self.assertIn("equal invisible columns of width 16", self.cli("respace", "--game-root", self.root, "--target", "strip.png", "--frames", 4)["prompt"])


class FixTests(Case):
    def test_only_the_named_items_change_and_everything_else_is_kept(self):
        packet = dp.fix(self.root, "strip.png", ["ROW ONE, columns TWO and THREE: lower the receiving boot to 2% of the cell height", "ROW TWO, column THREE: bend the arm so the hand fits"])
        prompt = packet["prompt"]
        self.assertIn("This is a very limited repair, not regeneration or redesign.", prompt)
        self.assertIn("Change ONLY these items:", prompt)
        self.assertIn("1. ROW ONE, columns TWO and THREE", prompt)
        self.assertIn("2. ROW TWO, column THREE", prompt)
        self.assertIn("Every other pixel belonging to the figures must stay as close as possible to the input", prompt)
        self.assertIn("preserve the neutral first and last poses and the identical size of every figure", prompt)
        self.assertIn("THE CAMERA NEVER MOVES", prompt)
        self.assertEqual([r["role"] for r in packet["references"]], ["edit-target"])

    def test_what_must_stay_can_be_named(self):
        self.assertIn("In particular preserve the header jump and landing.", dp.fix(self.root, "strip.png", ["x"], keep="the header jump and landing")["prompt"])

    def test_a_fix_names_what_to_change(self):
        with self.assertRaisesRegex(ValueError, "name at least one thing to change"):
            dp.fix(self.root, "strip.png", ["  "])
        with self.assertRaisesRegex(ValueError, "name at least one thing to change"):
            dp.fix(self.root, "strip.png", [])

    def test_the_command_line_writes_the_fix_prompt_and_needs_a_change(self):
        packet = self.cli("fix", "--game-root", self.root, "--target", "strip.png", "--change", "frame 3: lower the boot", "--change", "frame 5: close the hand", "--keep", "frames 1 and 8")
        self.assertIn("2. frame 5: close the hand", packet["prompt"])
        self.assertIn("preserve frames 1 and 8.", packet["prompt"])
        self.assertEqual(run("fix", "--game-root", self.root, "--target", "strip.png").returncode, 2)


if __name__ == "__main__":
    unittest.main()
