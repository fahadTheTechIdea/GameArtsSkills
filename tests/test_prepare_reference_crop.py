"""Tests for approved-reference image crop and conditioning evidence gate."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from gamearts_testkit import digest, key_image, picture, write_settings

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_reference_crop.py"
spec = importlib.util.spec_from_file_location("prepare_reference_crop", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ReferenceCropTests(unittest.TestCase):
    def fixture(self, root):
        approved = root / ".gamearts" / "outputs" / "mockups" / "approved"
        source = picture(approved / "fictional_workshop_scene_v001.png")
        settings_file = write_settings(root)
        job = {
            "asset_id": "test_workshop_v001",
            "asset_class": "static_structure",
            "approved_mockup": {
                "id": "fictional_scene", "revision": "v001",
                "approval_status": "approved",
                "file": str(source.relative_to(root)),
                "sha256": digest(source)
            },
            "region": {"id": "workshop", "rect": [10, 6, 22, 14], "padding_px": 2},
            "identity_lock": ["brown roof", "one fixed camera"]
        }
        manifest = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"mockups": [{
            "mockup_id": "fictional_scene", "revision": "v001",
            "status": "approved", "file": str(source.relative_to(root)),
            "sha256": digest(source)
        }]}))
        job_file = root / "reference_job.json"
        job_file.write_text(json.dumps(job))
        return source, settings_file, job, job_file

    def test_real_crop_and_selected_settings_in_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, settings, job, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            crop_path = packet_file.parent / packet["reference_crop"]
            self.assertTrue(crop_path.exists())
            self.assertEqual(packet["region"]["actual_crop_box"], [8, 4, 34, 22])
            self.assertEqual(packet["reference_crop_size"], [26, 18])
            with Image.open(src) as original, Image.open(crop_path) as cropped:
                self.assertEqual(cropped.getpixel((2, 2)), original.getpixel((10, 6)))
            prompt = (packet_file.parent / packet["prompt_path"]).read_text()
            self.assertIn("illustrated", prompt)
            self.assertIn("fine charcoal", prompt)
            self.assertIn("elevated orthographic oblique", prompt)
            self.assertIn(crop_path.name, prompt)
            self.assertIn("ONE static_structure master", prompt)
            self.assertNotIn("isometric pixel-art workshop", prompt)
            self.assertEqual(packet["conditioning_status"], "prepared_not_attached")
            self.assertEqual(packet["production_approval"], "not_granted")
            self.assertEqual(packet["export_rule"], "key_background")

    def test_packet_holds_no_absolute_path_and_survives_moving_the_game(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "game"
            root.mkdir()
            _, _, _, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            flat = json.dumps(packet)
            self.assertNotIn(str(root), flat)
            self.assertNotIn(str(root).replace("\\", "/"), flat)
            moved = Path(td) / "moved_game"
            shutil.copytree(root, moved)
            receipt = moved / "receipt.json"
            candidate = moved / "candidate.png"
            key_image((16, 16), {(8, 8): (11, 22, 33, 255)}).save(candidate)
            receipt.write_text(json.dumps({"reference_crop_sha256": packet["reference_crop_sha256"],
                                           "reference_image_path": packet["reference_crop"], "image_input_attached": True,
                                           "tool_invocation_id": "t-1", "candidate_image": str(candidate),
                                           "candidate_sha256": digest(candidate)}))
            result = mod.verify(moved / "generated" / "reference.packet.json", receipt)
            self.assertEqual(result["file_integrity"], "passed")

    def test_prepare_requires_owner_confirmed_schema_valid_settings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            write_settings(root, settings_status="inferred")
            with self.assertRaisesRegex(ValueError, "owner_confirmed"):
                mod.prepare(root, job_file, root / "generated")
            write_settings(root)
            (root / ".gamearts" / "project.json").write_text('{"project_id": "partial"}')
            with self.assertRaisesRegex(ValueError, "contract violation"):
                mod.prepare(root, job_file, root / "other")

    def test_dotted_mockup_ids_share_the_lifecycle_rule(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, _, job, job_file = self.fixture(root)
            job["approved_mockup"]["id"] = "city.scene-1"
            job_file.write_text(json.dumps(job))
            manifest = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
            record = json.loads(manifest.read_text())
            record["mockups"][0]["mockup_id"] = "city.scene-1"
            manifest.write_text(json.dumps(record))
            self.assertTrue(mod.prepare(root, job_file, root / "generated").is_file())

    def test_crop_requires_managed_approved_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, _, job, job_file = self.fixture(root)
            moved = root / "external.png"
            moved.write_bytes(src.read_bytes())
            job["approved_mockup"]["file"] = "external.png"
            job_file.write_text(json.dumps(job))
            with self.assertRaisesRegex(ValueError, "mockups/approved"):
                mod.prepare(root, job_file, root / "generated")

    def test_rejects_out_of_range_crop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, job, job_file = self.fixture(root)
            job["region"]["rect"] = [25, 20, 30, 20]
            job_file.write_text(json.dumps(job))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                mod.prepare(root, job_file, root / "generated")

    def test_rejects_changed_source_and_camera_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, _, job, job_file = self.fixture(root)
            src.write_bytes(src.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                mod.prepare(root, job_file, root / "generated")
            job["approved_mockup"]["sha256"] = digest(src)
            manifest = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
            record = json.loads(manifest.read_text())
            record["mockups"][0]["sha256"] = digest(src)
            manifest.write_text(json.dumps(record))
            job["approved_camera"] = "isometric"
            job_file.write_text(json.dumps(job))
            with self.assertRaisesRegex(ValueError, "camera conflicts"):
                mod.prepare(root, job_file, root / "generated")

    def test_rejects_unregistered_mockup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            (root / ".gamearts" / "outputs" / "manifests" / "mockups.json").unlink()
            with self.assertRaisesRegex(ValueError, "lifecycle manifest"):
                mod.prepare(root, job_file, root / "generated")

    def test_rejects_approved_record_without_source_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            manifest = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
            entry = json.loads(manifest.read_text())
            del entry["mockups"][0]["sha256"]
            manifest.write_text(json.dumps(entry))
            with self.assertRaisesRegex(ValueError, "lacks source SHA256"):
                mod.prepare(root, job_file, root / "generated")

    def test_rejects_mismatching_approval_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            path = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
            path.write_text(json.dumps({"mockups": [{
                "mockup_id": "fictional_scene", "revision": "v001",
                "status": "revoked", "file": "wrong.png"
            }]}))
            with self.assertRaisesRegex(ValueError, "matching explicitly approved"):
                mod.prepare(root, job_file, root / "generated")

    def test_rejects_eight_view_static_without_explicit_rotation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, job, job_file = self.fixture(root)
            job["directions"] = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]
            job_file.write_text(json.dumps(job))
            with self.assertRaisesRegex(ValueError, "ONE approved view"):
                mod.prepare(root, job_file, root / "generated")

    def test_verify_rejects_missing_or_false_tool_attachment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, job, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            candidate = root / "candidate.png"
            Image.new("RGBA", (20, 20), (255, 0, 255, 255)).save(candidate)
            receipt_file = root / "receipt.json"
            with self.assertRaisesRegex(ValueError, "receipt"):
                mod.verify(packet_file, receipt_file)
            receipt = {
                "reference_crop_sha256": packet["reference_crop_sha256"],
                "reference_image_path": packet["reference_crop"],
                "image_input_attached": False,
                "tool_invocation_id": "reported-42",
                "candidate_image": str(candidate),
                "candidate_sha256": digest(candidate)
            }
            receipt_file.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "not attached"):
                mod.verify(packet_file, receipt_file)
            receipt["image_input_attached"] = True
            receipt["reference_crop_sha256"] = "not-the-image"
            receipt_file.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "does not match"):
                mod.verify(packet_file, receipt_file)


    def test_static_uses_one_view_not_world_camera_as_direction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            self.assertEqual(packet["resolved_directions"], ["fixed"])
            self.assertEqual(packet["resolved_camera"], "elevated orthographic oblique")

    def test_ui_uses_ui_camera_not_world_camera(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, settings_file, job, job_file = self.fixture(root)
            config = json.loads(settings_file.read_text())
            config["art_style"]["ui_camera"] = "flat front-facing card illustration"
            settings_file.write_text(json.dumps(config))
            job["asset_class"] = "ui_presentation"
            job_file.write_text(json.dumps(job))
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            prompt = (packet_file.parent / packet["prompt_path"]).read_text()
            self.assertEqual(packet["resolved_camera"], "flat front-facing card illustration")
            self.assertEqual(packet["resolved_directions"], ["ui"])
            self.assertIn("flat front-facing card illustration", prompt)
            self.assertNotIn("CAMERA FROM SELECTED GAME SETTINGS / APPROVED REFERENCE: elevated orthographic oblique", prompt)
            self.assertEqual(packet["export_rule"], "full_bleed")
            self.assertIn("fills its canvas", prompt)
            self.assertNotIn("solid opaque #FF00FF background", prompt)

    def test_terrain_uses_ground_grid_not_world_object_camera(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, job, job_file = self.fixture(root)
            job["asset_class"] = "terrain"
            job_file.write_text(json.dumps(job))
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            self.assertEqual(packet["resolved_camera"], "orthogonal_ground_grid")
            self.assertEqual(packet["resolved_directions"], ["tile"])

    def test_mobile_keeps_game_configured_direction_set(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, job, job_file = self.fixture(root)
            job["asset_class"] = "mobile_directional"
            job_file.write_text(json.dumps(job))
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            self.assertEqual(packet["resolved_directions"],
                             ["S", "SW", "W", "NW", "N", "NE", "E", "SE"])

    def test_manifest_tamper_invalidates_prepared_packet(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            manifest = root / ".gamearts" / "outputs" / "manifests" / "mockups.json"
            manifest.write_text('{"mockups": []}')
            with self.assertRaisesRegex(ValueError, "SHA256 changed"):
                mod.verify(packet_file, root / "missing_receipt.json")

    def receipt_for(self, root, packet_file, candidate):
        packet = json.loads(packet_file.read_text())
        receipt = root / "receipt.json"
        receipt.write_text(json.dumps({"reference_crop_sha256": packet["reference_crop_sha256"],
                                       "reference_image_path": packet["reference_crop"], "image_input_attached": True,
                                       "tool_invocation_id": "t-1", "candidate_image": str(candidate),
                                       "candidate_sha256": digest(candidate)}))
        return receipt

    def test_a_receipt_missing_required_fields_is_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"image_input_attached": True}))
            with self.assertRaisesRegex(ValueError, "gamearts-reference-receipt contract violation"):
                mod.verify(packet_file, receipt)

    def test_verify_rejects_near_key_contamination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            candidate = root / "candidate.png"
            key_image((16, 16), {(8, 8): (11, 22, 33, 255), (2, 2): (250, 4, 250, 255)}).save(candidate)
            with self.assertRaisesRegex(ValueError, "near-#FF00FF"):
                mod.verify(packet_file, self.receipt_for(root, packet_file, candidate))

    def test_verify_rejects_keyless_candidate_for_a_keyed_class(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, _, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            candidate = root / "candidate.png"
            Image.new("RGBA", (16, 16), (40, 90, 30, 255)).save(candidate)
            with self.assertRaisesRegex(ValueError, "lacks the exact #FF00FF background"):
                mod.verify(packet_file, self.receipt_for(root, packet_file, candidate))

    def test_full_bleed_class_accepts_a_candidate_with_no_key_pixels(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, job, job_file = self.fixture(root)
            job["asset_class"] = "terrain"
            job_file.write_text(json.dumps(job))
            packet_file = mod.prepare(root, job_file, root / "generated")
            candidate = root / "candidate.png"
            Image.new("RGBA", (16, 16), (40, 90, 30, 255)).save(candidate)
            result = mod.verify(packet_file, self.receipt_for(root, packet_file, candidate))
            self.assertEqual(result["export_rule"], "full_bleed")
            self.assertEqual(result["file_integrity"], "passed")

    def test_valid_receipt_still_requires_visual_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, _, job, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            candidate = root / "candidate.png"
            img = Image.new("RGBA", (16, 16), (255, 0, 255, 255))
            img.putpixel((8, 8), (11, 22, 33, 255))
            img.save(candidate)
            receipt_file = root / "receipt.json"
            receipt_file.write_text(json.dumps({
                "reference_crop_sha256": packet["reference_crop_sha256"],
                "reference_image_path": packet["reference_crop"],
                "image_input_attached": True,
                "tool_invocation_id": "agent-claimed-tool-result",
                "candidate_image": str(candidate),
                "candidate_sha256": digest(candidate)
            }))
            result = mod.verify(packet_file, receipt_file)
            self.assertEqual(result["file_integrity"], "passed")
            self.assertEqual(result["visual_match_to_mockup"], "not_verified")
            self.assertEqual(result["status"], "candidate_pending_visual_review")


if __name__ == "__main__":
    unittest.main()
