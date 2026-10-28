"""Every script is run the way an agent runs it: as a command, with its arguments, exit status and output."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import digest, make_mockup, make_sheet, picture, shaded_picture, write_settings

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
OUT = ".gamearts/outputs"


def run(script, *args, cwd=None):
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True, cwd=cwd)
    return result


def run_json(script, *args):
    result = run(script, *args)
    assert result.returncode == 0, f"{script} {args}: exit {result.returncode}\n{result.stdout}\n{result.stderr}"
    return json.loads(result.stdout)


class LifecycleCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        write_settings(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def life(self, *args):
        return run("gamearts_asset_lifecycle.py", *args, "--game-root", self.root)

    def life_json(self, *args):
        return run_json("gamearts_asset_lifecycle.py", *args, "--game-root", self.root)

    def test_the_whole_lifecycle_through_the_command_line(self):
        self.assertTrue(self.life_json("check-settings")["owner_confirmed"])
        image, metadata = make_mockup(self.root, "market", "v001", "scene")
        registered = self.life_json("register", "--metadata", metadata, "--image", image)
        self.assertEqual(registered["status"], "generated")
        audit = self.life_json("audit-mockup", "--id", "market", "--revision", "v001")
        self.assertEqual((audit["status"], audit["issues"]), ("consistent", []))
        approved = self.life_json("approve-mockup", "--id", "market", "--revision", "v001", "--user-approval-ref", "yes in chat")
        self.assertEqual(approved["status"], "approved")
        folder = self.root / OUT / "assets/generated/lamp_v001"
        folder.mkdir(parents=True)
        make_sheet(folder, "lamp_v001_sheet", "lamp")
        registered_asset = self.life_json("register-asset", "--id", "lamp", "--revision", "v001",
                                          "--bundle", f"{OUT}/assets/generated/lamp_v001", "--source-mockup", "market:v001")
        self.assertEqual(registered_asset["technical_validation"], "passed")
        self.assertEqual(self.life_json("audit", "--id", "lamp")["asset_id"], "lamp")  # a generated asset audits without blocking issues
        promoted = self.life_json("approve", "--id", "lamp", "--user-approval-ref", "looks right")
        self.assertEqual(promoted["status"], "approved")
        self.assertEqual(self.life_json("audit", "--id", "lamp")["status"], "consistent")
        selected = self.life_json("select", "--kind", "assets", "--stage", "approved")
        self.assertEqual([r["id"] for r in selected["eligible"]], ["lamp"])
        self.assertEqual(selected["blocked"], [])
        listed = self.life_json("list", "--kind", "assets", "--status", "approved")
        self.assertEqual(len(listed), 1)
        revoked = self.life_json("revoke", "--kind", "assets", "--id", "lamp", "--reason", "wrong scale", "--replaced-by", "lamp_v002")
        self.assertEqual(revoked["status"], "revoked")
        restored = self.life_json("restore", "--kind", "assets", "--id", "lamp", "--revision", "v001", "--user-restore-ref", "put it back")
        self.assertEqual(restored["status"], "generated")
        self.assertEqual(self.life_json("reconcile")["status"], "consistent")
        self.assertEqual(self.life_json("reconcile-assets")["status"], "consistent")

    def test_a_blocked_operation_exits_1_names_the_problem_and_changes_nothing(self):
        def state():  # `system/` only holds the (empty) lock file and backups; nothing else may appear
            return sorted(p.relative_to(self.root).as_posix() for p in (self.root / ".gamearts").rglob("*") if "system" not in p.parts)

        before = state()
        result = self.life("approve-mockup", "--id", "ghost", "--revision", "v001", "--user-approval-ref", "yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("BLOCKED", result.stderr)
        self.assertEqual(state(), before)
        self.assertFalse((self.root / OUT).exists())

    def test_audit_exits_1_with_the_issues_when_an_asset_is_inconsistent(self):
        image, metadata = make_mockup(self.root, "market", "v001", "scene")
        self.life_json("register", "--metadata", metadata, "--image", image)
        audit = self.life("audit-mockup", "--id", "market", "--revision", "v001")
        self.assertEqual(audit.returncode, 0)
        (self.root / OUT / "mockups/generated" / image.name).write_bytes(b"changed")
        bad = self.life("audit-mockup", "--id", "market", "--revision", "v001")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("hash mismatch", bad.stdout)

    def test_register_generated_through_the_command_line_uses_the_saved_image_generator(self):
        from PIL import Image
        write_settings(self.root, image_generation={"tool": "built_in_image_gen"})
        output = self.root.parent / f"{self.root.name}_tool_output.png"
        shaded_picture((50, 30), (60, 130, 70)).save(output)
        prompt = self.root.parent / f"{self.root.name}_prompt.txt"
        prompt.write_text("A village pitch in warm afternoon light.", encoding="utf-8")
        registered = self.life_json("register-generated", "--image", output, "--id", "pitch", "--revision", "v001", "--scope", "scene",
                                    "--prompt-file", prompt)
        self.assertEqual((registered["status"], registered["image_generator_setting"]), ("generated", "built_in_image_gen"))
        audit = self.life_json("audit-mockup", "--id", "pitch", "--revision", "v001")
        self.assertEqual((audit["status"], audit["issues"]), ("consistent", []))
        wrong = self.life("register-generated", "--image", output, "--id", "pitch", "--revision", "v002", "--scope", "scene",
                          "--prompt-file", prompt, "--tool-mode", "cli_image_gen")
        self.assertEqual(wrong.returncode, 1)
        self.assertIn("image generator is built_in_image_gen", wrong.stderr)

    def test_register_refuses_a_mockup_from_the_wrong_image_generator_through_the_command_line(self):
        write_settings(self.root, image_generation={"tool": "connected_tool", "tool_name": "Studio Painter"})
        self.assertEqual(self.life_json("check-settings")["image_generation"]["tool_name"], "Studio Painter")
        image, metadata = make_mockup(self.root, "market", "v001", "scene")
        refused = self.life("register", "--metadata", metadata, "--image", image)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("BLOCKED", refused.stderr)
        self.assertIn("image generator", refused.stderr)

    def test_import_mockup_through_the_command_line(self):
        from PIL import Image
        outside = self.root.parent / f"{self.root.name}_outside.png"
        shaded_picture((40, 30), (30, 120, 60)).save(outside)
        before = outside.read_bytes()
        imported = self.life_json("import-mockup", "--source", outside, "--id", "clubhouse", "--revision", "v001", "--scope", "asset",
                                  "--user-approval-ref", "user: it is already approved")
        self.assertEqual(imported["status"], "approved")
        self.assertEqual(imported["import_checks"]["size"], [40, 30])
        self.assertEqual(outside.read_bytes(), before)
        self.assertEqual(self.life_json("reconcile")["status"], "consistent")
        bad = self.life("import-mockup", "--source", outside, "--id", "Bad Id", "--revision", "v001", "--scope", "asset")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("BLOCKED", bad.stderr)
        self.assertEqual(self.life_json("list", "--kind", "mockups")[0]["id"], "clubhouse")

    def test_the_help_text_lists_every_operation(self):
        text = run("gamearts_asset_lifecycle.py", "--help").stdout
        for operation in ("check-settings", "register", "register-generated", "import-mockup", "audit-mockup", "approve-mockup", "register-asset", "audit", "approve", "select",
                          "list", "revoke", "restore", "reconcile", "reconcile-assets"):
            self.assertIn(operation, text)


class BuilderCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sheet_builder_and_validator(self):
        from gamearts_testkit import key_image
        key_image((12, 10), {(4, 5): (20, 50, 90, 255)}).save(self.root / "frame.png")
        job = self.root / "job.json"
        job.write_text(json.dumps({"name": "cli_sheet_v001", "asset_id": "cli", "columns": 2, "spacing": 3,
                                   "frames": [{"file": "frame.png", "name": "a", "pivot": [4, 9]}, {"file": "frame.png", "name": "b", "pivot": [4, 9]}]}))
        out = self.root / "out"
        built = run("build_sheet_atlas.py", job, "--output-dir", out)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        self.assertIn("BUILT", built.stdout)
        checked = run("validate_sheet_atlas.py", out / "cli_sheet_v001.png", out / "cli_sheet_v001.atlas.json")
        self.assertEqual(checked.returncode, 0, checked.stdout)
        again = run("build_sheet_atlas.py", job, "--output-dir", out)
        self.assertEqual(again.returncode, 1)
        self.assertIn("ERROR", again.stderr)

    def test_component_bundle_builder_validator_and_the_approval_gate(self):
        from test_component_bundle import ComponentTests
        config = ComponentTests().fixture(self.root)
        job = self.root / "component_job.json"
        job.write_text(json.dumps(config))
        out = self.root / "bundle"
        built = run("build_component_bundle.py", job, "--output-dir", out)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        plain = run("validate_component_bundle.py", out)
        self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr)
        self.assertIn("NOT APPROVAL VERIFIED", plain.stdout)
        gate = run("validate_component_bundle.py", out, "--approval-gate")
        self.assertEqual(gate.returncode, 1)
        self.assertIn("missing mandatory parent-cleanup evidence", gate.stdout)

    def test_parent_cleanup_command_and_report(self):
        from test_validate_parent_cleanup import example
        cleanup = example(self.root)
        report = self.root / "report.json"
        passed = run("validate_parent_cleanup.py", cleanup, "--strict-props", "--report", report)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertEqual(json.loads(report.read_text())["technical_status"], "passed")
        job = json.loads(cleanup.read_text())
        del job["detached_components"][0]["source_offset"]
        cleanup.write_text(json.dumps(job))
        blocked = run("validate_parent_cleanup.py", cleanup, "--strict-props")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("BLOCKED", blocked.stdout)

    def test_reference_crop_prepare_and_verify(self):
        write_settings(self.root)
        mockup_image, metadata = make_mockup(self.root, "scene-1", "v001", "scene")
        game = ["--game-root", self.root]
        run_json("gamearts_asset_lifecycle.py", "register", *game, "--metadata", metadata, "--image", mockup_image)
        run_json("gamearts_asset_lifecycle.py", "approve-mockup", *game, "--id", "scene-1", "--revision", "v001", "--user-approval-ref", "yes")
        approved = next((self.root / OUT / "mockups/approved").glob("*.png"))
        job = self.root / "reference_job.json"
        job.write_text(json.dumps({
            "asset_id": "tower_v001", "asset_class": "static_structure",
            "approved_mockup": {"id": "scene-1", "revision": "v001", "approval_status": "approved",
                                "file": approved.relative_to(self.root).as_posix(), "sha256": digest(approved)},
            "region": {"id": "tower", "rect": [8, 6, 20, 14], "padding_px": 2}, "identity_lock": ["tall roof"]}))
        out = self.root / OUT / "assets/generated/tower_v001/reference"
        prepared = run("prepare_reference_crop.py", "prepare", *game, "--job", job, "--output-dir", out)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        packet = out / "reference.packet.json"
        self.assertTrue(packet.is_file())
        from gamearts_testkit import key_image
        candidate = self.root / "candidate.png"
        key_image((16, 16), {(8, 8): (11, 22, 33, 255)}).save(candidate)
        packet_body = json.loads(packet.read_text())
        receipt = self.root / "receipt.json"
        receipt.write_text(json.dumps({"reference_crop_sha256": packet_body["reference_crop_sha256"], "reference_image_path": packet_body["reference_crop"],
                                       "image_input_attached": True, "tool_invocation_id": "t-1", "candidate_image": str(candidate),
                                       "candidate_sha256": digest(candidate)}))
        verified = run("prepare_reference_crop.py", "verify", "--packet", packet, "--receipt", receipt)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertEqual(json.loads(verified.stdout)["status"], "candidate_pending_visual_review")
        missing = run("prepare_reference_crop.py", "verify", "--packet", packet, "--receipt", self.root / "nope.json")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("BLOCKED", missing.stderr)

    def test_visual_review_prepare_and_verify(self):
        from test_visual_review_cleanup import decision, fixture
        cleanup, review, _ = fixture(self.root)
        out = self.root / "review"
        prepared = run("visual_review_cleanup.py", "prepare", "--cleanup", cleanup, "--review-spec", review, "--output-dir", out)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        packet = out / "visual_review.packet.json"
        vote = out / "decision.json"
        vote.write_text(json.dumps(decision(packet)))
        result = self.root / "result.json"
        verified = run("visual_review_cleanup.py", "verify", "--packet", packet, "--decision", vote, "--result", result)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertEqual(json.loads(result.read_text())["review_status"], "user_visual_approval_recorded")
        bad = json.loads(vote.read_text())
        bad["reviewer_type"] = "agent"
        vote.write_text(json.dumps(bad))
        self.assertEqual(run("visual_review_cleanup.py", "verify", "--packet", packet, "--decision", vote).returncode, 1)


class UpdaterCommandTests(unittest.TestCase):
    def test_update_before_bootstrap_exits_1_with_a_clear_message(self):
        with tempfile.TemporaryDirectory() as game:
            result = run("sync_local_agents.py", "update", "--game-root", game)
            self.assertEqual(result.returncode, 1)
            self.assertIn("bootstrap is required", result.stderr)

    def test_a_missing_game_folder_is_reported(self):
        result = run("sync_local_agents.py", "update", "--game-root", Path(tempfile.gettempdir()) / "definitely-not-a-game-folder")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)


if __name__ == "__main__":
    unittest.main()
