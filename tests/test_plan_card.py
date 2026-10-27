"""The plan card (plan P13.4): before the first picture is made, the lane, the number of pictures, the approvals and what it may cost."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)
from gamearts_testkit import write_settings

import gamearts_plan_card as card  # noqa: E402
from test_lifecycle_operations import GameFolder, OUT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_plan_card.py"


class GameCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        write_settings(self.root, directions="dirs_8")

    def tearDown(self):
        self._tmp.cleanup()

    def plan(self, asset_class, **kwargs):
        return card.plan(self.root, asset_class, **kwargs)


class LaneTests(GameCase):
    def test_a_single_static_asset_is_quick(self):
        for asset_class in ("prop", "static_structure", "terrain", "ui_presentation", "effect", "parallax_layer", "fixed_machinery"):
            with self.subTest(asset_class):
                self.assertEqual(self.plan(asset_class)["lane"], "quick", asset_class)

    def test_anything_with_detachable_parts_is_full(self):
        result = self.plan("fixed_machinery", detachable_parts=3)
        self.assertEqual(result["lane"], "full")
        self.assertIn("detachable", result["why"])

    def test_a_character_that_faces_and_moves_is_standard(self):
        result = self.plan("mobile_directional", actions=2, frames_per_action=4)
        self.assertEqual(result["lane"], "standard")

    def test_an_animated_prop_with_no_parts_is_standard_not_quick(self):
        self.assertEqual(self.plan("prop", actions=1, frames_per_action=6)["lane"], "standard")

    def test_a_set_of_pictures_is_standard_and_needs_to_say_how_many(self):
        self.assertEqual(self.plan("tileset", pictures=16)["lane"], "standard")
        with self.assertRaisesRegex(ValueError, "how many pictures"):
            self.plan("tileset")
        with self.assertRaisesRegex(ValueError, "how many pictures"):
            self.plan("icon_set", pictures=0)

    def test_a_set_of_one_picture_is_one_static_asset_and_reads_as_one(self):
        result = self.plan("icon_set", pictures=1)
        self.assertEqual(result["lane"], "quick")
        self.assertEqual(result["estimated_pictures"], 2)
        self.assertNotIn("a set of 1", result["why"])
        self.assertIn("the finished asset", result["approvals"])

    def test_a_stack_of_parallax_layers_is_a_set_and_counts_every_layer(self):
        result = self.plan("parallax_layer", pictures=7)
        self.assertEqual(result["lane"], "standard")
        self.assertEqual(result["image_calls"]["pictures"], 7)
        self.assertEqual(self.plan("parallax_layer")["lane"], "quick")

    def test_a_game_with_no_ground_world_is_not_planned_world_art(self):
        write_settings(self.root, world_kind="screen_space", screen={"base_resolution_px": [1280, 720]}, drop=("world", "directions"))
        with self.assertRaisesRegex(ValueError, "screen_space.*terrain art does not apply"):
            self.plan("terrain")
        self.assertEqual(self.plan("ui_presentation")["lane"], "quick")
        self.assertEqual(self.plan("icon_set", pictures=1)["lane"], "quick")

    def test_a_cut_out_rig_counts_its_parts_and_not_a_picture_for_every_frame(self):
        drawn = self.plan("mobile_directional", actions=1, frames_per_action=8, detachable_parts=6)
        rig = self.plan("mobile_directional", actions=1, frames_per_action=8, detachable_parts=6, rig_by_transform=True)
        self.assertIn("frames", drawn["image_calls"])
        self.assertNotIn("frames", rig["image_calls"])
        self.assertEqual(rig["lane"], "full")
        self.assertLess(rig["estimated_pictures"], drawn["estimated_pictures"])
        with self.assertRaisesRegex(ValueError, "how many parts"):
            self.plan("mobile_directional", actions=1, frames_per_action=8, rig_by_transform=True)

    def test_a_quick_card_for_a_building_says_it_assumes_nothing_moves(self):
        self.assertIn("nothing on it opens or moves", self.plan("static_structure")["message"])
        self.assertNotIn("nothing on it opens or moves", self.plan("static_structure", detachable_parts=2)["message"])
        self.assertNotIn("nothing on it opens or moves", self.plan("prop")["message"])

    def test_an_unknown_class_names_the_choices(self):
        with self.assertRaisesRegex(ValueError, "mobile_directional"):
            self.plan("dragon")

    def test_negative_or_fractional_amounts_are_refused(self):
        for key in ("actions", "frames_per_action", "detachable_parts"):
            with self.subTest(key), self.assertRaisesRegex(ValueError, "whole number"):
                self.plan("prop", **{key: -1})


class CountTests(GameCase):
    def test_a_quick_asset_costs_a_mockup_and_a_master(self):
        result = self.plan("prop")
        self.assertEqual(result["image_calls"], {"mockup": 1, "master": 1})
        self.assertEqual(result["estimated_pictures"], 2)

    def test_an_approved_mockup_that_already_covers_the_asset_needs_no_new_one(self):
        result = self.plan("prop", mockup_approved=True)
        self.assertEqual(result["image_calls"], {"master": 1})
        self.assertEqual(result["estimated_pictures"], 1)

    def test_a_facing_character_adds_one_master_per_other_direction_and_one_picture_per_frame(self):
        result = self.plan("mobile_directional", actions=2, frames_per_action=4)
        self.assertEqual(result["image_calls"], {"mockup": 1, "master": 1, "directional_masters": 7, "frames": 8 * 2 * 4})
        self.assertEqual(result["estimated_pictures"], 1 + 1 + 7 + 64)

    def test_the_number_of_directions_comes_from_the_games_settings(self):
        write_settings(self.root, directions="dirs_4")
        self.assertEqual(self.plan("mobile_directional", actions=1, frames_per_action=2)["image_calls"]["directional_masters"], 3)
        write_settings(self.root, directions="dirs_1_side")
        self.assertEqual(self.plan("mobile_directional", actions=1, frames_per_action=2)["image_calls"]["directional_masters"], 0)

    def test_directions_do_not_multiply_a_static_or_non_facing_class(self):
        self.assertEqual(self.plan("prop", actions=1, frames_per_action=6)["image_calls"]["frames"], 6)
        self.assertEqual(self.plan("tileset", pictures=16)["image_calls"], {"mockup": 1, "pictures": 16})

    def test_each_detachable_part_costs_a_master_and_a_rebuilt_area_behind_it(self):
        result = self.plan("fixed_machinery", detachable_parts=3, actions=1, frames_per_action=4)
        self.assertEqual(result["image_calls"], {"mockup": 1, "master": 1, "parts": 3 * 2, "frames": 4})
        self.assertEqual(result["estimated_pictures"], 1 + 1 + 6 + 4)

    def test_a_mobile_class_needs_the_games_directions_so_missing_settings_say_so(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(ValueError, "directions"):
                card.plan(Path(empty), "mobile_directional", actions=1, frames_per_action=2)
            self.assertEqual(card.plan(Path(empty), "prop")["lane"], "quick")  # a static asset needs no settings to be planned


class ApprovalTests(GameCase):
    def test_quick_asks_for_the_mockup_and_the_finished_asset_only(self):
        self.assertEqual(self.plan("prop")["approvals"], ["the mockup", "the finished asset"])
        self.assertEqual(self.plan("prop", mockup_approved=True)["approvals"], ["the finished asset"])

    def test_standard_adds_the_master_and_full_adds_the_hidden_area_review(self):
        self.assertEqual(self.plan("mobile_directional", actions=1, frames_per_action=2)["approvals"], ["the mockup", "the master picture", "the finished asset"])
        self.assertEqual(self.plan("fixed_machinery", detachable_parts=1)["approvals"],
                         ["the mockup", "the master picture", "the cut-out parts and the areas behind them (review boards)", "the finished asset"])


class CreditTests(GameCase):
    def plan_with(self, tool, **extra):
        write_settings(self.root, directions="dirs_8", image_generation={"tool": tool, "tool_name": "Acme Art"} if tool == "connected_tool" else {"tool": tool})
        return self.plan("prop")["credits"]

    def test_a_connected_tool_may_cost_credits_and_the_card_does_not_invent_a_price(self):
        text = self.plan_with("connected_tool")
        self.assertIn("Acme Art", text)
        self.assertIn("ask", text.lower())
        self.assertNotRegex(text, r"\d+ credits")

    def test_the_other_tools_say_what_is_true_of_them(self):
        self.assertIn("API", self.plan_with("cli_image_gen"))
        self.assertIn("own plan", self.plan_with("built_in_image_gen"))
        self.assertIn("supply", self.plan_with("user_supplied"))

    def test_settings_that_cannot_be_read_are_named_in_the_card_not_hidden(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIn("settings could not be read", card.plan(Path(empty), "prop")["credits"])

    def test_a_game_with_no_saved_tool_says_it_is_not_chosen_yet(self):
        write_settings(self.root, directions="dirs_8", drop=("image_generation",))
        self.assertIn("not chosen", self.plan("prop")["credits"])


class MessageTests(GameCase):
    def test_the_message_states_lane_count_approvals_and_credits_in_plain_words(self):
        message = self.plan("prop")["message"]
        for expected in ("Quick lane", "2 pictures", "the mockup, then the finished asset", "Credits"):
            self.assertIn(expected, message)

    def test_the_message_for_a_single_approval_and_a_single_picture_is_singular(self):
        message = self.plan("prop", mockup_approved=True)["message"]
        self.assertIn("1 picture ", message)
        self.assertNotIn("1 pictures", message)

    def test_full_names_why_it_is_the_longer_road(self):
        message = self.plan("fixed_machinery", detachable_parts=2)["message"]
        self.assertIn("Full lane", message)
        self.assertIn("cut-out parts", message)


class CommandTests(GameCase):
    def run_card(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--game-root", str(self.root), *args], capture_output=True, text=True)

    def test_the_command_prints_the_card_as_json(self):
        done = self.run_card("--asset-class", "mobile_directional", "--actions", "1", "--frames-per-action", "4")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual((result["lane"], result["estimated_pictures"]), ("standard", 1 + 1 + 7 + 32))

    def test_a_refusal_says_why_and_exits_one(self):
        done = self.run_card("--asset-class", "tileset")
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)
        self.assertIn("how many pictures", done.stderr)


class CompositeGateTests(GameFolder):
    """Quick is for a static single asset. A composite described as Quick gets no easier road: the cleanup and review gates are the ones that stop it."""

    def test_a_composite_bundle_without_cleanup_evidence_cannot_be_approved_whatever_lane_was_named(self):
        import build_component_bundle as bundle
        from test_component_bundle import ComponentTests
        source = self.approved_mockup()
        folder = self.root / OUT / "assets/generated/machine_v001"
        folder.parent.mkdir(parents=True, exist_ok=True)
        config = ComponentTests().fixture(self.root)
        bundle.build(config, folder, self.root)
        import gamearts_asset_lifecycle as life
        life.register_asset(self.root, "machine_v001", "v001", f"{OUT}/assets/generated/machine_v001", [source])
        with self.assertRaises(ValueError) as refused:
            life.approve_asset(self.root, "machine_v001", "owner said it looks fine")
        self.assertRegex(str(refused.exception), r"(?i)cleanup|review|gate")
        self.assertEqual(self.manifest("assets")[0]["status"], "generated")


if __name__ == "__main__":
    unittest.main()
