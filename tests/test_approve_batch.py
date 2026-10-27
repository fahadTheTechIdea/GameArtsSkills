"""Batch approval (plan P13.5): several exact revisions approved on one reference, each through the single-approval path, none dragging the rest down."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

import gamearts_testkit  # noqa: F401  (puts scripts/ on sys.path)

import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
from test_lifecycle_operations import GameFolder, OUT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_asset_lifecycle.py"


class MockupBatchTests(GameFolder):
    def generated(self, *names):
        from gamearts_testkit import make_mockup
        for name in names:
            image, metadata = make_mockup(self.root, name, "v001", "scene")
            life.register_mockup(self.root, metadata, image)

    def statuses(self):
        return {r["mockup_id"]: r["status"] for r in self.manifest("mockups")}

    def test_every_shown_item_is_approved_on_the_one_reference(self):
        self.generated("arrival", "match", "finale")
        items = [("arrival", "v001"), ("match", "v001"), ("finale", "v001")]
        result = life.approve_batch(self.root, "mockups", items, items, "owner said: approve scenes 1 to 3")
        self.assertEqual(result["approved"], ["arrival:v001", "match:v001", "finale:v001"])
        self.assertEqual((result["not_approved"], result["ok"]), ([], True))
        self.assertEqual(set(self.statuses().values()), {"approved"})
        self.assertEqual({r["approval_reference"] for r in self.manifest("mockups")}, {"owner said: approve scenes 1 to 3"})
        self.assertEqual(life.reconcile_mockups(self.root)["status"], "consistent")

    def test_an_item_that_was_not_shown_is_left_unapproved_and_the_rest_go_ahead(self):
        self.generated("arrival", "match")
        result = life.approve_batch(self.root, "mockups", [("arrival", "v001"), ("match", "v001")], [("arrival", "v001")], "approve what you showed me")
        self.assertEqual((result["approved"], result["ok"]), (["arrival:v001"], False))
        self.assertEqual(result["not_approved"], [{"item": "match:v001", "reason": "it was not among the items shown to the owner for this approval"}])
        self.assertEqual(self.statuses(), {"arrival": "approved", "match": "generated"})

    def test_an_item_that_is_not_generated_or_does_not_exist_is_reported_and_the_rest_go_ahead(self):
        self.generated("arrival", "match")
        life.approve_mockup(self.root, "match", "v001", "earlier approval")
        items = [("arrival", "v001"), ("match", "v001"), ("ghost", "v001")]
        result = life.approve_batch(self.root, "mockups", items, items, "approve them all")
        self.assertEqual(result["approved"], ["arrival:v001"])
        reasons = {entry["item"]: entry["reason"] for entry in result["not_approved"]}
        self.assertEqual(set(reasons), {"match:v001", "ghost:v001"})
        self.assertTrue(all(reasons.values()))
        self.assertFalse(result["ok"])
        self.assertEqual(self.statuses()["arrival"], "approved")

    def test_a_failure_in_the_middle_rolls_back_only_that_item(self):
        self.generated("arrival", "match", "finale")
        original = life.approve_mockup
        calls = []

        def flaky(root, item_id, revision, reference):
            calls.append(item_id)
            if item_id == "match":
                raise OSError("disk said no")
            return original(root, item_id, revision, reference)
        items = [("arrival", "v001"), ("match", "v001"), ("finale", "v001")]
        life.approve_mockup = flaky
        try:
            result = life.approve_batch(self.root, "mockups", items, items, "approve them all")
        finally:
            life.approve_mockup = original
        self.assertEqual(calls, ["arrival", "match", "finale"])
        self.assertEqual(result["approved"], ["arrival:v001", "finale:v001"])
        self.assertEqual(result["not_approved"], [{"item": "match:v001", "reason": "disk said no"}])
        self.assertEqual(self.statuses(), {"arrival": "approved", "match": "generated", "finale": "approved"})

    def test_a_blank_reference_an_empty_list_a_repeat_and_an_unknown_kind_are_refused_before_anything_changes(self):
        self.generated("arrival")
        item = [("arrival", "v001")]
        with self.assertRaisesRegex(ValueError, "approval reference"):
            life.approve_batch(self.root, "mockups", item, item, "  ")
        with self.assertRaisesRegex(ValueError, "at least one"):
            life.approve_batch(self.root, "mockups", [], [], "ok")
        with self.assertRaisesRegex(ValueError, "more than once"):
            life.approve_batch(self.root, "mockups", item + item, item, "ok")
        with self.assertRaisesRegex(ValueError, "mockups or assets"):
            life.approve_batch(self.root, "storyboards", item, item, "ok")
        self.assertEqual(self.statuses(), {"arrival": "generated"})


class AssetBatchTests(GameFolder):
    def test_assets_are_approved_one_by_one_through_the_single_path_and_audit_clean(self):
        source = self.approved_mockup()
        first = self.registered_asset("workshop", "v001", source)
        second = self.registered_asset("market", "v001", source)
        items = [(first, "v001"), (second, "v001")]
        result = life.approve_batch(self.root, "assets", items, items, "owner approved both sheets")
        self.assertEqual((result["approved"], result["ok"]), ([f"{first}:v001", f"{second}:v001"], True))
        self.assertEqual([life.audit_asset(self.root, name) for name in (first, second)], [[], []])
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")

    def test_an_asset_that_fails_its_gate_is_reported_with_the_gates_own_words_and_the_other_is_approved(self):
        source = self.approved_mockup()
        good = self.registered_asset("workshop", "v001", source)
        name, bundle = self.generated_bundle("market", "v001", damage=True)
        life.register_asset(self.root, name, "v001", bundle, [source])
        items = [(good, "v001"), (name, "v001")]
        result = life.approve_batch(self.root, "assets", items, items, "approve both")
        self.assertEqual(result["approved"], [f"{good}:v001"])
        self.assertEqual(result["not_approved"][0]["item"], f"{name}:v001")
        self.assertIn("Technical artwork gate failed", result["not_approved"][0]["reason"])
        self.assertEqual({r["asset_id"]: r["status"] for r in self.manifest("assets")}, {good: "approved", name: "generated"})

    def test_a_revision_that_is_not_the_recorded_one_is_reported_not_approved(self):
        source = self.approved_mockup()
        name = self.registered_asset("workshop", "v001", source)
        result = life.approve_batch(self.root, "assets", [(name, "v002")], [(name, "v002")], "approve")
        self.assertEqual(result["approved"], [])
        self.assertIn("v002", result["not_approved"][0]["reason"])
        self.assertEqual(self.manifest("assets")[0]["status"], "generated")


class BatchCommandTests(GameFolder):
    def run_op(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--game-root", str(self.root)], capture_output=True, text=True)

    def generated(self, *names):
        from gamearts_testkit import make_mockup
        for name in names:
            image, metadata = make_mockup(self.root, name, "v001", "scene")
            life.register_mockup(self.root, metadata, image)

    def test_the_command_approves_the_shown_items_and_says_what_comes_next(self):
        self.generated("arrival", "match")
        done = self.run_op("approve-batch", "--kind", "mockups", "--item", "arrival:v001", "--item", "match:v001",
                           "--shown", "arrival:v001", "--shown", "match:v001", "--user-approval-ref", "approve both")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual((result["ok"], result["approved"]), (True, ["arrival:v001", "match:v001"]))
        self.assertIn("2 approved", result["next_step"])
        self.assertEqual(result["report"]["updated"], True)

    def test_a_partial_batch_exits_one_but_still_prints_everything_that_happened(self):
        self.generated("arrival", "match")
        done = self.run_op("approve-batch", "--kind", "mockups", "--item", "arrival:v001", "--item", "match:v001",
                           "--shown", "arrival:v001", "--user-approval-ref", "approve what I showed")
        self.assertEqual(done.returncode, 1)
        result = json.loads(done.stdout)
        self.assertEqual((result["ok"], result["approved"]), (False, ["arrival:v001"]))
        self.assertIn("match:v001", result["next_step"])
        self.assertEqual(common.read_json(self.root / OUT / "manifests/mockups.json")["mockups"][1]["status"], "generated")

    def test_the_shown_list_is_required(self):
        self.generated("arrival")
        done = self.run_op("approve-batch", "--kind", "mockups", "--item", "arrival:v001", "--user-approval-ref", "approve")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--shown", done.stderr)


if __name__ == "__main__":
    unittest.main()
