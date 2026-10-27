"""The whole production pipeline on synthetic art, driven only through the command lines an agent uses.

REHEARSAL, NOT ART: the mockup is drawn with a few rectangles and every approval string is a stand-in. No image model runs
and no human decides anything, so this proves the files, gates and records fit together end to end (mockup -> reference crop ->
clean parent and separated parts -> sheets, atlases, bundle -> cleanup proof -> review boards -> approval -> audit -> revoke),
not that any art is good. Set GAMEARTS_REHEARSAL_KEEP=<folder> to keep the resulting game folder for inspection.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gamearts_testkit import PINK, digest, make_mockup, write_settings

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
OUT = ".gamearts/outputs"
WALL = (150, 110, 80, 255)
# (x0, y0, x1, y1) in the 50 x 40 building crop
PARTS = {"door": (20, 18, 32, 40), "workbench": (4, 30, 16, 38), "spanner": (40, 34, 48, 37)}
KINDS = {"door": "animated", "workbench": "removable", "spanner": "removable"}
COLORS = {"door": (60, 40, 30, 255), "workbench": (60, 90, 160, 255), "spanner": (180, 180, 190, 255)}


def run(script, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True)
    return result


def ok(script, *args):
    result = run(script, *args)
    assert result.returncode == 0, f"{script} {' '.join(map(str, args))}\nexit {result.returncode}\n{result.stdout}\n{result.stderr}"
    return result


def ok_json(script, *args):
    return json.loads(ok(script, *args).stdout)


def draw_mockup():
    """A 96 x 64 'workshop': ground, a walled building with a door, a workbench and a spanner."""
    picture = Image.new("RGB", (96, 64), (90, 140, 70))
    building = Image.new("RGB", (50, 40), WALL[:3])
    building.paste((110, 50, 40), (0, 0, 50, 6))
    for name, box in PARTS.items():
        building.paste(COLORS[name][:3], box)
    picture.paste(building, (20, 10))
    return picture


def mask_for(box, size):
    mask = Image.new("L", size, 0)
    mask.paste(255, box)
    return mask


class PipelineRehearsal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "game"
        self.root.mkdir()
        write_settings(self.root)
        self.game = ["--game-root", self.root]
        self.work = Path(self._tmp.name) / "work"
        self.work.mkdir()

    def tearDown(self):
        keep = os.environ.get("GAMEARTS_REHEARSAL_KEEP")
        if keep:
            shutil.copytree(self.root, Path(keep) / "game", dirs_exist_ok=True)
        self._tmp.cleanup()

    def life(self, *args):
        return ok_json("gamearts_asset_lifecycle.py", *args, *self.game)

    # ---- stage 1: the approved mockup and the reference crop
    def approved_mockup(self):
        image, metadata = make_mockup(self.root, "workshop-scene", "v001", "scene", picture_image=draw_mockup())
        self.life("register", "--metadata", metadata, "--image", image)
        self.life("approve-mockup", "--id", "workshop-scene", "--revision", "v001", "--user-approval-ref", "REHEARSAL stand-in, not a user decision")
        return next((self.root / OUT / "mockups/approved").glob("*.png"))

    # ---- stage 2: the clean parent, the separated parts and their proof
    def draw_cleanup(self, approved):
        with Image.open(approved) as opened:
            source = opened.convert("RGBA").crop((20, 10, 70, 50))
        parent = source.copy()
        for box in PARTS.values():
            parent.paste(WALL, box)  # the reviewed clean plate behind every removed object
        proof = self.work / "proof"
        proof.mkdir()
        source.save(proof / "source.png")
        parent.save(proof / "master.png")
        parent.save(proof / "plate.png")
        components, sprites = [], {}
        for name, box in PARTS.items():
            sprite = source.crop(box)
            silhouette = Image.new("L", sprite.size, 255)
            sprite.save(proof / f"{name}.png")
            silhouette.save(proof / f"{name}.silhouette.png")
            mask_for(box, source.size).save(proof / f"{name}.mask.png")
            sprites[name] = sprite
            components.append({"id": name, "kind": KINDS[name], "sprite": f"{name}.png", "removal_mask": f"{name}.mask.png",
                               "sprite_silhouette_mask": f"{name}.silhouette.png", "silhouette_review": "approved",
                               "silhouette_reference_id": f"{name}-review", "source_offset": [box[0], box[1]]})
        (proof / "cleanup.json").write_text(json.dumps({
            "schema_version": "1.0", "method": "pixel_exact", "source_composite": "source.png", "static_parent": "master.png",
            "clean_plate": "plate.png", "clean_plate_review": "approved", "clean_plate_reference_id": "workshop-plate",
            "art_style_id": "illustrated", "detached_components": components}))
        return proof, sprites

    # ---- the whole run
    def test_mockup_to_approved_asset_and_back(self):
        approved = self.approved_mockup()

        # reference crop: the real approved pixels, attached to the (stand-in) image tool, then the master candidate is verified
        crop_job = self.work / "reference_job.json"
        crop_job.write_text(json.dumps({
            "asset_id": "workshop_v001", "asset_class": "static_structure",
            "approved_mockup": {"id": "workshop-scene", "revision": "v001", "approval_status": "approved",
                                "file": approved.relative_to(self.root).as_posix(), "sha256": digest(approved)},
            "region": {"id": "workshop", "rect": [20, 10, 50, 40], "padding_px": 0}, "identity_lock": ["brown walls", "dark roof strip", "one door"]}))
        bundle = self.root / OUT / "assets/generated/workshop_v001"
        reference = bundle / "reference"
        ok("prepare_reference_crop.py", "prepare", *self.game, "--job", crop_job, "--output-dir", reference)
        packet = json.loads((reference / "reference.packet.json").read_text())
        with Image.open(reference / packet["reference_crop"]) as crop:
            self.assertEqual(crop.size, (50, 40))
        candidate = self.work / "master_candidate.png"  # a master on the exact key background, as an image tool would return it
        padded = Image.new("RGBA", (60, 48), PINK)
        with Image.open(approved) as opened:
            padded.paste(opened.convert("RGBA").crop((20, 10, 70, 50)), (5, 4))
        padded.save(candidate)
        receipt = self.work / "receipt.json"
        receipt.write_text(json.dumps({"reference_crop_sha256": packet["reference_crop_sha256"], "reference_image_path": packet["reference_crop"],
                                       "image_input_attached": True, "tool_invocation_id": "REHEARSAL-no-real-tool", "candidate_image": str(candidate),
                                       "candidate_sha256": digest(candidate)}))
        verified = ok_json("prepare_reference_crop.py", "verify", "--packet", reference / "reference.packet.json", "--receipt", receipt)
        self.assertEqual(verified["status"], "candidate_pending_visual_review")  # the script never claims the art matches

        # clean parent + separated parts, then sheets/atlases/bundle with the cleanup proof packaged in
        proof, sprites = self.draw_cleanup(approved)
        ok("validate_parent_cleanup.py", proof / "cleanup.json", "--strict-props")
        job = self.work / "bundle_job.json"
        job.write_text(json.dumps({
            "name": "workshop_v001", "directions": ["S"], "sample_times": [0, 0.5, 1],
            "source_mockups": [{"mockup_id": "workshop-scene", "revision": "v001"}],
            "detached_inventory": {"workshop_body": ["door", "workbench", "spanner"]},
            "parent_cleanup_evidence": [{"parent_component": "workshop_body", "direction": "S", "frame_index": 0, "manifest": "proof/cleanup.json"}],
            "components": [
                {"id": "workshop_body", "parent": None, "views": {"S": {"frames": [{"file": "proof/master.png", "pivot": [25, 39], "anchors": {"door_hinge": [20, 29]}}]}}},
                {"id": "door", "parent": "workshop_body", "mount": "door_hinge", "parent_action": "open",
                 "views": {"S": {"frames": [{"file": "proof/door.png", "pivot": [0, 11]}]}},
                 "mount_tracks": {"open": {"S": [{"time": 0, "rotation_degrees": 0}, {"time": 1, "rotation_degrees": -70}]}}}]}))
        # the builder resolves frames relative to the job's folder, so the job sits beside `proof/`
        built = ok("build_component_bundle.py", job, "--output-dir", bundle.parent / "bundle_scratch")
        self.assertIn("BUILT", built.stdout)
        # the candidate folder already holds the reference crop, so move the built files in beside it
        for item in (bundle.parent / "bundle_scratch").iterdir():
            shutil.move(str(item), str(bundle / item.name))
        (bundle.parent / "bundle_scratch").rmdir()
        gate = run("validate_component_bundle.py", bundle, "--approval-gate")
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        self.assertIn("mandatory parent cleanup technical gate", gate.stdout)
        data = json.loads((bundle / "workshop_v001.bundle.json").read_text())
        self.assertEqual(data["validation"]["parent_cleanup"], "passed_declared_pixel_check")
        self.assertEqual(data["visual_review_protocol"], "review_packet")

        # the two loose props become their own measured sheet in the same candidate
        props_job = self.work / "props_job.json"
        for name in ("workbench", "spanner"):
            sprites[name].save(self.work / f"{name}.png")
        props_job.write_text(json.dumps({"name": "workshop_props_v001", "asset_id": "workshop_props", "columns": 2, "spacing": 3,
                                         "frames": [{"file": "workbench.png", "name": "workbench", "pivot": [0, 8]}, {"file": "spanner.png", "name": "spanner", "pivot": [0, 3]}]}))
        ok("build_sheet_atlas.py", props_job, "--output-dir", bundle)
        ok("validate_sheet_atlas.py", bundle / "workshop_props_v001.png", bundle / "workshop_props_v001.atlas.json")

        # human review boards: approved crop, original, clean parent, plate, removal regions, uncertain regions, props side by side
        uncertain = Image.new("L", (50, 40), 0)
        uncertain.paste(255, PARTS["workbench"])
        uncertain.save(bundle / "uncertain_workbench.mask.png")
        (bundle / "review_spec.json").write_text(json.dumps({
            "asset_id": "workshop", "revision": "v001", "art_style_id": "illustrated",
            "approved_reference": {"file": f"reference/{packet['reference_crop']}", "crop_packet": "reference/reference.packet.json",
                                   "sha256": packet["reference_crop_sha256"], "mockup_id": "workshop-scene", "mockup_revision": "v001"},
            "expected_component_ids": ["door", "workbench", "spanner"], "inventory_audit": "complete_for_visible_reference", "occlusion_audit": "completed",
            "uncertain_regions": [{"id": "wall_behind_workbench", "mask": "uncertain_workbench.mask.png", "evidence_status": "inferred",
                                   "reason": "the wall behind the workbench was never visible"}]}))
        cleanup = next((bundle / "parent_cleanup").glob("*/cleanup.json"))
        ok("visual_review_cleanup.py", "prepare", "--cleanup", cleanup, "--review-spec", bundle / "review_spec.json", "--output-dir", bundle / "visual_review")
        review_packet = bundle / "visual_review" / "visual_review.packet.json"
        with Image.open(bundle / "visual_review" / "visual_review_board.png") as board:
            self.assertGreater(board.width, 800)
        decision = {"asset_id": "workshop", "revision": "v001", "packet_sha256": digest(review_packet), "decision": "approved", "reviewer_type": "user",
                    "user_approval_reference": "REHEARSAL stand-in, not a user decision", "component_ids_approved": ["door", "spanner", "workbench"],
                    "uncertainty_ids_acknowledged": ["wall_behind_workbench"], "reviewed_inventory": True, "reviewed_silhouettes": True,
                    "reviewed_clean_background": True}
        (bundle / "visual_review" / "decision.json").write_text(json.dumps(decision))
        ok("visual_review_cleanup.py", "verify", "--packet", review_packet, "--decision", bundle / "visual_review" / "decision.json")

        # register, approve through the lifecycle, audit, select, then change a file and watch the audit block it
        registered = self.life("register-asset", "--id", "workshop", "--revision", "v001", "--bundle", f"{OUT}/assets/generated/workshop_v001",
                               "--source-mockup", "workshop-scene:v001")
        self.assertEqual((registered["technical_validation"], registered["technical_issues"]), ("passed", []))
        promoted = self.life("approve", "--id", "workshop", "--user-approval-ref", "REHEARSAL stand-in, not a user decision",
                             "--visual-review", "visual_review/visual_review.packet.json", "visual_review/decision.json")
        self.assertEqual(promoted["status"], "approved")
        self.assertEqual(promoted["engine_validation"], "not_assessed_by_approval")
        self.assertEqual(self.life("audit", "--id", "workshop")["status"], "consistent")
        self.assertEqual([r["id"] for r in self.life("select", "--kind", "assets", "--stage", "approved")["eligible"]], ["workshop"])
        approved_bundle = self.root / OUT / "assets/approved/workshop_v001"
        self.assertTrue((approved_bundle / "visual_review" / "visual_review_board.png").is_file())
        self.assertEqual(self.life("reconcile-assets")["status"], "consistent")

        sheet = approved_bundle / "workshop_props_v001.png"
        with Image.open(sheet) as opened:
            pixels = opened.convert("RGBA")
        pixels.putpixel((0, 0), (1, 2, 3, 255))
        pixels.save(sheet)
        blocked = run("gamearts_asset_lifecycle.py", "audit", "--id", "workshop", *map(str, self.game))
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("approved artifact bytes changed", blocked.stdout)

        # the mockup this asset came from is rejected: the dependent asset is named, and revoking the asset is clean
        revoked_mockup = self.life("revoke", "--kind", "mockups", "--id", "workshop-scene", "--revision", "v001", "--reason", "REHEARSAL: direction changed")
        self.assertEqual(revoked_mockup["dependents"], [{"asset_id": "workshop", "status": "approved"}])
        revoked_asset = self.life("revoke", "--kind", "assets", "--id", "workshop", "--reason", "built on a revoked mockup", "--replaced-by", "workshop_v002")
        self.assertEqual(revoked_asset["status"], "revoked")
        self.assertEqual(self.life("select", "--kind", "assets", "--stage", "approved")["eligible"], [])
        self.assertTrue((self.root / OUT / "assets/revoked/workshop_v001/workshop_v001.bundle.json").is_file())
        self.assertEqual(self.life("reconcile")["status"], "consistent")


if __name__ == "__main__":
    unittest.main()
