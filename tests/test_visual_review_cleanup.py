"""Verify reviewed source/masks, side-by-side boards, user decisions and hash binding."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "visual_review_cleanup.py"
spec = importlib.util.spec_from_file_location("visual_review_cleanup", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
PINK = (255, 0, 255, 255)


def fixture(root):
    folder = Path(root) / "workbench"
    folder.mkdir(parents=True)
    parent = Image.new("RGBA", (40, 32), (200, 190, 175, 255))
    original = parent.copy()
    source_mask = Image.new("L", parent.size, 0)
    for y in range(10, 22):
        for x in range(7, 22):
            original.putpixel((x, y), (110, 65, 39, 255))
            source_mask.putpixel((x, y), 255)
    parent.save(folder / "parent.png")
    parent.save(folder / "plate.png")
    original.save(folder / "original.png")
    source_mask.save(folder / "workbench.mask.png")
    sprite = Image.new("RGBA", (18, 16), PINK)
    mask = Image.new("L", sprite.size, 0)
    for y in range(2, 14):
        for x in range(3, 16):
            sprite.putpixel((x, y), (110, 65, 39, 255))
            mask.putpixel((x, y), 255)
    sprite.save(folder / "workbench.png")
    mask.save(folder / "workbench.silhouette.png")
    hidden = Image.new("L", parent.size, 0)
    for y in range(12, 15):
        for x in range(10, 14):
            hidden.putpixel((x, y), 255)
    hidden.save(folder / "hidden_tabletop.mask.png")
    cleanup = {
        "schema_version": "1.0", "method": "pixel_exact",
        "source_composite": "original.png", "static_parent": "parent.png",
        "clean_plate": "plate.png", "clean_plate_review": "approved",
        "clean_plate_reference_id": "clean_plate_candidate",
        "detached_components": [{
            "id": "workbench", "kind": "removable",
            "sprite": "workbench.png", "removal_mask": "workbench.mask.png",
            "sprite_silhouette_mask": "workbench.silhouette.png"
        }]
    }
    cleanup_file = folder / "cleanup.json"
    cleanup_file.write_text(json.dumps(cleanup))
    review = {
        "asset_id": "test_workshop", "revision": "v002",
        "expected_component_ids": ["workbench"],
        "inventory_audit": "complete_for_visible_reference",
        "occlusion_audit": "completed",
        "uncertain_regions": [{
            "id": "tabletop", "mask": "workbench/hidden_tabletop.mask.png",
            "evidence_status": "inferred", "reason": "toolbox obscured tabletop"
        }]
    }
    review_file = Path(root) / "review_spec.json"
    review_file.write_text(json.dumps(review))
    return cleanup_file, review_file, folder


def decision(packet_path):
    packet = mod.read(packet_path)
    return {
        "asset_id": packet["asset_id"], "revision": packet["revision"],
        "packet_sha256": mod.sha(packet_path),
        "decision": "approved", "reviewer_type": "user",
        "user_approval_reference": "actual-message-reference-for-test",
        "component_ids_approved": packet["component_ids"],
        "uncertainty_ids_acknowledged": packet["uncertain_region_ids"],
        "reviewed_inventory": True,
        "reviewed_silhouettes": True,
        "reviewed_clean_background": True
    }


class VisualReviewTests(unittest.TestCase):
    def test_board_contains_original_parent_plate_and_individual_props(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, spec_file, _ = fixture(root)
            packet_file = mod.prepare(cleanup, spec_file, root / "review")
            packet = mod.read(packet_file)
            self.assertEqual(packet["review_status"], "pending_user_visual_review")
            self.assertEqual(packet["component_ids"], ["workbench"])
            self.assertEqual(packet["uncertain_region_ids"], ["tabletop"])
            with Image.open(root / "review" / packet["review_board"]["path"]) as image:
                self.assertGreater(image.width, 800)
            with Image.open(root / "review" / packet["props_board"]["path"]) as image:
                self.assertGreater(image.width, 500)
            self.assertEqual(packet["semantic_object_verification"], "requires_human_review")

    def test_explicit_decision_checks_all_unknowns_and_background(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, _ = fixture(root)
            packet = mod.prepare(cleanup, review, root / "review")
            vote = decision(packet)
            vote_file = root / "review" / "decision.json"
            vote["uncertainty_ids_acknowledged"] = []
            vote_file.write_text(json.dumps(vote))
            with self.assertRaisesRegex(ValueError, "uncertainty_ids_acknowledged"):
                mod.verify(packet, vote_file)
            vote["uncertainty_ids_acknowledged"] = ["tabletop"]
            vote["reviewed_clean_background"] = False
            vote_file.write_text(json.dumps(vote))
            with self.assertRaisesRegex(ValueError, "reviewed_clean_background"):
                mod.verify(packet, vote_file)
            vote["reviewed_clean_background"] = True
            vote_file.write_text(json.dumps(vote))
            checked = mod.verify(packet, vote_file)
            self.assertEqual(checked["review_status"], "user_visual_approval_recorded")
            self.assertEqual(checked["approval_source_verification"],
                             "agent_recorded_not_host_attested")

    def test_source_mutation_invalidates_prior_user_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, folder = fixture(root)
            packet = mod.prepare(cleanup, review, root / "review")
            vote = root / "review" / "decision.json"
            vote.write_text(json.dumps(decision(packet)))
            self.assertEqual(mod.verify(packet, vote)["review_status"], "user_visual_approval_recorded")
            image = Image.open(folder / "parent.png")
            image.putpixel((25, 25), (1, 2, 3, 255))
            image.save(folder / "parent.png")
            with self.assertRaisesRegex(ValueError, "Review source file changed"):
                mod.verify(packet, vote)

    def test_bad_silhouette_mask_blocks_board(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, folder = fixture(root)
            image = Image.open(folder / "workbench.png")
            image.putpixel((0, 0), (130, 121, 100, 255))
            image.save(folder / "workbench.png")
            with self.assertRaisesRegex(ValueError, "silhouette mask differs"):
                mod.prepare(cleanup, review, root / "review")

    def test_incomplete_independent_inventory_blocks_board(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, _ = fixture(root)
            data = json.loads(review.read_text())
            data["expected_component_ids"] = ["cabinet"]
            review.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "inventory"):
                mod.prepare(cleanup, review, root / "review")

    def test_uncertainty_must_be_classified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, _ = fixture(root)
            data = json.loads(review.read_text())
            data["uncertain_regions"][0]["evidence_status"] = "verified"
            review.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "uncertainty"):
                mod.prepare(cleanup, review, root / "review")

    def test_no_approval_for_other_revision(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, _ = fixture(root)
            packet = mod.prepare(cleanup, review, root / "review")
            vote = decision(packet)
            vote["revision"] = "v003"
            file = root / "review" / "decision.json"
            file.write_text(json.dumps(vote))
            with self.assertRaisesRegex(ValueError, "different asset revision"):
                mod.verify(packet, file)

    def test_clean_parent_cannot_change_outside_removal_mask(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, folder = fixture(root)
            image = Image.open(folder / "parent.png")
            image.putpixel((35, 25), (0, 0, 0, 255))
            image.save(folder / "parent.png")
            with self.assertRaisesRegex(ValueError, "Clean parent pixel test failed"):
                mod.prepare(cleanup, review, root / "review")

    def test_review_board_change_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, _ = fixture(root)
            packet = mod.prepare(cleanup, review, root / "review")
            vote = root / "review" / "decision.json"
            vote.write_text(json.dumps(decision(packet)))
            board = root / "review" / "visual_review_board.png"
            image = Image.open(board)
            image.putpixel((0, 0), (0, 0, 0))
            image.save(board)
            with self.assertRaisesRegex(ValueError, "review_board changed"):
                mod.verify(packet, vote)

    def test_review_cannot_depend_on_revoked_or_external_asset_files(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as other:
            root = Path(td)
            cleanup, review, folder = fixture(root)
            external = Path(other) / "old-revoked-workbench.png"
            external.write_bytes((folder / "workbench.png").read_bytes())
            manifest = json.loads(cleanup.read_text())
            manifest["detached_components"][0]["sprite"] = str(external)
            cleanup.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "outside current asset candidate"):
                mod.prepare(cleanup, review, root / "review")

    def test_agent_cannot_self_approve(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cleanup, review, _ = fixture(root)
            packet = mod.prepare(cleanup, review, root / "review")
            vote = decision(packet)
            vote["reviewer_type"] = "agent"
            file = root / "review" / "decision.json"
            file.write_text(json.dumps(vote))
            with self.assertRaisesRegex(ValueError, "user visual approval"):
                mod.verify(packet, file)


if __name__ == "__main__":
    unittest.main()
