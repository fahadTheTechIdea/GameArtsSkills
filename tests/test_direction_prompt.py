"""Tests for the per-facing prompt packet and the facing repair edit (scripts/gamearts_direction_prompt.py)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gamearts_testkit import write_settings, settings

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_direction_prompt.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "game"
        self.root.mkdir()
        write_settings(self.root)
        for name in ("turnaround.png", "e_neutral.png", "clap_timeline.png", "strip.png"):
            Image.new("RGBA", (64, 32), (10, 20, 30, 255)).save(self.root / name)

    def build(self, facing="E", *extra, frames=8):
        return run("build", "--game-root", self.root, "--facing", facing, "--frames", frames, "--action", "clap", *extra)

    def packet(self, facing="E", *extra, frames=8):
        result = self.build(facing, *extra, frames=frames)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def blocked(self, result, text):
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stderr, "BLOCKED")
        self.assertRegex(result.stderr, text)
        self.assertEqual(result.stdout, "")

    def settings(self, **overrides):
        write_settings(self.root, **overrides)


class BuildTests(Case):
    ANCHORS = ("--turnaround", "turnaround.png", "--turnaround-view", "bottom row, third figure", "--facing-reference", "e_neutral.png", "--timeline-reference", "clap_timeline.png")

    def test_every_anchor_is_attached_in_order_and_given_its_job(self):
        packet = self.packet("E", *self.ANCHORS, "--subject", "a green tanker truck")
        self.assertEqual([(r["role"], r["path"]) for r in packet["references"]], [("turnaround", "turnaround.png"), ("facing", "e_neutral.png"), ("timeline", "clap_timeline.png")])
        self.assertTrue(all(len(r["sha256"]) == 64 for r in packet["references"]))
        prompt = packet["prompt"]
        self.assertIn("Input 1 is the APPROVED turnaround", prompt)
        self.assertIn("Match bottom row, third figure of it exactly", prompt)  # the exact view is named
        self.assertIn("Input 2 is the approved neutral picture of THIS facing", prompt)
        self.assertRegex(prompt, r"Input 3 is ONLY the approved action timeline.*Do NOT inherit its camera or facing")
        self.assertIn("a green tanker truck doing clap", prompt)
        self.assertEqual(packet["warnings"], [])

    def test_the_facing_says_what_shows_and_what_must_not(self):
        east = self.packet("E")["prompt"]
        self.assertIn("pure SIDE view", east)
        self.assertIn("front and rear faces are not visible", east)
        north = self.packet("N")["prompt"]
        self.assertIn("only its REAR face and its top surface show", north)
        self.assertIn("Its front is hidden", north)
        for facing in ("S", "SW", "W", "NW", "N", "NE", "E", "SE"):
            with self.subTest(facing=facing):
                self.assertIn("FACING FOR THIS ENTIRE SHEET: " + {"S": "SOUTH", "SW": "SOUTHWEST", "W": "WEST", "NW": "NORTHWEST", "N": "NORTH", "NE": "NORTHEAST", "E": "EAST", "SE": "SOUTHEAST"}[facing], self.packet(facing)["prompt"])

    def test_the_saved_camera_is_repeated_and_never_isometric(self):
        prompt = self.packet("SE")["prompt"]
        self.assertIn("CAMERA: elevated orthographic oblique.", prompt)  # the owner's saved wording
        self.assertIn("THE CAMERA NEVER MOVES; only the subject turns", prompt)
        self.assertIn("NEVER an isometric or diamond view", prompt)

    def test_the_layout_the_scale_and_the_ground_line_are_numbers(self):
        packet = self.packet("E", "--cell", "400x500", "--neutral-height", "300", "--ground-line", "450")
        self.assertEqual(packet["layout"], {"frames": 8, "columns": 8, "rows": 1, "cell": [400, 500], "canvas": [3200, 500], "neutral_height": 300, "ground_line": 450, "gutter": 48})
        prompt = packet["prompt"]
        self.assertIn("EXACTLY 8 complete figures, in ONE horizontal row", prompt)
        self.assertIn("canvas is 3200x500 pixels", prompt)
        self.assertIn("at least 48 pixels of completely empty background", prompt)
        self.assertIn("about 300 pixels tall", prompt)
        self.assertIn("the line 450 pixels below the top of each cell", prompt)
        self.assertIn("Never resize a figure between frames", prompt)
        grid = self.packet("E", "--columns", "4")
        self.assertEqual((grid["layout"]["rows"], grid["layout"]["canvas"]), (2, [1536, 1024]))
        self.assertIn("in 2 rows of 4", grid["prompt"])

    def test_a_loop_starts_and_ends_on_the_neutral_pose_unless_it_is_not_a_loop(self):
        self.assertIn("The FIRST and LAST figures are identical copies of the approved neutral pose", self.packet("E", *self.ANCHORS)["prompt"])
        self.assertNotIn("FIRST and LAST", self.packet("E", *self.ANCHORS, "--no-neutral-ends")["prompt"])

    def test_the_background_follows_the_chosen_policy(self):
        self.assertIn("solid pure #FF00FF background", self.packet("E")["prompt"])
        self.assertIn("genuine transparent alpha", self.packet("E", "--background", "alpha")["prompt"])

    def test_missing_anchors_are_warned_about_not_silently_accepted(self):
        warnings = "\n".join(self.packet("E")["warnings"])
        self.assertIn("no approved turnaround is attached", warnings)
        self.assertIn("no approved E picture is attached", warnings)
        self.assertIn("no neutral picture of this facing is attached to copy", warnings)
        unnamed = "\n".join(self.packet("E", "--turnaround", "turnaround.png")["warnings"])
        self.assertIn("the turnaround's view is not named", unnamed)

    def test_an_opposite_facing_is_offered_as_a_mirror_where_the_art_stays_correct(self):
        self.assertTrue(any("may be a mirror of an approved E" in w for w in self.packet("W")["warnings"]))
        self.assertFalse(any("mirror" in w for w in self.packet("E")["warnings"]))

    def test_the_slice_command_carries_the_strip_numbers_into_the_cut(self):
        command = self.packet("E", *self.ANCHORS, "--columns", "4")["slice"]
        self.assertIn("--frames 8 --columns 4", command)
        self.assertIn("--direction E --action clap", command)
        self.assertIn("--reference <the approved neutral picture of this facing>", command)

    def test_the_prompt_is_written_from_the_saved_style(self):
        self.settings(art_style={"id": "pixel_art", "outline_policy": "Selective outline.", "shading_policy": "Many tones."})
        self.assertIn("STYLE (saved, do not change): pixel_art. Selective outline. Many tones.", self.packet("E")["prompt"])


class RefusalTests(Case):
    def test_a_facing_outside_the_games_directions_is_refused(self):
        self.settings(directions=["S", "W", "N", "E"])
        self.blocked(self.build("SE"), r"SE is not one of this game's directions \(S, W, N, E\)")

    def test_a_camera_without_facing_words_is_refused_not_guessed(self):
        self.settings(world={"grid": "orthogonal_square", "camera_profile": "custom", "object_camera": "a hand-written camera", "logical_tile_m": [1, 1],
                             "ground_tile_px": [128, 64], "pixels_per_meter": 64, "construction_snap_m": 1})
        self.blocked(self.build("E"), "has no facing words in this builder")

    def view(self, profile, camera, facing):
        self.settings(world={"grid": "orthogonal_square", "camera_profile": profile, "object_camera": camera, "logical_tile_m": [1, 1],
                             "ground_tile_px": [64, 64], "pixels_per_meter": 64, "construction_snap_m": 1})
        return self.packet(facing)["prompt"]

    def test_an_isometric_camera_keeps_its_own_angle_and_names_facings_on_the_screen(self):
        prompt = self.view("isometric_3_4", "isometric 3/4 orthographic, 2:1 diamond grid", "SE")
        self.assertIn("CAMERA: isometric 3/4 orthographic, 2:1 diamond grid.", prompt)
        self.assertIn("ground axes recede diagonally in a fixed diamond", prompt)
        self.assertIn("direction the subject points on the SCREEN", prompt)
        self.assertNotIn("NEVER an isometric", prompt)  # the oblique ban would contradict this game's own camera

    def test_a_top_down_camera_shows_only_top_surfaces(self):
        prompt = self.view("top_down", "top-down orthographic", "NE")
        self.assertIn("FACING FOR THIS ENTIRE SHEET: pointing toward the top-right of the screen, seen from directly above", prompt)
        self.assertIn("Directly overhead orthographic: only top surfaces show", prompt)
        self.assertIn("no side, front or rear faces", prompt)

    def test_a_side_view_has_only_the_two_sides(self):
        self.settings(world={"grid": "orthogonal_square", "camera_profile": "side", "object_camera": "side-view orthographic", "logical_tile_m": [1, 1],
                             "ground_tile_px": [64, 64], "pixels_per_meter": 64, "construction_snap_m": 1}, directions=["E", "W", "N"])
        self.assertIn("CAMERA: side-view orthographic. THE CAMERA NEVER MOVES. Side-view orthographic", self.packet("E")["prompt"])
        self.blocked(self.build("N"), "a side camera has no N facing here")

    def test_unconfirmed_settings_are_refused(self):
        self.settings(settings_status="needs_review")
        self.blocked(self.build("E"), "settings must be owner_confirmed")
        self.blocked(run("repair", "--game-root", self.root, "--facing", "SE", "--target", "strip.png", "--turnaround", "turnaround.png", "--problem", "x", "--degrees", "35", "--turn", "toward-viewer"),
                     "settings must be owner_confirmed")

    def test_a_picture_that_is_missing_or_outside_the_game_is_refused(self):
        self.blocked(self.build("E", "--turnaround", "nothing.png"), "is not a picture file")
        self.blocked(self.build("E", "--turnaround", "../outside.png"), "the turnaround picture must stay inside its folder")
        (self.root / "notes.txt").write_text("x", encoding="utf-8")
        self.blocked(self.build("E", "--facing-reference", "notes.txt"), "is not a picture file")

    def test_a_layout_that_cannot_hold_the_figures_is_refused(self):
        self.blocked(self.build("E", "--columns", "3"), "8 frames do not fit 3 columns")
        self.blocked(self.build("E", "--cell", "big"), "must be WIDTHxHEIGHT")
        self.blocked(self.build("E", "--neutral-height", "480", "--ground-line", "450"), "must be above the ground line")


class RepairTests(Case):
    def repair(self, *extra, **more):
        args = {"--facing": "SE", "--target": "strip.png", "--turnaround": "turnaround.png", "--problem": "it is too close to a right side profile", "--degrees": "35", "--turn": "toward-viewer"}
        args.update(more)
        flat = [item for pair in args.items() for item in pair]
        return run("repair", "--game-root", self.root, *flat, *extra)

    def test_a_wrong_facing_is_repaired_by_an_edit_against_the_turnaround_with_the_angle_in_degrees(self):
        result = self.repair("--turnaround-view", "bottom row, rightmost figure", "--frames", "18")
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual([(r["role"], r["path"]) for r in packet["references"]], [("edit-target", "strip.png"), ("turnaround", "turnaround.png")])
        prompt = packet["prompt"]
        self.assertIn("Use case: precise-object-edit.", prompt)
        self.assertIn("required viewing-angle reference, matching bottom row, rightmost figure", prompt)
        self.assertIn("Correct ONLY the facing/camera relationship for all 18 figures", prompt)
        self.assertIn("The current result is wrong: it is too close to a right side profile", prompt)
        self.assertIn("about 35 degrees toward the viewer", prompt)
        self.assertIn("SOUTHEAST, a three-quarter FRONT view", prompt)
        self.assertIn("THE CAMERA NEVER MOVES", prompt)  # the camera is repeated in the edit
        self.assertIn("Change nothing else", prompt)
        self.assertIn("playback or measurement logs are not facing acceptance", packet["not_assessed"][0])

    def test_a_repair_needs_the_turnaround_the_angle_and_the_fault(self):
        self.blocked(self.repair(**{"--degrees": "0"}), "degrees must be a whole number from 1 to 90")
        self.blocked(self.repair(**{"--degrees": "120"}), "degrees must be a whole number from 1 to 90")
        self.blocked(self.repair(**{"--problem": "  "}), "say what is wrong")
        self.blocked(self.repair(**{"--turnaround": "gone.png"}), "is not a picture file")
        self.blocked(self.repair(**{"--facing": "ZZ"}), "ZZ is not one of this game's directions")
        self.assertEqual(run("repair", "--game-root", self.root, "--facing", "SE", "--target", "strip.png", "--problem", "x", "--degrees", "35", "--turn", "toward-viewer").returncode, 2)  # no turnaround given


if __name__ == "__main__":
    unittest.main()
