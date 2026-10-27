"""Engine switching is safe (plan A14.6): changing the engine a game targets changes guidance and default exports, never the art, a gate or an approval."""
import json
import unittest
from pathlib import Path

import gamearts_testkit  # noqa: F401  (puts scripts/ on sys.path)
from gamearts_testkit import write_settings

import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_presets as presets  # noqa: E402
from test_lifecycle_operations import GameFolder, OUT  # noqa: E402

ENGINES = ("godot", "generic", "phaser", "unity", "defold", "gamemaker")


class SwitchCase(GameFolder):
    def switch(self, engine):
        write_settings(self.root, engine_target={"profile": engine}, art_style={"id": "pixel_art", "preset": "pixel_mid"})

    def snapshot(self):
        return {"settings": life.check_settings(self.root), "mockups": self.manifest("mockups"), "assets": self.manifest("assets")}


class ArtAndApprovalsAreUntouchedTests(SwitchCase):
    def setUp(self):
        super().setUp()
        self.switch("godot")
        source = self.approved_mockup()
        self.name = self.registered_asset(source=source)
        life.approve_asset(self.root, self.name, "approved-in-test")
        self.before = self.snapshot()
        self.bundle_digests = {p.name: common.sha256_file(p) for p in sorted((self.root / OUT / "assets/approved" / self.name).rglob("*")) if p.is_file()}

    def test_the_material_settings_hash_is_the_same_for_every_engine(self):
        for engine in ENGINES:
            with self.subTest(engine):
                self.switch(engine)
                self.assertEqual(life.check_settings(self.root)["material_settings_sha256"], self.before["settings"]["material_settings_sha256"])

    def test_switching_and_switching_back_leaves_every_record_exactly_as_it_was(self):
        for engine in ("generic", "unity", "godot"):
            self.switch(engine)
        after = self.snapshot()
        self.assertEqual((after["mockups"], after["assets"]), (self.before["mockups"], self.before["assets"]))

    def test_no_engine_makes_the_settings_need_review_or_changes_what_is_owner_confirmed(self):
        for engine in ENGINES:
            with self.subTest(engine):
                self.switch(engine)
                settings = life.check_settings(self.root)
                self.assertEqual((settings["status"], settings["owner_confirmed"], settings["settings_status"]), ("valid", True, "owner_confirmed"))
                self.assertNotIn("review_flags", json.dumps(settings))

    def test_the_approved_asset_still_audits_clean_and_stays_approved_under_every_engine(self):
        for engine in ENGINES:
            with self.subTest(engine):
                self.switch(engine)
                self.assertEqual(life.audit_asset(self.root, self.name), [])
                self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")
                self.assertEqual(self.manifest("assets")[0]["status"], "approved")
        self.assertEqual({p.name: common.sha256_file(p) for p in sorted((self.root / OUT / "assets/approved" / self.name).rglob("*")) if p.is_file()}, self.bundle_digests)

    def test_only_the_guidance_and_the_default_exports_differ(self):
        outcomes = {}
        for engine in ENGINES:
            self.switch(engine)
            check = life.check_settings(self.root)
            outcomes[engine] = (check["engine_target"]["default_exports"], bool(check["integration_notes"]), check["engine_target"]["profile"])
        self.assertEqual(outcomes["godot"][0], ["runtime"])
        self.assertEqual(outcomes["generic"][0], [])
        self.assertEqual({e: outcomes[e][2] for e in ENGINES}, {e: e for e in ENGINES})
        self.assertTrue(all(outcomes[e][1] for e in ENGINES), "every installed engine has pixel-art guidance")

    def test_the_automatic_files_follow_the_engine_and_never_touch_the_approved_art(self):
        self.switch("generic")
        self.assertEqual(life.auto_exports(self.root, self.name), {})
        self.switch("godot")
        self.assertEqual(life.auto_exports(self.root, self.name)["runtime"]["status"], "written")
        self.switch("generic")
        self.assertEqual(life.auto_exports(self.root, self.name), {})  # switching away does not delete or redo what exists
        self.assertEqual({p.name: common.sha256_file(p) for p in sorted((self.root / OUT / "assets/approved" / self.name).rglob("*")) if p.is_file()}, self.bundle_digests)
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")

    def test_an_engine_with_no_profile_works_exactly_like_generic(self):
        self.switch("not-installed")
        check = life.check_settings(self.root)
        self.assertEqual(check["material_settings_sha256"], self.before["settings"]["material_settings_sha256"])
        self.assertFalse(check["engine_target"]["found"])
        self.assertEqual(life.auto_exports(self.root, self.name), {})
        self.assertEqual(life.audit_asset(self.root, self.name), [])


class EveryProfileTests(unittest.TestCase):
    def test_every_installed_profile_is_selectable_and_resolves(self):
        for name in presets.engine_profiles():
            result = presets.resolve_engine_target({"engine_target": {"profile": name}})
            self.assertTrue(result["found"], name)
            self.assertIn("default_exports", result)


if __name__ == "__main__":
    unittest.main()
