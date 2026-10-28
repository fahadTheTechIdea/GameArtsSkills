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
    "free_world": [("world_kind", "free_world", None), ("look", "painterly", None), ("soft_edges", "hard", None), ("viewpoint", "side", None), ("scale", "64", None),
                   ("directions", "dirs_2_side", None)] + COMMON,
    "layered_scene": [("world_kind", "layered_scene", None), ("look", "painterly", None), ("soft_edges", "hard", None), ("viewpoint", "side", None), ("scale", "32", None),
                      ("layers", "5", None), ("directions", "dirs_2_side", None)] + COMMON,
    "screen_space": [("world_kind", "screen_space", None), ("look", "flat_vector", None), ("soft_edges", "matte", None), ("screen_size", "1920x1080", None),
                     ("screen_scaling", "fit", None)] + COMMON,
}


def choose(root, name, value, text=None, said="the owner's own words"):
    return wizard.answer(root, name, value, text, said)


def confirm(root, who="owner", words="yes, confirmed"):
    """Confirm the way the skill does: with the version the owner was shown."""
    return life.confirm_settings(root, who, words, wizard.version((common.read_json(Path(root) / ".gamearts" / "project.json").get("setup") or {}).get("answers") or {}))


def run(root, plan):
    for name, value, text in plan:
        choose(root, name, value, text)


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
        choose(self.root, "project_name", "name", "Demo")
        first = wizard.next_question(self.root)
        self.assertEqual(first["question"]["id"], "world_kind")
        self.assertIn("What kind of world", first["text"])
        self.assertIn("1. A tile map", first["text"])
        self.assertEqual([o["value"] for o in first["question"]["options"]], ["grid_world", "free_world", "layered_scene", "screen_space"])
        self.assertFalse(first["complete"])

    def test_the_questions_that_follow_depend_on_the_world_kind(self):
        choose(self.root, "world_kind", "screen_space")
        asked = [q["id"] for q in wizard.applicable(wizard.load_answers(self.root))]
        self.assertIn("screen_size", asked)
        self.assertNotIn("viewpoint", asked)
        self.assertNotIn("directions", asked)
        choose(self.root, "world_kind", "grid_world")
        asked = [q["id"] for q in wizard.applicable(wizard.load_answers(self.root))]
        self.assertIn("viewpoint", asked)
        self.assertNotIn("screen_size", asked)

    def test_the_looks_offered_are_the_ones_that_suit_the_world(self):
        choose(self.root, "world_kind", "screen_space")
        values = [o["value"] for o in wizard.question("look", wizard.load_answers(self.root))["options"]]
        self.assertIn("flat_vector", values)
        self.assertIn(wizard.OTHER, values)

    def test_an_existing_games_current_setting_is_marked_but_never_counted_as_an_answer(self):
        kit.write_settings(self.root, animation={"preferred_method": "frame_based", "animated_attachment_anchors": True})
        choose(self.root, "world_kind", "grid_world")
        shown = wizard.show(self.root)
        movement = next(q for q in shown["questions"] if q["question"]["id"] == "animation")
        self.assertEqual(movement["current"], "frame_based")
        self.assertIn("(current setting)", movement["text"])
        self.assertIn("animation", shown["unanswered"])


class AnswerTests(GameCase):
    def test_an_answer_must_be_one_of_the_options(self):
        with self.assertRaisesRegex(ValueError, "not one of the options"):
            choose(self.root, "world_kind", "voxel")
        self.assertEqual(wizard.load_answers(self.root), {})

    def test_a_question_that_does_not_apply_yet_is_refused(self):
        with self.assertRaisesRegex(ValueError, "does not apply"):
            choose(self.root, "tile_size", "32x32")

    def test_choices_that_need_the_owners_words_refuse_to_go_without(self):
        run(self.root, PLANS["grid_world"][:3])
        for name, value in (("tile_size", wizard.OTHER), ("image_generator", "connected_tool"), ("palette", "words"), ("engine", wizard.OTHER)):
            with self.subTest(name), self.assertRaisesRegex(ValueError, "own words|WIDTHxHEIGHT"):
                choose(self.root, name, value)
        with self.assertRaisesRegex(ValueError, "WIDTHxHEIGHT"):
            choose(self.root, "tile_size", wizard.OTHER, "big")

    def test_an_engine_the_owner_names_is_checked_when_they_answer_and_kept_as_a_profile_name(self):
        run(self.root, PLANS["grid_world"][:5])
        for bad in ("Godot 4.2", "C++ engine", "ünity"):
            with self.subTest(bad), self.assertRaisesRegex(ValueError, "cannot be an engine name"):
                choose(self.root, "engine", wizard.OTHER, bad)
        self.assertNotIn("engine", wizard.load_answers(self.root))
        run(self.root, [x for x in PLANS["grid_world"][5:] if x[0] != "engine"] + [("engine", wizard.OTHER, "Godot 4")])
        wizard.finish(self.root)
        self.assertEqual(self.settings()["engine_target"]["profile"], "godot-4")

    def test_a_palette_picture_that_is_missing_or_not_a_picture_is_refused_when_named_not_when_the_settings_are_written(self):
        run(self.root, PLANS["grid_world"][:3])
        with self.assertRaisesRegex(ValueError, "is not a file"):
            choose(self.root, "palette", "picture", "missing.png")
        (self.root / "notes.png").write_text("not a picture", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot be read as a picture"):
            choose(self.root, "palette", "picture", "notes.png")
        self.assertNotIn("palette", wizard.load_answers(self.root))

    def test_an_existing_games_settings_are_marked_on_every_question_that_has_one(self):
        for kind, plan in PLANS.items():
            root = self.root / kind
            run(root, plan)
            wizard.finish(root)
            fresh = self.root / (kind + "_again")                 # a new wizard over the finished game: nothing answered, the settings are the only memory
            (fresh / ".gamearts").mkdir(parents=True)
            (fresh / ".gamearts" / "project.json").write_bytes((root / ".gamearts" / "project.json").read_bytes())
            held = common.read_json(fresh / ".gamearts" / "project.json")
            picked = {name: value for name, value, _ in plan if name not in ("project_name", "image_generator", "engine")}
            marked = {name: wizard._current(fresh, name) for name in picked}
            for name, value in picked.items():
                with self.subTest(kind=kind, question=name):
                    self.assertEqual(marked[name], value, (held.get("world"), held.get("screen")))

    def test_a_palette_from_a_picture_and_one_from_words_are_marked_as_what_they_were(self):
        from PIL import Image
        Image.new("RGB", (4, 1), (200, 30, 30)).save(self.root / "colours.png")
        for choice, text, expected in (("picture", "colours.png", "picture"), ("words", "warm earth tones", "words")):
            root = self.root / choice
            root.mkdir()
            Image.new("RGB", (4, 1), (200, 30, 30)).save(root / "colours.png")
            run(root, [x for x in PLANS["grid_world"] if x[0] != "palette"] + [("palette", choice, text)])
            wizard.finish(root)
            self.assertEqual(wizard._current(root, "palette"), expected)

    def test_changing_the_world_kind_resets_only_the_questions_that_depend_on_it(self):
        run(self.root, PLANS["grid_world"])
        choose(self.root, "world_kind", "free_world")
        answers = wizard.load_answers(self.root)
        self.assertNotIn("look", answers)
        self.assertNotIn("viewpoint", answers)
        self.assertNotIn("tile_size", answers)
        self.assertIn("animation", answers)  # independent of the world kind
        self.assertIn("engine", answers)

    def test_choosing_the_same_thing_again_keeps_the_answers_that_depend_on_it(self):
        run(self.root, PLANS["grid_world"])
        choose(self.root, "world_kind", "grid_world")
        self.assertIn("look", wizard.load_answers(self.root))


class OwnerWordsTests(GameCase):
    def test_every_pick_needs_the_owners_own_words_and_they_are_kept(self):
        for said in (None, "", "   "):
            with self.subTest(said=said), self.assertRaisesRegex(ValueError, "own words"):
                wizard.answer(self.root, "project_name", "name", "Demo", said)
        self.assertEqual(wizard.load_answers(self.root), {})
        choose(self.root, "project_name", "name", "Demo", "call it Demo please")
        self.assertEqual(wizard.load_answers(self.root)["project_name"]["said"], "call it Demo please")
        self.assertEqual(wizard.show(self.root)["questions"][0]["answered"]["said"], "call it Demo please")

    def test_the_words_for_an_unchanged_pick_are_recorded_without_resetting_what_depends_on_it(self):
        run(self.root, PLANS["grid_world"])
        wizard.finish(self.root)
        answers = wizard.load_answers(self.root)
        del answers["world_kind"]["said"]
        common.atomic_write_json(wizard.state_path(self.root), {"schema_version": "1.0", "answers": answers})
        self.assertIn("look", wizard.load_answers(self.root))
        choose(self.root, "world_kind", "grid_world", None, "a tile map, as I said")
        after = wizard.load_answers(self.root)
        self.assertEqual(after["world_kind"]["said"], "a tile map, as I said")
        self.assertIn("look", after)  # nothing that depends on the world kind was reset
        self.assertIn("tile_size", after)

    def test_settings_missing_the_words_behind_a_pick_cannot_be_confirmed(self):
        run(self.root, PLANS["screen_space"])
        wizard.finish(self.root)
        settings = self.settings()
        del settings["setup"]["answers"]["animation"]["said"]
        common.atomic_write_json(self.root / ".gamearts" / "project.json", settings)
        with self.assertRaisesRegex(ValueError, "no owner words recorded for: animation"):
            confirm(self.root)


class VersionTests(GameCase):
    def finished(self):
        run(self.root, PLANS["screen_space"])
        return wizard.finish(self.root)

    def test_the_version_is_short_stable_and_names_exactly_these_picks(self):
        first = self.finished()["version"]
        self.assertRegex(first, "^[0-9a-f]{12}$")
        self.assertEqual(wizard.status(self.root)["version"], first)
        self.assertEqual(life.check_settings(self.root)["setup"]["version"], first)
        choose(self.root, "animation", "hybrid", None, "different words, same pick")  # same pick, other words: same version
        self.assertEqual(wizard.status(self.root)["version"], first)
        choose(self.root, "animation", "frame_based")
        self.assertNotEqual(wizard.status(self.root)["version"], first)

    def test_a_confirmation_must_cite_the_version_the_owner_was_shown(self):
        shown = self.finished()["version"]
        for wrong in (None, "", "000000000000"):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, "version shown to the owner"):
                life.confirm_settings(self.root, "owner", "yes", wrong)
        self.assertEqual(self.settings()["settings_status"], "inferred")
        self.assertTrue(life.confirm_settings(self.root, "owner", "yes", shown)["owner_confirmed"])

    def test_settings_changed_after_the_owner_was_shown_the_version_are_refused(self):
        shown = self.finished()["version"]
        settings = self.settings()
        settings["setup"]["answers"]["animation"]["value"] = "frame_based"  # edited behind the owner's back
        common.atomic_write_json(self.root / ".gamearts" / "project.json", settings)
        with self.assertRaisesRegex(ValueError, "version shown to the owner"):
            life.confirm_settings(self.root, "owner", "yes", shown)


class SoftEdgeTests(GameCase):
    def test_a_look_with_soft_edges_asks_what_to_do_about_them_and_a_hard_edged_look_does_not(self):
        choose(self.root, "project_name", "name", "Demo")
        choose(self.root, "world_kind", "screen_space")
        choose(self.root, "look", "pixel_mid")
        self.assertNotIn("soft_edges", [q["id"] for q in wizard.applicable(wizard.load_answers(self.root))])
        choose(self.root, "look", "flat_vector")
        asked = wizard.question("soft_edges", wizard.load_answers(self.root))
        self.assertIn("soft painted edges", asked["prompt"])
        self.assertEqual([o["value"] for o in asked["options"]], ["hard", "matte"])
        self.assertIn("soft_edges", wizard.unanswered(wizard.load_answers(self.root)))

    def test_a_look_in_the_owners_own_words_is_asked_too(self):
        choose(self.root, "world_kind", "screen_space")
        choose(self.root, "look", wizard.OTHER, "chalk on slate")
        self.assertIn("soft_edges", [q["id"] for q in wizard.applicable(wizard.load_answers(self.root))])

    def test_the_answer_is_recorded_as_a_constraint_and_follows_a_change_of_look(self):
        run(self.root, PLANS["screen_space"])
        wizard.finish(self.root)
        self.assertIn("companion matte", " ".join(self.settings()["prompting"]["additional_constraints"]))
        choose(self.root, "look", "pixel_mid")
        self.assertNotIn("soft_edges", wizard.load_answers(self.root))  # a hard-edged look has nothing to decide
        wizard.finish(self.root)
        self.assertNotIn("prompting", self.settings())


class SummaryTests(GameCase):
    def test_finish_shows_the_picks_in_plain_words_with_what_each_means_and_every_possible_question(self):
        run(self.root, PLANS["grid_world"])
        result = wizard.finish(self.root)
        text = " ".join(result["summary"])
        self.assertIn("World: A tile map", text)
        self.assertIn("generates no pictures", text)  # what user_supplied means
        self.assertIn("plain guidance for any engine", text)
        possible = wizard.show(self.root)["possible"]
        self.assertEqual([item["id"] for item in possible], wizard.ORDER)
        self.assertIn("after the viewpoint", next(item["appears"] for item in possible if item["id"] == "tile_size"))


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
                ("image_generator", "connected_tool", "SomeTool"), ("image_fallback", "none", None), ("engine", "other", "Bevy"), ("palette", "words", "warm earth tones")]
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
                    choose(root, name, alternatives[0])
                    if name == "image_generator":
                        choose(root, "image_fallback", "none")  # a tool that generates asks what to use when it is unavailable
                    wizard.finish(root)
                    changed = common.read_json(root / ".gamearts" / "project.json")
                    self.assertNotEqual({k: v for k, v in changed.items() if k != "setup"}, {k: v for k, v in baseline.items() if k != "setup"}, f"{kind}: {name}")
                    baseline = changed

    def test_a_confirmed_game_whose_settings_change_needs_review_and_an_unchanged_one_keeps_its_confirmation(self):
        run(self.root, PLANS["grid_world"])
        wizard.finish(self.root)
        confirm(self.root)
        wizard.finish(self.root)
        self.assertEqual(self.settings()["settings_status"], "owner_confirmed")
        choose(self.root, "look", "pixel_low")
        wizard.finish(self.root)
        saved = self.settings()
        self.assertEqual(saved["settings_status"], "needs_review")
        self.assertNotIn("confirmed_at", saved)


class ConfirmGateTests(GameCase):
    def test_settings_the_wizard_did_not_write_cannot_be_confirmed(self):
        kit.write_settings(self.root, drop=("confirmed_by", "confirmed_at"), settings_status="inferred")
        with self.assertRaisesRegex(ValueError, "cannot be confirmed.*setup wizard"):
            confirm(self.root)
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
            confirm(self.root)

    def test_settings_the_wizard_wrote_are_confirmed_with_the_owners_words(self):
        run(self.root, PLANS["screen_space"])
        wizard.finish(self.root)
        self.assertTrue(confirm(self.root)["owner_confirmed"])


class ImageFallbackTests(GameCase):
    """The owner's second choice of image generator: asked after the first (never when they make the pictures themselves), saved with it, never assumed."""

    def after_generator(self, value, text=None):
        run(self.root, [("project_name", "name", "Demo Game"), ("world_kind", "grid_world", None), ("look", "pixel_mid", None), ("viewpoint", "oblique", None),
                        ("tile_size", "32x32", None), ("directions", "dirs_4", None), ("animation", "hybrid", None), ("image_generator", value, text)])

    def test_it_is_asked_after_a_generating_tool_with_none_among_the_choices_and_the_main_tool_left_out(self):
        self.after_generator("built_in_image_gen")
        asked = wizard.next_question(self.root)["question"]
        self.assertEqual(asked["id"], "image_fallback")
        values = [o["value"] for o in asked["options"]]
        self.assertEqual(values, ["none", "cli_image_gen", "connected_tool"])

    def test_it_is_not_asked_when_the_owner_makes_the_pictures(self):
        self.after_generator("user_supplied")
        self.assertNotEqual(wizard.next_question(self.root)["question"]["id"], "image_fallback")
        self.assertNotIn("image_fallback", wizard.unanswered(wizard.load_answers(self.root)))

    def test_a_named_connected_fallback_is_saved_beside_the_main_tool(self):
        self.after_generator("built_in_image_gen")
        with self.assertRaisesRegex(ValueError, "own words"):
            choose(self.root, "image_fallback", "connected_tool")
        choose(self.root, "image_fallback", "connected_tool", "SpriteCook (gpt-image 2.5)")
        run(self.root, [("engine", "generic", None), ("palette", "none", None)])
        wizard.finish(self.root)
        saved = common.read_json(self.root / ".gamearts" / "project.json")
        self.assertEqual(saved["image_generation"], {"tool": "built_in_image_gen", "fallback": {"tool": "connected_tool", "tool_name": "SpriteCook (gpt-image 2.5)"}})
        self.assertEqual(wizard._current(self.root, "image_fallback"), "connected_tool")

    def test_no_fallback_is_saved_as_none_and_never_assumed(self):
        self.after_generator("built_in_image_gen")
        self.assertIn("image_fallback", wizard.unanswered(wizard.load_answers(self.root)))
        choose(self.root, "image_fallback", "none")
        run(self.root, [("engine", "generic", None), ("palette", "none", None)])
        wizard.finish(self.root)
        self.assertEqual(common.read_json(self.root / ".gamearts" / "project.json")["image_generation"], {"tool": "built_in_image_gen"})
        self.assertTrue(any("never uses another" in line for line in wizard.summary(wizard.load_answers(self.root))))


class ContractTests(GameCase):
    """What other tools build on (the Storyboard framework drives the wizard and reads check-settings): the names here change only with a notice."""

    def test_the_question_ids_and_the_shape_of_next_are_stable(self):
        self.assertEqual(wizard.ORDER, ["project_name", "world_kind", "look", "soft_edges", "viewpoint", "tile_size", "scale", "layers", "screen_size",
                                        "screen_scaling", "directions", "animation", "image_generator", "image_fallback", "engine", "palette"])
        asked = wizard.next_question(self.root)
        self.assertEqual(set(asked) >= {"question", "complete", "text", "progress"}, True)
        self.assertEqual(set(asked["question"]) >= {"id", "prompt", "options"}, True)
        self.assertTrue(all("value" in option and "label" in option for option in asked["question"]["options"]))
        self.assertEqual(wizard.next_question(self.root)["complete"], False)

    def test_check_settings_keeps_the_fields_other_tools_read(self):
        run(self.root, PLANS["screen_space"])
        wizard.finish(self.root)
        confirm(self.root)
        checked = life.check_settings(self.root)
        for field in ("status", "settings_status", "owner_confirmed", "material_settings_sha256", "world_kind", "engine_target", "image_generation", "setup"):
            self.assertIn(field, checked)
        self.assertEqual((checked["status"], checked["owner_confirmed"]), ("valid", True))
        saved = self.settings()
        for field in ("project_id", "image_generation", "engine_target"):
            self.assertIn(field, saved)

    def test_a_framework_installed_in_a_parent_folder_serves_a_nested_game(self):
        nested = self.root / "stories" / "one"
        nested.mkdir(parents=True)
        run(nested, PLANS["screen_space"])
        wizard.finish(nested)
        self.assertEqual(life.check_settings(nested)["status"], "valid")
        self.assertFalse((self.root / ".gamearts").exists())  # nothing was written at the parent


class CommandTests(GameCase):
    def call(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *arguments, "--game-root", str(self.root)], capture_output=True, text=True)

    def test_the_game_is_named_by_an_answer_and_the_name_becomes_the_project_id(self):
        run(self.root, PLANS["screen_space"])
        choose(self.root, "project_name", "name", "Sunny  Farm")
        wizard.finish(self.root)
        self.assertEqual(self.settings()["project_id"], "sunny-farm")
        with self.assertRaisesRegex(ValueError, "cannot be a project name"):
            choose(self.root, "project_name", "name", "Sunny/Farm!")
        with self.assertRaisesRegex(ValueError, "own words"):
            choose(self.root, "project_name", "name")

    def test_the_command_shows_the_next_question_records_an_answer_and_refuses_a_bad_one(self):
        shown = json.loads(self.call("next").stdout)
        self.assertEqual(shown["question"]["id"], "project_name")
        self.assertEqual(self.call("answer", "--id", "project_name", "--value", "name", "--text", "Demo", "--said", "call it Demo").returncode, 0)
        done = self.call("answer", "--id", "world_kind", "--value", "screen_space", "--said", "no ground, just screens")
        self.assertEqual(done.returncode, 0, done.stderr)
        bad = self.call("answer", "--id", "look", "--value", "nonsense", "--said", "x")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("not one of the options", bad.stderr)
        self.assertEqual(json.loads(self.call("status").stdout)["complete"], False)
        self.assertEqual(json.loads(self.call("show").stdout)["questions"][1]["answered"]["value"], "screen_space")


if __name__ == "__main__":
    unittest.main()
