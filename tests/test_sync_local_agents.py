"""Regression tests for local Claude/Codex Game Arts safe auto-updates."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_local_agents.py"
spec = importlib.util.spec_from_file_location("sync_local_agents", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class LocalAgentSyncTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "framework"
        game = root / "game"
        source.mkdir()
        game.mkdir()
        (source / sync.MASTER).write_text("# Latest Game Arts\n")
        for folder in (".agents/skills/game-arts", ".claude/skills/game-arts"):
            path = source / folder
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text("version one\n")
        scripts = source / "scripts"
        scripts.mkdir()
        shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
        instructions = game / ".gamearts" / "instructions"
        instructions.mkdir(parents=True)
        (instructions / "personal.md").write_text("Keep my art decisions\n")
        (game / ".gamearts" / "project.json").write_text('{"art_style": "custom"}\n')
        outputs = game / ".gamearts" / "outputs" / "mockups" / "approved"
        outputs.mkdir(parents=True)
        (outputs / "approved.png").write_bytes(b"do not overwrite")
        (game / "AGENTS.md").write_text("# My agent rules\n\nMy original guidance.\n")
        (game / "CLAUDE.md").write_text("# My Claude guidance\n")
        config = game / ".claude" / "settings.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"permissions": {"allow": ["Read"]},
                                      "hooks": {"SessionStart": [{
                                        "matcher": "startup",
                                        "hooks": [{"type": "command", "command": "echo existing"}]
                                      }]}}))
        return source, game

    def test_updates_both_skills_without_changing_personal_game_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, game = self.fixture(Path(tmp))
            result = sync.sync(source, game)
            self.assertFalse(result["conflicts"])
            self.assertTrue((game / ".agents/skills/game-arts/SKILL.md").is_file())
            self.assertTrue((game / ".claude/skills/game-arts/SKILL.md").is_file())
            self.assertEqual((game / ".gamearts/instructions/personal.md").read_text(),
                             "Keep my art decisions\n")
            self.assertEqual((game / ".gamearts/outputs/mockups/approved/approved.png").read_bytes(),
                             b"do not overwrite")
            self.assertIn("My original guidance.", (game / "AGENTS.md").read_text())
            self.assertIn(sync.BEGIN, (game / "AGENTS.md").read_text())
            src = source / ".agents/skills/game-arts/SKILL.md"
            src.write_text("version two\n")
            out = sync.sync(source, game)
            self.assertIn(".agents/skills/game-arts/SKILL.md", out["updated"])
            self.assertEqual((game / ".agents/skills/game-arts/SKILL.md").read_text(),
                             "version two\n")
            self.assertEqual((game / ".claude/skills/game-arts/SKILL.md").read_text(),
                             "version one\n")

    def test_preserves_locally_modified_managed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, game = self.fixture(Path(tmp))
            sync.sync(source, game)
            source_file = source / ".agents/skills/game-arts/SKILL.md"
            installed = game / ".agents/skills/game-arts/SKILL.md"
            source_file.write_text("new upstream\n")
            installed.write_text("my local custom content\n")
            result = sync.sync(source, game)
            self.assertTrue(result["conflicts"])
            self.assertEqual(installed.read_text(), "my local custom content\n")

    def test_one_time_adopt_backs_up_preexisting_framework_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, game = self.fixture(Path(tmp))
            current = game / ".claude/skills/game-arts/SKILL.md"
            current.parent.mkdir(parents=True)
            current.write_text("old installed framework\n")
            first = sync.sync(source, game)
            self.assertTrue(first["conflicts"])
            self.assertEqual(current.read_text(), "old installed framework\n")
            second = sync.sync(source, game, adopt=True)
            self.assertFalse(second["conflicts"])
            self.assertEqual(current.read_text(), "version one\n")
            backup_files = list((game / ".gamearts/system/backups").rglob("SKILL.md"))
            self.assertEqual(len(backup_files), 1)
            self.assertEqual(backup_files[0].read_text(), "old installed framework\n")

    def test_authorized_adoption_retires_prior_master_with_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, game = self.fixture(Path(tmp))
            old = game / "GAME_ARTS_MASTER_STANDARD_v7.6.md"
            old.write_text("# Prior standard\n")
            sync.sync(source, game, adopt=False)
            self.assertTrue(old.exists())
            sync.sync(source, game, adopt=True)
            self.assertFalse(old.exists())
            copies = list((game / ".gamearts/system/backups").rglob(old.name))
            self.assertEqual(len(copies), 1)
            self.assertEqual(copies[0].read_text(), "# Prior standard\n")
            self.assertTrue((game / sync.MASTER).is_file())

    def test_hook_installation_is_idempotent_and_retains_other_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, game = self.fixture(Path(tmp))
            sync.sync(source, game)
            sync.install_hooks(game)
            sync.install_hooks(game)
            for location in (".claude/settings.json", ".codex/hooks.json"):
                settings = json.loads((game / location).read_text())
                groups = settings["hooks"]["SessionStart"]
                handlers = [h for g in groups for h in g.get("hooks", [])]
                owned = [h for h in handlers if "sync_local_agents.py" in h["command"]]
                self.assertEqual(len(owned), 1)
                self.assertIn("--game-root", owned[0]["command"])
                if location.startswith(".claude"):
                    self.assertEqual(settings["permissions"]["allow"], ["Read"])
                    self.assertTrue(any(h["command"] == "echo existing" for h in handlers))

    def test_untrusted_existing_user_script_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, game = self.fixture(Path(tmp))
            (source / "scripts/prepare_reference_crop.py").write_text("framework script\n")
            target = game / "scripts/prepare_reference_crop.py"
            target.parent.mkdir()
            target.write_text("my own script\n")
            result = sync.sync(source, game)
            self.assertTrue(result["conflicts"])
            self.assertEqual(target.read_text(), "my own script\n")

    def test_updater_lock_prevents_concurrent_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, game = self.fixture(Path(tmp))
            with sync.lock(game):
                with self.assertRaisesRegex(ValueError, "Another Game Arts sync"):
                    with sync.lock(game):
                        pass
            self.assertFalse((game / ".gamearts/system/agent-sync.lock").exists())


if __name__ == "__main__":
    unittest.main()
