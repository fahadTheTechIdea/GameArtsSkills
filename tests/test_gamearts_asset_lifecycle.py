"""Reject/revoke enforcement tests for Game Arts lifecycle lookup and transitions."""
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from gamearts_testkit import make_sheet, shaded_picture

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_asset_lifecycle.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("gamearts_asset_lifecycle", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def real_sheet(candidate, name="workshop_v001_sheet"):
    """A genuine sheet + measured atlas in `candidate` (a bundle with no sheet cannot be approved)."""
    return make_sheet(candidate, name, "workshop_v001")


class LifecycleGuardTests(unittest.TestCase):
    def use_real_sheet(self, out):
        """Swap the placeholder shell.png of the generated candidate for a real sheet; return its declared files."""
        candidate = out / "assets/generated/workshop_v001"
        (candidate / "shell.png").unlink()
        files = real_sheet(candidate)
        manifest = out / "manifests/assets.json"
        body = json.loads(manifest.read_text())
        body["assets"][0]["files"] = list(files)
        manifest.write_text(json.dumps(body))
        return candidate, files

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
            crop_receipt = bundle / "reference.packet.json"
            crop_info = json.loads(crop_receipt.read_text())
            crop_info["approved_mockup"]["id"] = "scene"
            crop_info["approved_mockup"]["revision"] = "v001"
            crop_info["approved_mockup"]["sha256"] = json.loads(
                (output / "manifests/mockups.json").read_text()
            )["mockups"][0]["sha256"]
            crop_receipt.write_text(json.dumps(crop_info))
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

    def test_approve_generated_asset_atomically_and_reconcile_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            candidate, sheet_files = self.use_real_sheet(out)
            (candidate / "workshop_v001.blueprint.json").write_text(json.dumps({
                "status": "generated_needs_visual_review",
                "production_approval": "not_granted"
            }))
            (candidate / "workshop_v001.validation.json").write_text(json.dumps({
                "status": "pending", "godot": "not_tested"
            }))
            mf = out / "manifests/assets.json"
            body = json.loads(mf.read_text())
            source = json.loads((out / "manifests/mockups.json").read_text())["mockups"][0]
            body["assets"][0]["source_mockups"] = [{
                "mockup_id": "scene", "revision": "v001",
                "reference_sha256": source["sha256"]
            }]
            body["assets"][0]["files"] += ["workshop_v001.blueprint.json",
                                          "workshop_v001.validation.json"]
            mf.write_text(json.dumps(body))
            outcome = mod.approve_asset(root, "workshop_v001", "approved-in-chat")
            self.assertEqual(outcome["status"], "approved")
            self.assertEqual(outcome["technical_validation"], "passed")
            self.assertEqual(outcome["engine_validation"], "not_assessed_by_approval")
            folder = out / "assets/approved/workshop_v001"
            self.assertTrue((folder / sheet_files[0]).exists())
            self.assertFalse(candidate.exists())
            bp = json.loads((folder / "workshop_v001.blueprint.json").read_text())
            self.assertEqual(bp["status"], "approved_artwork_not_engine_verified")
            self.assertEqual(bp["production_approval"], "granted_by_user")
            qa = json.loads((folder / "workshop_v001.validation.json").read_text())
            self.assertEqual(qa["godot"], "not_tested")
            self.assertEqual(mod.audit_asset(root, "workshop_v001"), [])
            record = json.loads(mf.read_text())["assets"][0]
            self.assertEqual(record["technical_validation"]["status"], "passed")
            self.assertIn(sheet_files[0], record["artifact_hashes"])
            # Hash changes after approval must immediately block approved reuse.
            (folder / sheet_files[0]).write_bytes(b"tampered")
            self.assertTrue(any("approved artifact bytes changed" in message
                                for message in mod.audit_asset(root, "workshop_v001")))

    def test_promote_new_composite_only_after_exact_user_review_packet(self):
        from test_visual_review_cleanup import fixture as review_fixture, decision
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from visual_review_cleanup import prepare
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            candidate, _sheet = self.use_real_sheet(out)
            cleanup, review_spec, _ = review_fixture(candidate)
            spec = json.loads(review_spec.read_text())
            spec["asset_id"] = "workshop_v001"
            spec["revision"] = "v001"
            spec["approved_reference"]["mockup_id"] = "scene"
            review_spec.write_text(json.dumps(spec))
            ref = candidate / "reference.packet.json"
            crop = json.loads(ref.read_text())
            crop["approved_mockup"]["id"] = "scene"
            crop["approved_mockup"]["revision"] = "v001"
            source = json.loads((out / "manifests/mockups.json").read_text())["mockups"][0]
            crop["approved_mockup"]["sha256"] = source["sha256"]
            ref.write_text(json.dumps(crop))
            packet = prepare(cleanup, review_spec, candidate / "visual_review")
            vote = candidate / "visual_review" / "decision.json"
            accept = decision(packet)
            accept["user_approval_reference"] = "actual-approved-turn-in-test"
            vote.write_text(json.dumps(accept))
            mf = out / "manifests/assets.json"
            body = json.loads(mf.read_text())
            record = body["assets"][0]
            record["source_mockups"] = [{
                "mockup_id": "scene", "revision": "v001",
                "reference_sha256": source["sha256"]
            }]
            record["revision"] = "v001"
            record["visual_review_protocol"] = "review_packet_v1"
            record["visual_reviews"] = [{"packet": "visual_review/visual_review.packet.json",
                                         "decision": "visual_review/decision.json"}]
            mf.write_text(json.dumps(body))
            outcome = mod.approve_asset(root, "workshop_v001", "actual-approved-turn-in-test")
            self.assertEqual(outcome["visual_review_protocol"], "review_packet")  # the legacy spelling is normalized
            folder = out / "assets/approved/workshop_v001"
            self.assertTrue((folder / "workbench" / "cleanup.json").is_file())
            self.assertTrue((folder / "visual_review" / "visual_review.packet.json").is_file())
            self.assertEqual(mod.audit_asset(root, "workshop_v001"), [])
            png = folder / "workbench" / "workbench.png"
            with Image.open(png) as original:
                changed = original.convert("RGBA")
            changed.putpixel((0, 0), (1, 20, 30, 255))
            changed.save(png)
            issues = mod.audit_asset(root, "workshop_v001")
            self.assertTrue(any("approved artifact bytes changed" in item or
                                "invalid approval evidence" in item for item in issues))

    def test_invalid_decision_cannot_promote_or_change_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            candidate, sheet_files = self.use_real_sheet(out)
            manifest = out / "manifests/assets.json"
            body = json.loads(manifest.read_text())
            body["assets"][0]["visual_review_protocol"] = "review_packet"
            body["assets"][0]["revision"] = "v001"
            manifest.write_text(json.dumps(body))
            before = manifest.read_bytes()
            with self.assertRaisesRegex(ValueError, "acceptance packet missing"):
                mod.approve_asset(root, "workshop_v001", "unverified")
            self.assertEqual(manifest.read_bytes(), before)
            self.assertTrue((candidate / sheet_files[0]).is_file())

    def test_bundle_without_a_real_sheet_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)  # shell.png holds the bytes b"asset": not an image, and there is no atlas
            before = (out / "manifests/assets.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "Technical artwork gate failed.*atlas"):
                mod.approve_asset(root, "workshop_v001", "approved-in-test")
            self.assertEqual((out / "manifests/assets.json").read_bytes(), before)
            self.assertTrue((out / "assets/generated/workshop_v001/shell.png").is_file())

    def test_sheet_with_pixels_outside_its_frames_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            candidate, sheet_files = self.use_real_sheet(out)
            sheet = candidate / sheet_files[0]
            cell_w = json.loads((candidate / sheet_files[1]).read_text())["cell_size"][0]
            image = Image.open(sheet).convert("RGBA")
            image.putpixel((cell_w + 1, 0), (1, 2, 3, 255))  # in the gutter, outside every frame: must be exact key
            image.save(sheet)
            with self.assertRaisesRegex(ValueError, "Technical artwork gate failed.*not exact #FF00FF"):
                mod.approve_asset(root, "workshop_v001", "approved-in-test")
            self.assertTrue(candidate.exists())

    def test_post_approval_audit_failure_rolls_back_bundle_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = self.fixture(root)
            candidate, sheet_files = self.use_real_sheet(out)
            original = (candidate / sheet_files[0]).read_bytes()
            mf = out / "manifests/assets.json"
            before = mf.read_bytes()
            # Missing approved source link causes post-move audit to fail.
            with self.assertRaisesRegex(ValueError, "Post-approval asset audit failed"):
                mod.approve_asset(root, "workshop_v001", "approved-in-test")
            self.assertTrue((candidate / sheet_files[0]).is_file())
            self.assertEqual((candidate / sheet_files[0]).read_bytes(), original)
            self.assertEqual(mf.read_bytes(), before)
            self.assertFalse((out / "assets/approved/workshop_v001").exists())

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


class MockupLifecycleGateTests(unittest.TestCase):
    def confirmed_fixture(self, root, status="owner_confirmed"):
        (root / ".gamearts").mkdir(parents=True)
        settings = {
            "schema_version": "1.0",
            "project_id": "test.game",
            "settings_status": status,
            "confirmed_at": "2026-10-23T12:00:00Z",
            "confirmed_by": "owner",
            "art_style": {"id": "rendered_2d"},
            "world": {
                "grid": "orthogonal_square",
                "logical_tile_m": [16, 16],
                "ground_tile_px": [256, 256],
                "pixels_per_meter": 16,
                "construction_snap_m": 1
            },
            "directions": ["S"],
            "animation": {"preferred_method": "hybrid", "animated_attachment_anchors": True},
            "workflow": {"mockup_approval_required": True, "detail_decomposition_required": True},
            "export": {"background_hex": "#FF00FF", "background_alpha": 255,
                       "atlas_per_sheet": True, "no_zip": True}
        }
        project = root / ".gamearts/project.json"
        project.write_text(json.dumps(settings))
        settings_sha = hashlib.sha256(project.read_bytes()).hexdigest()
        generated = root / ".gamearts/outputs/mockups/generated"
        generated.mkdir(parents=True)
        (root / ".gamearts/outputs/manifests").mkdir(parents=True)
        image = generated / "test_game_world_colony_mockup_v001.png"
        with shaded_picture((64, 40), (20, 30, 40)) as canvas:
            canvas.save(image)
        image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
        metadata = {
            "schema_version": "1.0",
            "mockup_id": "test-game-colony",
            "revision": "v001",
            "scope": "world",
            "status": "generated",
            "file": image.relative_to(root).as_posix(),
            "sha256": image_sha,
            "settings_sha256": settings_sha,
            "prompt": "Legacy-style colony world mockup from an agent brief.",
            "prompt_origin": "agent_brief",
            "imagegen_prompt_captured": False,
            "tool_mode": "built_in_image_gen",
            "created_at_utc": "2026-10-23T12:00:00Z"
        }
        metadata_path = image.with_suffix(".metadata.json")
        metadata_path.write_text(json.dumps(metadata))
        return image, metadata_path

    def test_register_creates_manifest_and_metadata_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            outcome = mod.register_mockup(root, metadata, image)
            self.assertEqual(outcome["status"], "generated")
            manifest = json.loads((root / ".gamearts/outputs/manifests/mockups.json").read_text())
            self.assertEqual(len(manifest["mockups"]), 1)
            self.assertEqual(manifest["mockups"][0]["mockup_id"], "test-game-colony")
            self.assertEqual(manifest["mockups"][0]["status"], "generated")
            self.assertEqual(mod.audit_mockup(root, "test-game-colony", "v001"), [])
            self.assertEqual(mod.reconcile_mockups(root)["issues"], [])
            schemas = Path(__file__).resolve().parents[1] / "schemas"
            import jsonschema
            jsonschema.validate(manifest, json.loads((schemas / "gamearts-mockups-manifest.schema.json").read_text()))
            jsonschema.validate(
                json.loads(metadata.read_text()),
                json.loads((schemas / "gamearts-mockup-metadata.schema.json").read_text()))

    def test_register_refuses_unconfirmed_settings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root, status="inferred")
            with self.assertRaisesRegex(ValueError, "owner_confirmed"):
                mod.register_mockup(root, metadata, image)

    def test_register_refuses_settings_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            body = json.loads(metadata.read_text())
            body["settings_sha256"] = "0" * 64
            metadata.write_text(json.dumps(body))
            with self.assertRaisesRegex(ValueError, "settings_sha256"):
                mod.register_mockup(root, metadata, image)

    def test_register_refuses_duplicate_revision(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            with self.assertRaisesRegex(ValueError, "already registered"):
                mod.register_mockup(root, metadata, image)

    def test_approve_mockup_moves_image_metadata_and_approval_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            outcome = mod.approve_mockup(root, "test-game-colony", "v001", "approved-in-test")
            self.assertEqual(outcome["status"], "approved")
            approved_image = root / ".gamearts/outputs/mockups/approved/test_game_world_colony_mockup_v001.png"
            approved_metadata = approved_image.with_suffix(".metadata.json")
            self.assertTrue(approved_image.is_file())
            self.assertTrue(approved_metadata.is_file())
            record = json.loads((root / ".gamearts/outputs/manifests/mockups.json").read_text())["mockups"][0]
            self.assertEqual(record["status"], "approved")
            self.assertEqual(record["approval"], "user_granted")
            self.assertEqual(record["approval_reference"], "approved-in-test")
            self.assertEqual(json.loads(approved_metadata.read_text())["file"],
                             approved_image.relative_to(root).as_posix())
            self.assertEqual(mod.audit_mockup(root, "test-game-colony", "v001"), [])
            self.assertEqual(len(mod.select(root, "mockups", "approved", "test-game-colony", "v001")), 1)

    def test_approved_mockup_tamper_blocks_audit_and_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            mod.approve_mockup(root, "test-game-colony", "v001", "approved-in-test")
            approved_image = root / ".gamearts/outputs/mockups/approved/test_game_world_colony_mockup_v001.png"
            approved_image.write_bytes(b"tampered")
            issues = mod.audit_mockup(root, "test-game-colony", "v001")
            self.assertTrue(any("hash mismatch" in issue or "artifact changed" in issue for issue in issues))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                mod.select(root, "mockups", "approved", "test-game-colony", "v001")

    def test_revoke_mockup_moves_metadata_companion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            mod.revoke(root, "mockups", "test-game-colony", "rejected in test", "v001")
            revoked_image = root / ".gamearts/outputs/mockups/revoked/test_game_world_colony_mockup_v001.png"
            revoked_metadata = revoked_image.with_suffix(".metadata.json")
            self.assertTrue(revoked_image.is_file())
            self.assertTrue(revoked_metadata.is_file())
            self.assertFalse(image.exists())
            record = json.loads((root / ".gamearts/outputs/manifests/mockups.json").read_text())["mockups"][0]
            self.assertEqual(record["status"], "revoked")
            self.assertEqual(record["file"], revoked_image.relative_to(root).as_posix())
            self.assertEqual(json.loads(revoked_metadata.read_text())["file"],
                             revoked_image.relative_to(root).as_posix())
            self.assertEqual(mod.audit_mockup(root, "test-game-colony", "v001"), [])

    def test_reconcile_reports_unregistered_image_and_missing_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            orphan = root / ".gamearts/outputs/mockups/generated/test_game_orphan_mockup_v002.png"
            with shaded_picture((16, 16), (1, 2, 3)) as canvas:
                canvas.save(orphan)
            issues = mod.reconcile_mockups(root)["issues"]
            self.assertTrue(any("Unregistered mockup image" in issue for issue in issues))
            self.assertTrue(any("Missing mockup metadata" in issue for issue in issues))

    def test_settings_change_invalidates_generated_settings_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            project = root / ".gamearts/project.json"
            settings = json.loads(project.read_text())
            settings["art_style"]["id"] = "illustrated"
            project.write_text(json.dumps(settings))
            issues = mod.audit_mockup(root, "test-game-colony", "v001")
            self.assertTrue(any("different material settings" in issue for issue in issues))
            self.assertTrue(any("different settings" in issue for issue in mod.reconcile_mockups(root)["issues"]))

    def test_settings_edit_after_approval_flags_for_review_but_never_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            mod.approve_mockup(root, "test-game-colony", "v001", "approved-in-test")
            project = root / ".gamearts/project.json"
            settings = json.loads(project.read_text())
            settings["confirmed_by"] = "someone else"  # not a material setting: nothing to flag
            project.write_text(json.dumps(settings, indent=4))
            notes = []
            self.assertEqual(mod.audit_mockup(root, "test-game-colony", "v001", notes), [])
            self.assertEqual(notes, [])
            settings["art_style"]["id"] = "illustrated"  # material: flagged, but approved art stays usable
            project.write_text(json.dumps(settings))
            notes = []
            self.assertEqual(mod.audit_mockup(root, "test-game-colony", "v001", notes), [])
            self.assertTrue(any("different material settings" in n for n in notes))
            self.assertEqual(len(mod.select(root, "mockups", "approved", "test-game-colony", "v001")), 1)

    def test_reformatting_settings_does_not_invalidate_a_generated_mockup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image, metadata = self.confirmed_fixture(root)
            mod.register_mockup(root, metadata, image)
            project = root / ".gamearts/project.json"
            project.write_text(json.dumps(json.loads(project.read_text()), indent=8))
            self.assertEqual(mod.audit_mockup(root, "test-game-colony", "v001"), [])


if __name__ == "__main__":
    unittest.main()
