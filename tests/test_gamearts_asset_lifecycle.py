"""Reject/revoke enforcement tests for Game Arts lifecycle lookup and transitions."""
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

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

    def approved_fixture(self, root):
        output = self.fixture(root)
        candidate = output / "assets/generated/workshop_v001"
        new_folder = output / "assets/approved/workshop_v001"
        new_folder.parent.mkdir(parents=True)
        candidate.rename(new_folder)
        bp = new_folder / "workshop_v001.blueprint.json"
        bp.write_text(json.dumps({
            "status": "generated_needs_visual_review",
            "production_approval": "not_granted",
            "approved_clean_plate": False,
            "clean_plate_approval": "approved_by_user",
            "user_visual_approval": {"status": "approved"}
        }))
        validation = new_folder / "workshop_v001.validation.json"
        validation.write_text(json.dumps({
            "status": "approved_artwork_not_engine_verified",
            "isolated_props_background_masking": "improved_pending_user_review",
            "godot": "not_tested"
        }))
        mf = output / "manifests/assets.json"
        saved = json.loads(mf.read_text())
        a = saved["assets"][0]
        a["status"] = "approved"
        a["approval"] = "user_granted"
        a["visual_review"] = "approved"
        a["bundle_path"] = ".gamearts/outputs/assets/approved/workshop_v001"
        a["files"] += [bp.name, validation.name]
        approved_hash = json.loads((output / "manifests/mockups.json").read_text())["mockups"][0]["sha256"]
        a["source_mockups"] = [{"mockup_id": "scene", "revision": "v001",
                                "reference_sha256": approved_hash}]
        mf.write_text(json.dumps(saved))
        return output, bp, validation

    def test_detects_stale_blueprint_approval_and_visual_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, blueprint, report = self.approved_fixture(root)
            issues = mod.audit_asset(root, "workshop_v001")
            self.assertTrue(any("blueprint still reports unapproved status" in issue
                                for issue in issues))
            self.assertTrue(any("sprite review is still marked pending" in issue
                                for issue in issues))
            with self.assertRaisesRegex(ValueError, "metadata audit failed"):
                mod.select(root, "assets", "approved", "workshop_v001")

    def test_synchronized_approval_metadata_does_not_claim_godot_test(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, blueprint, report = self.approved_fixture(root)
            bp = json.loads(blueprint.read_text())
            bp.update({"status": "approved_artwork_not_engine_verified",
                       "production_approval": "granted_by_user", "approved_clean_plate": True})
            blueprint.write_text(json.dumps(bp))
            qa = json.loads(report.read_text())
            qa["isolated_props_background_masking"] = "user_approved"
            report.write_text(json.dumps(qa))
            self.assertEqual(mod.audit_asset(root, "workshop_v001"), [])
            self.assertEqual(len(mod.select(root, "assets", "approved", "workshop_v001")), 1)
            self.assertEqual(qa["godot"], "not_tested")

    def test_detects_missing_declared_artwork(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, _, _ = self.approved_fixture(root)
            (output / "assets/approved/workshop_v001/shell.png").unlink()
            self.assertTrue(any("missing or unsafe bundle file" in s for s in
                                mod.audit_asset(root, "workshop_v001")))

    def test_detects_mismatched_reference_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, _, _ = self.approved_fixture(root)
            mf = output / "manifests/assets.json"
            data = json.loads(mf.read_text())
            data["assets"][0]["source_mockups"][0]["reference_sha256"] = "0" * 64
            mf.write_text(json.dumps(data))
            self.assertTrue(any("source mockup hash disagrees" in s for s in
                                mod.audit_asset(root, "workshop_v001")))

    def test_manifest_cannot_omit_visual_review_required_by_new_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out, bp, qa = self.approved_fixture(root)
            bundle = out / "assets/approved/workshop_v001"
            (bundle / "workshop_v001.bundle.json").write_text(json.dumps({
                "asset_id": "workshop_v001",
                "visual_review_protocol": "review_packet_v1"
            }))
            issues = mod.audit_asset(root, "workshop_v001")
            self.assertTrue(any("cannot omit mandatory visual-review protocol" in s for s in issues))

    def test_new_review_protocol_blocks_approval_without_visual_packet(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, blueprint, report = self.approved_fixture(root)
            bp = json.loads(blueprint.read_text())
            bp.update({"status": "approved_artwork_not_engine_verified",
                       "production_approval": "granted_by_user",
                       "approved_clean_plate": True})
            blueprint.write_text(json.dumps(bp))
            qa = json.loads(report.read_text())
            qa["isolated_props_background_masking"] = "user_approved"
            report.write_text(json.dumps(qa))
            mf = output / "manifests/assets.json"
            data = json.loads(mf.read_text())
            data["assets"][0]["visual_review_protocol"] = "review_packet_v1"
            data["assets"][0]["revision"] = "v001"
            mf.write_text(json.dumps(data))
            issues = mod.audit_asset(root, "workshop_v001")
            self.assertTrue(any("lacks mandatory user visual review" in s for s in issues))
            with self.assertRaisesRegex(ValueError, "metadata audit failed"):
                mod.select(root, "assets", "approved", "workshop_v001")

    def test_exact_visual_review_record_allows_reuse_only_while_files_unchanged(self):
        from test_visual_review_cleanup import fixture, decision
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from visual_review_cleanup import prepare
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, blueprint, report = self.approved_fixture(root)
            bp = json.loads(blueprint.read_text())
            bp.update({"status": "approved_artwork_not_engine_verified",
                       "production_approval": "granted_by_user",
                       "approved_clean_plate": True})
            blueprint.write_text(json.dumps(bp))
            qa = json.loads(report.read_text())
            qa["isolated_props_background_masking"] = "user_approved"
            report.write_text(json.dumps(qa))
            bundle = output / "assets/approved/workshop_v001"
            cleanup, review, folder = fixture(bundle)
            spec = json.loads(review.read_text())
            spec["asset_id"] = "workshop_v001"
            spec["revision"] = "v001"
            spec["approved_reference"]["mockup_id"] = "scene"
            spec["approved_reference"]["mockup_revision"] = "v001"
            review.write_text(json.dumps(spec))
            packet_path = prepare(cleanup, review, bundle / "visual_review")
            vote = bundle / "visual_review/decision.json"
            vote.write_text(json.dumps(decision(packet_path)))
            mf = output / "manifests/assets.json"
            data = json.loads(mf.read_text())
            data["assets"][0]["visual_review_protocol"] = "review_packet_v1"
            data["assets"][0]["revision"] = "v001"
            data["assets"][0]["visual_reviews"] = [{
                "packet": "visual_review/visual_review.packet.json",
                "decision": "visual_review/decision.json"
            }]
            mf.write_text(json.dumps(data))
            self.assertEqual(mod.audit_asset(root, "workshop_v001"), [])
            self.assertEqual(len(mod.select(root, "assets", "approved", "workshop_v001")), 1)
            # Any post-review change requires new explicit user review.
            with Image.open(folder / "parent.png") as before:
                edited = before.convert("RGBA")
            edited.putpixel((32, 23), (10, 20, 30, 255))
            edited.save(folder / "parent.png")
            issues = mod.audit_asset(root, "workshop_v001")
            self.assertTrue(any("invalid approval evidence" in s for s in issues))

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

    def test_revision_selects_exact_mockup_when_id_has_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            rev2 = out / "mockups/approved/game_scene_v002.png"
            rev2.write_bytes(b"new approved mockup")
            manifest = out / "manifests/mockups.json"
            data = json.loads(manifest.read_text())
            data["mockups"].append({
                "mockup_id": "scene", "revision": "v002", "status": "approved",
                "file": ".gamearts/outputs/mockups/approved/game_scene_v002.png",
                "sha256": hashlib.sha256(rev2.read_bytes()).hexdigest()
            })
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Expected one exact"):
                mod.select(root, "mockups", "approved", "scene")
            selected = mod.select(root, "mockups", "approved", "scene", "v002")
            self.assertEqual(len(selected), 1)
            self.assertTrue(selected[0]["path"].endswith("game_scene_v002.png"))
            mod.revoke(root, "mockups", "scene", "revision rejected", "v001")
            self.assertTrue((out / "mockups/approved/game_scene_v002.png").is_file())
            self.assertTrue((out / "mockups/revoked/game_scene_v001.png").is_file())

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
