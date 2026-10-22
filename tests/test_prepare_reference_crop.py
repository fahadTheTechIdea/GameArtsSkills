"""Tests for approved-reference image crop and conditioning evidence gate."""
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_reference_crop.py"
spec = importlib.util.spec_from_file_location("prepare_reference_crop", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReferenceCropTests(unittest.TestCase):
    def fixture(self, root):
        approved = root / ".gamearts" / "outputs" / "mockups" / "approved"
        approved.mkdir(parents=True)
        source = approved / "fictional_workshop_scene_v001.png"
        image = Image.new("RGB", (48, 32), (114, 171, 57))
        for y in range(6, 20):
            for x in range(10, 32):
                image.putpixel((x, y), (95, 71, 54))
        image.save(source)
        settings_file = root / ".gamearts" / "project.json"
        settings_file.write_text(json.dumps({
            "schema_version": "1.0",
            "project_id": "test_project",
            "art_style": {"id": "illustrated", "outline_policy": "fine charcoal"},
            "world": {"object_camera": "elevated orthographic oblique",
                      "pixels_per_meter": 16},
            "directions": ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]
        }))
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
        job_file = root / "reference_job.json"
        job_file.write_text(json.dumps(job))
        return source, settings_file, job, job_file

    def test_real_crop_and_selected_settings_in_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, settings, job, job_file = self.fixture(root)
            packet_file = mod.prepare(root, job_file, root / "generated")
            packet = json.loads(packet_file.read_text())
            crop_path = Path(packet["reference_crop"])
            self.assertTrue(crop_path.exists())
            self.assertEqual(packet["region"]["actual_crop_box"], [8, 4, 34, 22])
            self.assertEqual(packet["reference_crop_size"], [26, 18])
            with Image.open(src) as original, Image.open(crop_path) as cropped:
                self.assertEqual(cropped.getpixel((2, 2)), original.getpixel((10, 6)))
            prompt = Path(packet["prompt_path"]).read_text()
            self.assertIn("illustrated", prompt)
            self.assertIn("fine charcoal", prompt)
            self.assertIn("elevated orthographic oblique", prompt)
            self.assertIn(str(crop_path.resolve()), prompt)
            self.assertIn("ONE static_structure master", prompt)
            self.assertNotIn("isometric pixel-art workshop", prompt)
            self.assertEqual(packet["conditioning_status"], "prepared_not_attached")
            self.assertEqual(packet["production_approval"], "not_granted")

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
            job["approved_camera"] = "isometric"
            job_file.write_text(json.dumps(job))
            with self.assertRaisesRegex(ValueError, "camera conflicts"):
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
