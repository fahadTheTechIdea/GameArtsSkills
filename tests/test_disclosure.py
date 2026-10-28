"""The AI-content disclosure summary: built only from what was recorded, approved art only, and it writes nothing."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import make_mockup, make_sheet, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_disclosure as disclosure  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_disclosure.py"
OUT = ".gamearts/outputs"


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        write_settings(self.root)

    def mockup(self, mockup_id, approve=True):
        image, metadata = make_mockup(self.root, mockup_id, "v001", "world")
        life.register_mockup(self.root, metadata, image)
        if approve:
            life.approve_mockup(self.root, mockup_id, "v001", "approved-in-test")

    def edit(self, kind, change):
        path = self.root / OUT / "manifests" / f"{kind}.json"
        body = common.read_json(path)
        change(body)
        path.write_text(json.dumps(body), encoding="utf-8")

    def asset(self, asset_id, source, approved=True):
        name = f"{asset_id}_v001"
        folder = self.root / OUT / "assets/generated" / name
        folder.mkdir(parents=True)
        make_sheet(folder, f"{name}_sheet", asset_id)
        life.register_asset(self.root, name, "v001", f"{OUT}/assets/generated/{name}", [(source, "v001")])
        if approved:
            self.edit("assets", lambda body: body["assets"][-1].update(status="approved"))


class SummaryTests(Case):
    def test_a_game_with_nothing_recorded_reports_nothing_and_still_says_what_it_cannot_know(self):
        result = disclosure.build(self.root)
        self.assertEqual((result["mockups"], result["assets"], result["tools"]), ([], [], []))
        self.assertTrue(result["not_covered"])

    def test_a_generated_mockup_is_ai_generated_with_its_tool_and_a_supplied_one_is_not(self):
        self.mockup("market")
        self.mockup("logo")
        self.edit("mockups", lambda body: [r.update(tool_mode="external_import") for r in body["mockups"] if r["mockup_id"] == "logo"])
        result = disclosure.build(self.root)
        origins = {m["id"]: m["origin"] for m in result["mockups"]}
        self.assertEqual(origins, {"market": "ai_generated", "logo": "supplied"})
        self.assertEqual((result["ai_generated_mockups"], result["supplied_mockups"]), (1, 1))
        self.assertEqual(result["tools"], ["built_in_image_gen"])

    def test_the_model_and_the_fallback_role_are_carried_from_the_record(self):
        self.mockup("market")
        self.edit("mockups", lambda body: body["mockups"][0].update(tool_name="SpriteCook", provenance={"model": "gpt-image-2.5", "generator_role": "fallback"}))
        entry = disclosure.build(self.root)["mockups"][0]
        self.assertEqual((entry["tool"], entry["model"], entry["generator_role"]), ("SpriteCook", "gpt-image-2.5", "fallback"))

    def test_art_that_is_not_approved_is_left_out_because_it_cannot_ship(self):
        self.mockup("market", approve=False)
        self.assertEqual(disclosure.build(self.root)["mockups"], [])

    def test_an_approved_asset_is_traced_to_its_source_mockup(self):
        self.mockup("market")
        self.asset("workshop", "market")
        result = disclosure.build(self.root)
        self.assertEqual(result["assets"], [{"id": "workshop_v001", "revision": "v001", "origin": "from_ai_generated_mockup"}])
        self.assertEqual(result["assets_from_ai_generated_mockups"], 1)

    def test_an_asset_with_its_own_recorded_provenance_shows_it_and_one_without_is_counted(self):
        self.mockup("market")
        self.asset("workshop", "market")
        self.asset("tower", "market")
        self.edit("assets", lambda body: body["assets"][0].update(provenance={"provider": "Codex", "model": "image-model", "edit_mode": "generated", "seed": 7}))
        result = disclosure.build(self.root)
        by_id = {a["id"]: a for a in result["assets"]}
        self.assertEqual(by_id["workshop_v001"]["recorded_provenance"], {"provider": "Codex", "model": "image-model", "edit_mode": "generated"})
        self.assertNotIn("recorded_provenance", by_id["tower_v001"])
        self.assertEqual(result["assets_without_recorded_provenance"], 1)

    def test_an_asset_from_a_supplied_mockup_is_not_counted_as_ai_generated(self):
        self.mockup("logo")
        self.edit("mockups", lambda body: body["mockups"][0].update(tool_mode="external_import"))
        self.asset("badge", "logo")
        self.assertEqual(disclosure.build(self.root)["assets"][0]["origin"], "from_supplied_mockup")

    def test_a_generated_asset_that_is_not_approved_is_left_out(self):
        self.mockup("market")
        self.asset("workshop", "market", approved=False)
        self.assertEqual(disclosure.build(self.root)["assets"], [])

    def test_building_it_writes_nothing(self):
        self.mockup("market")
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        disclosure.build(self.root)
        self.assertEqual(sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")), before)

    def test_the_command_line_prints_the_summary(self):
        self.mockup("market")
        done = subprocess.run([sys.executable, str(SCRIPT), "--game-root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["ai_generated_mockups"], 1)


if __name__ == "__main__":
    unittest.main()
