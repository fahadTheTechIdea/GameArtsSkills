"""Confirming the settings (plan P14 finding): the real time and the owner's words are recorded by the framework, never typed by hand;
check-settings says when an isometric tile is not 2:1."""
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)
from gamearts_testkit import settings as default_settings, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_setup as wizard  # noqa: E402


class GameCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def saved(self):
        return common.read_json(self.root / ".gamearts" / "project.json")


ANSWERS = [("project_name", "name", "Demo"), ("world_kind", "screen_space", None), ("look", "flat_vector", None), ("screen_size", "1920x1080", None), ("screen_scaling", "fit", None),
           ("animation", "hybrid", None), ("image_generator", "user_supplied", None), ("engine", "generic", None), ("palette", "none", None)]


class ConfirmTests(GameCase):
    def setUp(self):
        super().setUp()
        for name, value, text in ANSWERS:  # settings the wizard wrote: confirming needs every one chosen by the owner
            wizard.answer(self.root, name, value, text)
        wizard.finish(self.root)

    def test_the_confirmation_is_stamped_with_the_real_time_and_the_owners_words(self):
        with mock.patch.object(life, "_now", return_value="2031-02-03T04:05:06.000007+00:00"):
            result = life.confirm_settings(self.root, "owner", "yes, save those")
        saved = self.saved()
        self.assertEqual((saved["settings_status"], saved["confirmed_by"], saved["confirmation_ref"]), ("owner_confirmed", "owner", "yes, save those"))
        self.assertEqual(saved["confirmed_at"], "2031-02-03T04:05:06.000007+00:00")  # the framework's clock, not a typed value
        self.assertTrue(result["owner_confirmed"])

    def test_nothing_else_in_the_settings_changes(self):
        before = common.canonical_settings_hash(self.saved())
        life.confirm_settings(self.root, "owner", "yes")
        self.assertEqual(common.canonical_settings_hash(self.saved()), before)

    def test_a_confirmation_needs_a_name_and_the_owners_words(self):
        for who, words in (("", "yes"), ("owner", ""), ("  ", "yes"), ("owner", None)):
            with self.subTest(who=who, words=words), self.assertRaisesRegex(ValueError, "never invented"):
                life.confirm_settings(self.root, who, words)
        self.assertEqual(self.saved()["settings_status"], "inferred")

    def test_a_game_with_no_settings_is_refused_and_nothing_is_created(self):
        empty = self.root / "other"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "Missing"):
            life.confirm_settings(empty, "owner", "yes")
        self.assertFalse((empty / ".gamearts" / "project.json").exists())


def iso(tile):
    return dict(default_settings()["world"], grid="isometric", camera_profile="isometric_3_4", ground_tile_px=tile)


class WarningTests(GameCase):
    def test_an_isometric_tile_that_is_not_two_to_one_is_warned_about(self):
        write_settings(self.root, world=iso([96, 32]))
        warnings = life.check_settings(self.root)["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("not 2:1", warnings[0])

    def test_a_two_to_one_isometric_tile_and_other_grids_raise_nothing(self):
        write_settings(self.root, world=iso([64, 32]))
        self.assertEqual(life.check_settings(self.root)["warnings"], [])
        write_settings(self.root)
        self.assertEqual(life.check_settings(self.root)["warnings"], [])


if __name__ == "__main__":
    unittest.main()
