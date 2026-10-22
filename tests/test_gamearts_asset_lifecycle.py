"""Reject/revoke enforcement tests for Game Arts lifecycle lookup and transitions."""
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_asset_lifecycle.py"
spec = importlib.util.spec_from_file_location("gamearts_asset_lifecycle", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class LifecycleGuardTests(unittest.TestCase):
    def fixture(self, root):
        output = root / ".gamearts/outputs"
        candidate = output / "assets/generated/workshop_v001"
        candidate.mkdir(parents=True)
        (candidate / "shell.png").write_bytes(b"asset")
        mock = output / "mockups/approved/game_scene_v001.png"
        mock.parent.mkdir(parents=True)
        mock.write_bytes(b"approved mockup")
        (output / "manifests").mkdir()
        (output / "manifests/assets.json").write_text(json.dumps({
            "assets": [{
                "asset_id": "workshop_v001",
                "status": "generated",
                "approval": "pending",
                "bundle_path": ".gamearts/outputs/assets/generated/workshop_v001",
                "files": ["shell.png"]
            }]
        }))
        (output / "manifests/mockups.json").write_text(json.dumps({
            "mockups": [{
                "mockup_id": "scene",
                "revision": "v001",
                "status": "approved",
                "file": ".gamearts/outputs/mockups/approved/game_scene_v001.png",
                "sha256": hashlib.sha256(mock.read_bytes()).hexdigest()
            }]
        }))
        return output

    def test_revoke_moves_complete_bundle_out_of_generated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            res = mod.revoke(root, "assets", "workshop_v001", "Failed visual cutout")
            self.assertEqual(res["status"], "revoked")
            self.assertFalse((out / "assets/generated/workshop_v001").exists())
            self.assertTrue((out / "assets/revoked/workshop_v001/shell.png").exists())
            saved = json.loads((out / "manifests/assets.json").read_text())["assets"][0]
            self.assertEqual(saved["status"], "revoked")
            self.assertEqual(saved["visual_review"], "rejected")
            self.assertEqual(saved["revocation_reason"], "Failed visual cutout")
            self.assertTrue(Path(res["manifest_backup"]).is_file())

    def test_rejected_item_is_never_selected_for_production(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            mod.revoke(root, "assets", "workshop_v001", "Failed cutout")
            self.assertEqual(mod.select(root, "assets", "generated"), [])
            with self.assertRaisesRegex(ValueError, "REJECTED/REVOKED"):
                mod.select(root, "assets", "generated", "workshop_v001")
            with self.assertRaisesRegex(ValueError, "REJECTED/REVOKED"):
                mod.select(root, "assets", "approved", "workshop_v001")

    def test_still_allows_exact_approved_mockup_as_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            selected = mod.select(root, "mockups", "approved", "scene")
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["status"], "approved")

    def test_approved_mockup_tamper_blocks_reference_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            (out / "mockups/approved/game_scene_v001.png").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                mod.select(root, "mockups", "approved", "scene")

    def test_rejection_reason_is_required(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            with self.assertRaisesRegex(ValueError, "reason"):
                mod.revoke(root, "assets", "workshop_v001", "")
            self.assertTrue((out / "assets/generated/workshop_v001").exists())

    def test_incomplete_bundle_refuses_transition(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            (out / "assets/generated/workshop_v001/shell.png").unlink()
            with self.assertRaisesRegex(ValueError, "missing required"):
                mod.revoke(root, "assets", "workshop_v001", "bad")
            self.assertTrue((out / "assets/generated/workshop_v001").exists())

    def test_duplicate_revocation_does_not_touch_preserved_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            mod.revoke(root, "assets", "workshop_v001", "bad")
            with self.assertRaisesRegex(ValueError, "already revoked"):
                mod.revoke(root, "assets", "workshop_v001", "same")
            self.assertEqual(len(list((root / ".gamearts/outputs/assets/revoked").iterdir())), 1)

    def test_record_path_must_match_status_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            mf = out / "manifests/assets.json"
            data = json.loads(mf.read_text())
            data["assets"][0]["status"] = "approved"
            mf.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "disagrees"):
                mod.select(root, "assets", "approved", "workshop_v001")

    def test_mockup_can_be_revoked_and_no_longer_used_as_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            mod.revoke(root, "mockups", "scene", "Visual direction rejected")
            self.assertFalse((out / "mockups/approved/game_scene_v001.png").exists())
            self.assertTrue((out / "mockups/revoked/game_scene_v001.png").is_file())
            self.assertEqual(mod.select(root, "mockups", "approved"), [])

    def test_rejected_visual_review_is_skipped_even_if_manifest_status_generated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            mf = out / "manifests/assets.json"
            data = json.loads(mf.read_text())
            data["assets"][0]["visual_review"] = "rejected"
            mf.write_text(json.dumps(data))
            self.assertEqual(mod.select(root, "assets", "generated"), [])
            with self.assertRaisesRegex(ValueError, "REJECTED/REVOKED"):
                mod.select(root, "assets", "generated", "workshop_v001")


if __name__ == "__main__":
    unittest.main()
