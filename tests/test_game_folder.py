"""A game's settings and art are kept in the game's own folder, never in the framework's.

The framework may be installed inside a game (a copy without the maintainers' plans folder) or live somewhere else; either way the game's
`.gamearts` state belongs to the game. Every stage takes its game root through `common.game_root`, which refuses the framework's own source
checkout and the folders skills are installed in, and these tests drive the stages against such folders.
"""
import re
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_disclosure as disclosure  # noqa: E402
import gamearts_doctor as doctor  # noqa: E402
import gamearts_plan_card as card  # noqa: E402
import gamearts_report as report  # noqa: E402
import gamearts_setup as wizard  # noqa: E402
import gamearts_storyboard as storyboard  # noqa: E402
import prepare_reference_crop as crop  # noqa: E402
import sync_local_agents  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REFUSED = "framework's own source folder"


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


class FolderCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def source_checkout(self, name="framework"):
        """A folder that looks like the maintainers' checkout: the tree that holds the plans and the common module."""
        folder = self.tmp / name
        for marker in common.FRAMEWORK_SOURCE_MARKERS:
            touch(folder / marker)
        return folder


class WhatIsAGameFolderTests(FolderCase):
    def test_this_repository_is_recognised_as_the_framework_source(self):
        self.assertIn(REFUSED, common.not_a_game_folder(ROOT))  # the markers match the real layout, so renaming one fails here

    def test_a_copy_of_the_framework_installed_inside_a_game_is_still_a_game(self):
        game = self.tmp / "my_game"
        touch(game / "scripts" / "gamearts_common.py")  # the installed scripts; the plans folder never ships
        touch(game / "GAME_ARTS_MASTER_STANDARD.md")
        self.assertIsNone(common.not_a_game_folder(game))
        self.assertEqual(common.game_root(game), game.resolve())

    def test_an_ordinary_game_folder_beside_the_framework_is_a_game(self):
        self.source_checkout()
        game = self.tmp / "my_game"
        game.mkdir()
        self.assertIsNone(common.not_a_game_folder(game))

    def test_the_source_checkout_and_the_folders_state_and_skills_live_in_are_refused(self):
        source = self.source_checkout()
        self.assertIn(REFUSED, common.not_a_game_folder(source))
        for parts in ((".gamearts",), (".claude", "skills"), (".agents", "skills")):
            with self.subTest(parts=parts):
                folder = self.tmp.joinpath("game", *parts, "inner")
                folder.mkdir(parents=True)
                self.assertIn("/".join(parts), common.not_a_game_folder(folder))
                with self.assertRaisesRegex(ValueError, "not a game's folder"):
                    common.game_root(folder)


class EveryStageTests(FolderCase):
    """Each stage that reads or writes a game's state refuses the framework's source checkout and creates nothing in it."""

    def entry_points(self):
        return {
            "load the settings": lambda root: common.load_project_settings(root),
            "setup: show": lambda root: wizard.show(root),
            "setup: answer": lambda root: wizard.answer(root, "project_name", "name", "Demo Game", "said"),
            "setup: finish": lambda root: wizard.finish(root),
            "lifecycle: check settings": lambda root: life.check_settings(root),
            "lifecycle: reconcile": lambda root: life.reconcile_mockups(root),
            "lifecycle: list": lambda root: life.list_records(root, "assets", None),
            "report": lambda root: report.build(root),
            "plan card": lambda root: card.plan(root, "static_structure"),
            "storyboard": lambda root: storyboard.exists(root),
            "disclosure": lambda root: disclosure.build(root),
            "install the framework": lambda root: sync_local_agents.sync(ROOT, root),
        }

    def test_each_stage_refuses_the_framework_source_and_creates_nothing_there(self):
        source = self.source_checkout()
        before = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))
        for name, call in self.entry_points().items():
            with self.subTest(stage=name), self.assertRaisesRegex(ValueError, REFUSED):
                call(source)
        self.assertEqual(sorted(path.relative_to(source).as_posix() for path in source.rglob("*")), before)
        self.assertFalse((source / ".gamearts").exists())

    def test_the_same_stages_work_for_a_real_game_folder(self):
        self.source_checkout()
        game = self.tmp / "my_game"
        write_settings(game)
        self.assertEqual(life.check_settings(game)["status"], "valid")
        self.assertTrue(wizard.show(game)["questions"])
        self.assertFalse(storyboard.exists(game))

    def test_finding_the_game_above_a_packet_refuses_a_source_checkout_that_has_a_gamearts_folder(self):
        source = self.source_checkout()
        (source / ".gamearts").mkdir()
        with self.assertRaisesRegex(ValueError, REFUSED):
            crop.find_game_root(source / "scripts")

    def test_the_doctor_says_so_instead_of_failing(self):
        source = self.source_checkout()
        result = doctor.run(source)
        folder = next(item for item in result["checks"] if item["name"] == "game folder")
        self.assertEqual(folder["status"], "fail")
        self.assertIn(REFUSED, folder["detail"])
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(any(item["name"] == "settings" for item in result["checks"]))  # nothing was read from it

    def test_installing_the_framework_into_a_game_makes_a_game_not_a_second_source_checkout(self):
        game = self.tmp / "my_game"
        game.mkdir()
        sync_local_agents.sync(ROOT, game)
        self.assertTrue((game / "scripts" / "gamearts_common.py").is_file())
        self.assertFalse((game / "plans").exists())  # the maintainers' plans never ship
        self.assertIsNone(common.not_a_game_folder(game))


class NoStageSkipsTheGuardTests(unittest.TestCase):
    """The stages above are the ones named here; this keeps a new one from resolving a game root by hand."""

    BY_HAND = re.compile(r"Path\((?:args\.)?game_root\)\.resolve\(\)|args\.game_root\.(?:expanduser\(\)\.)?resolve\(\)")
    ROUTED = re.compile(r"common\.game_root\(|common\.not_a_game_folder\(|load_project_settings\(|settings_fit\.announce\(")

    def test_no_script_resolves_a_game_root_by_hand_except_the_doctor_which_reports_it(self):
        offenders = [path.name for path in sorted(SCRIPTS.glob("*.py")) if path.name != "gamearts_doctor.py"
                     and self.BY_HAND.search(path.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_every_script_that_takes_a_game_root_hands_it_to_the_owner(self):
        silent = [path.name for path in sorted(SCRIPTS.glob("*.py")) if '"--game-root"' in path.read_text(encoding="utf-8")
                  and not self.ROUTED.search(path.read_text(encoding="utf-8"))]
        self.assertEqual(silent, [], "these scripts take --game-root and never pass it through common.game_root")

    def test_loading_the_settings_goes_through_the_owner(self):
        source = (SCRIPTS / "gamearts_common.py").read_text(encoding="utf-8")
        self.assertRegex(source, r'path = game_root\(root\) / "\.gamearts" / "project\.json"')


if __name__ == "__main__":
    unittest.main()
