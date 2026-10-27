"""The setup wizard: every setting is a question the owner answers by choosing; nothing is filled in for them, and settings the wizard did not write
cannot be confirmed."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)

import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_setup as wizard  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_setup.py"
COMMON = [("project_name", "name", "Demo Game"), ("animation", "hybrid", None), ("image_generator", "user_supplied", None), ("engine", "generic", None), ("palette", "none", None)]
PLANS = {
    "grid_world": [("world_kind", "grid_world", None), ("look", "pixel_mid", None), ("viewpoint", "oblique", None), ("tile_size", "32x32", None),
                   ("directions", "dirs_4", None)] + COMMON,
    "free_world": [("world_kind", "free_world", None), ("look", "painterly", None), ("viewpoint", "side", None), ("scale", "64", None),
                   ("directions", "dirs_2_side", None)] + COMMON,
    "layered_scene": [("world_kind", "layered_scene", None), ("look", "painterly", None), ("viewpoint", "side", None), ("scale", "32", None),
                      ("layers", "5", None), ("directions", "dirs_2_side", None)] + COMMON,
    "screen_space": [("world_kind", "screen_space", None), ("look", "flat_vector", None), ("screen_size", "1920x1080", None),
                     ("screen_scaling", "fit", None)] + COMMON,
}


def run(root, plan):
    for name, value, text in plan:
        wizard.answer(root, name, value, text)


class GameCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def settings(self):
        return common.read_json(self.root / ".gamearts" / "project.json")


class PromptTests(GameCase):
    def test_the_first_question_is_shown_with_its_prompt_and_numbered_options(self):
        self.assertEqual(wizard.next_question(self.root)["question"]["id"], "project_name")
        wizard.answer(self.root, "project_name", "name", "Demo")
        first = wizard.next_question(self.root)
        self.assertEqual(first["question"]["id"], "world_kind")
        self.assertIn("What kind of world", first["text"])
        self.assertIn("1. A tile map", first["text"])
        self.assertEqual([o["value"] for o in first["question"]["options"]], ["grid_world", "free_world", "layered_scene", "screen_space"])
        self.assertFalse(first["complete"])

    def test_the_questions_that_follow_depend_on_the_world_kind(self):
        wizard.answer(self.root, "world_kind", "screen_space")
        asked = [q["id"] for q in wizard.applicable(wizard.load_answers(self.root))]
        self.assertIn("screen_size", asked)
        self.assertNotIn("viewpoint", asked)
        self.assertNotIn("directions", asked)
        wizard.answer(self.root, "world_kind", "grid_world")
        asked = [q["id"] for q in wizard.applicable(wizard.load_answers(self.root))]
        self.assertIn("viewpoint", asked)
        self.assertNotIn("screen_size", asked)

    def test_the_looks_offered_are_the_ones_that_suit_the_world(self):
        wizard.answer(self.root, "world_kind", "screen_space")
        values = [o["value"] for o in wizard.question("look", wizard.load_answers(self.root))["options"]]
        self.assertIn("flat_vector", values)
        self.assertIn(wizard.OTHER, values)

    def test_an_existing_games_current_setting_is_marked_but_never_counted_as_an_answer(self):
        kit.write_settings(self.root, animation={"preferred_method": "frame_based", "animated_attachment_anchors": True})
        wizard.answer(self.root, "world_kind", "grid_world")
        shown = wizard.show(self.root)
        movement = next(q for q in shown["questions"] if q["question"]["id"] == "animation")
        self.assertEqual(movement["current"], "frame_based")
        self.assertIn("(current setting)", movement["text"])
        self.assertIn("animation", shown["unanswered"])


class AnswerTests(GameCase):
    def test_an_answer_must_be_one_of_the_options(self):
        with self.assertRaisesRegex(ValueError, "not one of the options"):
            wizard.answer(self.root, "world_kind", "voxel")
        self.assertEqual(wizard.load_answers(self.root), {})

    def test_a_question_that_does_not_apply_yet_is_refused(self):
        with self.assertRaisesRegex(ValueError, "does not apply"):
            wizard.answer(self.root, "tile_size", "32x32")

    def test_choices_that_need_the_owners_words_refuse_to_go_without(self):
        run(self.root, PLANS["grid_world"][:3])
        for name, value in (("tile_size", wizard.OTHER), ("image_generator", "connected_tool"), ("palette", "words"), ("engine", wizard.OTHER)):
            with self.subTest(name), self.assertRaisesRegex(ValueError, "own words|WIDTHxHEIGHT"):
                wizard.answer(self.root, name, value)
        with self.assertRaisesRegex(ValueError, "WIDTHxHEIGHT"):
            wizard.answer(self.root, "tile_size", wizard.OTHER, "big")

    def test_changing_the_world_kind_resets_only_the_questions_that_depend_on_it(self):
        run(self.root, PLANS["grid_world"])
        wizard.answer(self.root, "world_kind", "free_world")
        answers = wizard.load_answers(self.root)
        self.assertNotIn("look", answers)
        self.assertNotIn("viewpoint", answers)
        self.assertNotIn("tile_size", answers)
        self.assertIn("animation", answers)  # independent of the world kind
        self.assertIn("engine", answers)

    def test_choosing_the_same_thing_again_keeps_the_answers_that_depend_on_it(self):
        run(self.root, PLANS["grid_world"])
        wizard.answer(self.root, "world_kind", "grid_world")
        self.assertIn("look", wizard.load_answers(self.root))


class FinishTests(GameCase):
    def test_nothing_is_written_until_every_question_is_answered_and_the_open_ones_are_named(self):
        run(self.root, PLANS["grid_world"][:-2])
        self.assertFalse((self.root / ".gamearts" / "project.json").exists())  # no placeholder settings exist
        with self.assertRaisesRegex(ValueError, "engine, palette|palette"):
            wizard.finish(self.root)
        self.assertFalse((self.root / ".gamearts" / "project.json").exists())

    def test_every_world_kind_finishes_into_settings_the_schema_accepts(self):
        for kind, plan in PLANS.items():
            with self.subTest(kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                run(root, plan)
                self.assertTrue(wizard.status(root)["complete"])
                result = wizard.finish(root)
                self.assertEqual(result["settings_status"], "inferred")
                checked = life.check_settings(root)
                self.assertEqual(checked["status"], "valid")
                self.assertTrue(checked["setup"]["complete"])
                self.assertFalse(checked["owner_confirmed"])

    def test_the_answers_are_what_ends_up_in_the_settings(self):
        run(self.root, PLANS["grid_world"])
        wizard.finish(self.root)
        saved = self.settings()
        self.assertEqual((saved["world"]["ground_tile_px"], saved["world"]["pixels_per_meter"], saved["directions"]), ([32, 32], 32, "dirs_4"))
        self.assertEqual((saved["art_style"]["preset"], saved["image_generation"]["tool"], saved["engine_target"]["profile"]), ("pixel_mid", "user_supplied", "generic"))
        self.assertEqual(saved["art_style"]["palette_reference"], "no fixed palette (the owner's choice)")

    def test_the_owners_own_words_and_custom_sizes_are_kept(self):
        plan = [("project_name", "name", "Iso Demo"), ("world_kind", "grid_world", None), ("look", "pixel_hd", None), ("viewpoint", "isometric", "2:1 dimetric, about 26.57 degrees"),
                ("tile_size", "other", "96x48"), ("directions", "per_object", None), ("animation", "frame_based", None),
                ("image_generator", "connected_tool", "SomeTool"), ("engine", "other", "Bevy"), ("palette", "words", "warm earth tones")]
        run(self.root, plan)
        wizard.finish(self.root)
        saved = self.settings()
        self.assertEqual(saved["world"]["ground_tile_px"], [96, 48])
        self.assertIn("26.57", saved["world"]["object_camera"])
        self.assertEqual(saved["image_generation"], {"tool": "connected_tool", "tool_name": "SomeTool"})
        self.assertEqual(saved["engine_target"]["profile"], "bevy")
        self.assertEqual(saved["directions"], "dirs_8")  # "decide per object" is saved as the eight, as the master says
        self.assertEqual(saved["art_style"]["palette_reference"], "warm earth tones")

    def test_every_answer_changes_the_settings_so_none_is_accepted_and_ignored(self):
        for kind, plan in PLANS.items():
            with self.subTest(kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                run(root, plan)
                wizard.finish(root)
                baseline = common.read_json(root / ".gamearts" / "project.json")
                for name in ("animation", "image_generator", "engine"):
                    answers = wizard.load_answers(root)
                    alternatives = [o["value"] for o in wizard.question(name, answers)["options"] if o["value"] not in (answers[name]["value"], wizard.OTHER, "connected_tool")]
                    wizard.answer(root, name, alternatives[0])
                    wizard.finish(root)
                    changed = common.read_json(root / ".gamearts" / "project.json")
                    self.assertNotEqual({k: v for k, v in changed.items() if k != "setup"}, {k: v for k, v in baseline.items() if k != "setup"}, f"{kind}: {name}")
                    baseline = changed

    def test_a_confirmed_game_whose_settings_change_needs_review_and_an_unchanged_one_keeps_its_confirmation(self):
        run(self.root, PLANS["grid_world"])
        wizard.finish(self.root)
        life.confirm_settings(self.root, "owner", "yes, confirmed")
        wizard.finish(self.root)
        self.assertEqual(self.settings()["settings_status"], "owner_confirmed")
        wizard.answer(self.root, "look", "pixel_low")
        wizard.finish(self.root)
        saved = self.settings()
        self.assertEqual(saved["settings_status"], "needs_review")
        self.assertNotIn("confirmed_at", saved)


class ConfirmGateTests(GameCase):
    def test_settings_the_wizard_did_not_write_cannot_be_confirmed(self):
        kit.write_settings(self.root, drop=("confirmed_by", "confirmed_at"), settings_status="inferred")
        with self.assertRaisesRegex(ValueError, "cannot be confirmed.*setup wizard"):
            life.confirm_settings(self.root, "owner", "yes")
        self.assertEqual(self.settings()["settings_status"], "inferred")
        checked = life.check_settings(self.root)
        self.assertFalse(checked["setup"]["complete"])

    def test_settings_with_a_missing_answer_cannot_be_confirmed(self):
        run(self.root, PLANS["screen_space"])
        wizard.finish(self.root)
        settings = self.settings()
        del settings["setup"]["answers"]["palette"]
        common.atomic_write_json(self.root / ".gamearts" / "project.json", settings)
        with self.assertRaisesRegex(ValueError, "setting not answered: palette"):
            life.confirm_settings(self.root, "owner", "yes")

    def test_settings_the_wizard_wrote_are_confirmed_with_the_owners_words(self):
        run(self.root, PLANS["screen_space"])
        wizard.finish(self.root)
        self.assertTrue(life.confirm_settings(self.root, "owner", "yes, confirmed")["owner_confirmed"])


class CommandTests(GameCase):
    def call(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *arguments, "--game-root", str(self.root)], capture_output=True, text=True)

    def test_the_game_is_named_by_an_answer_and_the_name_becomes_the_project_id(self):
        run(self.root, PLANS["screen_space"])
        wizard.answer(self.root, "project_name", "name", "Sunny  Farm")
        wizard.finish(self.root)
        self.assertEqual(self.settings()["project_id"], "sunny-farm")
        with self.assertRaisesRegex(ValueError, "cannot be a project name"):
            wizard.answer(self.root, "project_name", "name", "Sunny/Farm!")
        with self.assertRaisesRegex(ValueError, "own words"):
            wizard.answer(self.root, "project_name", "name")

    def test_the_command_shows_the_next_question_records_an_answer_and_refuses_a_bad_one(self):
        shown = json.loads(self.call("next").stdout)
        self.assertEqual(shown["question"]["id"], "project_name")
        self.assertEqual(self.call("answer", "--id", "project_name", "--value", "name", "--text", "Demo").returncode, 0)
        done = self.call("answer", "--id", "world_kind", "--value", "screen_space")
        self.assertEqual(done.returncode, 0, done.stderr)
        bad = self.call("answer", "--id", "look", "--value", "nonsense")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("not one of the options", bad.stderr)
        self.assertEqual(json.loads(self.call("status").stdout)["complete"], False)
        self.assertEqual(json.loads(self.call("show").stdout)["questions"][1]["answered"]["value"], "screen_space")


if __name__ == "__main__":
    unittest.main()
