"""Local Claude/Codex Game Arts updater: safe installs, deletion propagation, crash recovery, hooks, fetch and verification."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_local_agents.py"
sys.path.insert(0, str(SCRIPT.parent))
import gamearts_common as common  # noqa: E402

spec = importlib.util.spec_from_file_location("sync_local_agents", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

LEGACY = ROOT / "tests" / "fixtures" / "legacy_sync_local_agents.py"
legacy_spec = importlib.util.spec_from_file_location("legacy_sync_local_agents", LEGACY)
legacy = importlib.util.module_from_spec(legacy_spec)
legacy_spec.loader.exec_module(legacy)

REV_A, REV_B = "a" * 40, "b" * 40
MASTER = "GAME_ARTS_MASTER_STANDARD_v7.7.md"


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source, self.game = self.fixture(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def fixture(self, root):
        source, game = root / "framework", root / "game"
        source.mkdir()
        game.mkdir()
        (source / MASTER).write_text("# Latest Game Arts\n")
        for folder in (".agents/skills/game-arts", ".claude/skills/game-arts"):
            (source / folder).mkdir(parents=True)
            (source / folder / "SKILL.md").write_text("version one\n")
        (source / "scripts").mkdir()
        shutil.copyfile(SCRIPT, source / "scripts" / SCRIPT.name)
        instructions = game / ".gamearts" / "instructions"
        instructions.mkdir(parents=True)
        (instructions / "personal.md").write_text("Keep my art decisions\n")
        (game / ".gamearts" / "project.json").write_text('{"art_style": "custom"}\n')
        approved = game / ".gamearts" / "outputs" / "mockups" / "approved"
        approved.mkdir(parents=True)
        (approved / "approved.png").write_bytes(b"do not overwrite")
        (game / "AGENTS.md").write_text("# My agent rules\n\nMy original guidance.\n")
        (game / "CLAUDE.md").write_text("# My Claude guidance\n")
        config = game / ".claude" / "settings.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"permissions": {"allow": ["Read"]}, "hooks": {"SessionStart": [{
            "matcher": "startup", "hooks": [{"type": "command", "command": "echo existing"}]}]}}))
        return source, game

    def state(self):
        return json.loads((self.game / sync.STATE).read_text())

    def add_framework_file(self, rel, text="framework file\n"):
        path = self.source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path


class InstallTests(Fixture):
    def test_updates_both_skills_without_changing_personal_game_data(self):
        result = sync.sync(self.source, self.game)
        self.assertFalse(result["conflicts"])
        self.assertTrue((self.game / ".agents/skills/game-arts/SKILL.md").is_file())
        self.assertTrue((self.game / ".claude/skills/game-arts/SKILL.md").is_file())
        self.assertEqual((self.game / ".gamearts/instructions/personal.md").read_text(), "Keep my art decisions\n")
        self.assertEqual((self.game / ".gamearts/outputs/mockups/approved/approved.png").read_bytes(), b"do not overwrite")
        self.assertIn("My original guidance.", (self.game / "AGENTS.md").read_text())
        self.assertIn(sync.BEGIN, (self.game / "AGENTS.md").read_text())
        (self.source / ".agents/skills/game-arts/SKILL.md").write_text("version two\n")
        out = sync.sync(self.source, self.game)
        self.assertIn(".agents/skills/game-arts/SKILL.md", out["updated"])
        self.assertEqual((self.game / ".agents/skills/game-arts/SKILL.md").read_text(), "version two\n")
        self.assertEqual((self.game / ".claude/skills/game-arts/SKILL.md").read_text(), "version one\n")

    def test_preserves_locally_modified_managed_files(self):
        sync.sync(self.source, self.game)
        installed = self.game / ".agents/skills/game-arts/SKILL.md"
        (self.source / ".agents/skills/game-arts/SKILL.md").write_text("new upstream\n")
        installed.write_text("my local custom content\n")
        result = sync.sync(self.source, self.game)
        self.assertTrue(result["conflicts"])
        self.assertEqual(installed.read_text(), "my local custom content\n")

    def test_one_time_adopt_backs_up_preexisting_framework_path(self):
        current = self.game / ".claude/skills/game-arts/SKILL.md"
        current.parent.mkdir(parents=True)
        current.write_text("old installed framework\n")
        self.assertTrue(sync.sync(self.source, self.game)["conflicts"])
        self.assertEqual(current.read_text(), "old installed framework\n")
        self.assertFalse(sync.sync(self.source, self.game, adopt=True)["conflicts"])
        self.assertEqual(current.read_text(), "version one\n")
        backups = list((self.game / ".gamearts/system/backups").rglob("SKILL.md"))
        self.assertEqual([b.read_text() for b in backups], ["old installed framework\n"])

    def test_untrusted_existing_user_script_is_not_replaced(self):
        self.add_framework_file("scripts/prepare_reference_crop.py", "framework script\n")
        target = self.game / "scripts/prepare_reference_crop.py"
        target.parent.mkdir()
        target.write_text("my own script\n")
        self.assertTrue(sync.sync(self.source, self.game)["conflicts"])
        self.assertEqual(target.read_text(), "my own script\n")

    def test_the_updater_lock_prevents_concurrent_syncs(self):
        with sync.lock(self.game):
            with self.assertRaisesRegex(ValueError, "Another Game Arts sync"):
                with sync.lock(self.game):
                    pass
        with sync.lock(self.game):  # released afterwards
            pass


class PresetShippingTests(Fixture):
    """Style presets and engine profiles (plan P10.4) are shipped data: installed, updated and removed like the other framework folders."""

    def test_presets_are_installed_updated_and_removed_with_the_framework(self):
        style = self.add_framework_file("presets/styles/pixel_mid.json", '{"id": "pixel_mid"}\n')
        engine = self.add_framework_file("presets/engines/generic.json", '{"id": "generic"}\n')
        result = sync.sync(self.source, self.game)
        self.assertFalse(result["conflicts"])
        self.assertTrue((self.game / "presets/styles/pixel_mid.json").is_file())
        self.assertTrue((self.game / "presets/engines/generic.json").is_file())
        engine.write_text('{"id": "generic", "summary": "changed"}\n')
        sync.sync(self.source, self.game)
        self.assertIn("changed", (self.game / "presets/engines/generic.json").read_text())
        style.unlink()
        result = sync.sync(self.source, self.game)
        self.assertIn("presets/styles/pixel_mid.json", result["removed"])
        self.assertFalse((self.game / "presets/styles/pixel_mid.json").exists())

    def test_a_preset_file_the_user_edited_is_kept_and_reported(self):
        self.add_framework_file("presets/styles/pixel_mid.json", '{"id": "pixel_mid"}\n')
        sync.sync(self.source, self.game)
        (self.game / "presets/styles/pixel_mid.json").write_text('{"id": "pixel_mid", "mine": true}\n')
        self.add_framework_file("presets/styles/pixel_mid.json", '{"id": "pixel_mid", "upstream": true}\n')
        result = sync.sync(self.source, self.game)
        self.assertTrue(any("pixel_mid.json" in item for item in result["conflicts"]))
        self.assertIn("mine", (self.game / "presets/styles/pixel_mid.json").read_text())


class MasterDiscoveryTests(Fixture):
    def test_the_master_is_found_by_pattern_so_a_rename_does_not_strand_games(self):
        sync.sync(self.source, self.game)
        (self.source / MASTER).rename(self.source / "GAME_ARTS_MASTER_STANDARD.md")
        result = sync.sync(self.source, self.game)
        self.assertEqual(result["removed"], [MASTER])
        self.assertIn("GAME_ARTS_MASTER_STANDARD.md", result["new"])
        self.assertFalse((self.game / MASTER).exists())
        self.assertIn("`GAME_ARTS_MASTER_STANDARD.md`", (self.game / "CLAUDE.md").read_text())

    def test_a_bridge_under_the_old_name_beside_the_real_master_is_ignored_and_removed_from_games(self):
        sync.sync(self.source, self.game)  # what the old updater did: the old-named file is the master in the game
        self.assertTrue((self.game / MASTER).is_file())
        (self.source / "GAME_ARTS_MASTER_STANDARD.md").write_bytes(b"# The real standard\n")
        (self.source / MASTER).write_bytes(b"# Moved\n\nPointer only.\n")
        self.assertEqual(sync.master_name(self.source), "GAME_ARTS_MASTER_STANDARD.md")
        result = sync.sync(self.source, self.game)
        self.assertEqual(result["new"], ["GAME_ARTS_MASTER_STANDARD.md"])
        self.assertEqual(result["removed"], [MASTER])
        self.assertEqual(result["conflicts"], [])
        self.assertFalse((self.game / MASTER).exists())
        self.assertIn("`GAME_ARTS_MASTER_STANDARD.md`", (self.game / "CLAUDE.md").read_text())

    def test_zero_or_several_masters_are_refused(self):
        (self.source / "GAME_ARTS_MASTER_STANDARD_extra.md").write_text("second\n")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            sync.sync(self.source, self.game)
        (self.source / "GAME_ARTS_MASTER_STANDARD_extra.md").unlink()
        (self.source / MASTER).unlink()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            sync.sync(self.source, self.game)

    def test_authorized_adoption_retires_a_prior_master_with_backup(self):
        old = self.game / "GAME_ARTS_MASTER_STANDARD_v7.6.md"
        old.write_text("# Prior standard\n")
        sync.sync(self.source, self.game, adopt=False)
        self.assertTrue(old.exists())
        sync.sync(self.source, self.game, adopt=True)
        self.assertFalse(old.exists())
        copies = list((self.game / ".gamearts/system/backups").rglob(old.name))
        self.assertEqual([c.read_text() for c in copies], ["# Prior standard\n"])
        self.assertTrue((self.game / MASTER).is_file())


class DeletionTests(Fixture):
    def test_a_file_removed_upstream_is_removed_when_unedited_with_a_backup_and_empty_folders_pruned(self):
        self.add_framework_file("docs/OLD.md", "old doc\n")
        self.add_framework_file("legacy_area_unused/ignored.md", "not a synced folder\n")
        sync.sync(self.source, self.game)
        self.assertTrue((self.game / "docs/OLD.md").is_file())
        (self.source / "docs/OLD.md").unlink()
        (self.source / "docs").rmdir()
        result = sync.sync(self.source, self.game)
        self.assertEqual(result["removed"], ["docs/OLD.md"])
        self.assertFalse((self.game / "docs").exists())  # the emptied folder went with it
        self.assertEqual([p.read_text() for p in (self.game / ".gamearts/system/backups").rglob("OLD.md")], ["old doc\n"])
        self.assertNotIn("docs/OLD.md", self.state()["files"])

    def test_a_removed_file_you_edited_is_kept_reported_once_and_then_yours(self):
        self.add_framework_file("docs/OLD.md", "old doc\n")
        sync.sync(self.source, self.game)
        (self.game / "docs/OLD.md").write_text("my edits\n")
        (self.source / "docs/OLD.md").unlink()
        first = sync.sync(self.source, self.game)
        self.assertEqual(first["kept_after_upstream_removal"], ["docs/OLD.md"])
        self.assertEqual((self.game / "docs/OLD.md").read_text(), "my edits\n")
        self.assertFalse(first["conflicts"])
        second = sync.sync(self.source, self.game)
        self.assertEqual(second["kept_after_upstream_removal"], [])
        self.assertEqual((self.game / "docs/OLD.md").read_text(), "my edits\n")

    def test_an_incomplete_checkout_removes_nothing(self):
        sync.sync(self.source, self.game)
        (self.source / "scripts" / SCRIPT.name).unlink()
        with self.assertRaisesRegex(ValueError, "Incomplete framework checkout"):
            sync.sync(self.source, self.game)
        self.assertTrue((self.game / ".claude/skills/game-arts/SKILL.md").is_file())
        self.assertTrue((self.game / MASTER).is_file())

    def test_files_that_were_never_tracked_are_never_deleted(self):
        sync.sync(self.source, self.game)
        mine = self.game / "docs/my_notes.md"
        mine.parent.mkdir(exist_ok=True)
        mine.write_text("mine\n")
        sync.sync(self.source, self.game)
        self.assertEqual(mine.read_text(), "mine\n")


class StateTests(Fixture):
    def test_a_failure_midway_keeps_completed_work_and_never_advances_the_revision(self):
        sync.sync(self.source, self.game, rev=REV_A)
        for n in range(4):
            self.add_framework_file(f"docs/new_{n}.md", f"document {n}\n")
        real = common.atomic_write_bytes
        writes = {"n": 0}

        def dying(path, data):
            if Path(path).name.startswith("new_"):
                writes["n"] += 1
                if writes["n"] == 3:
                    raise OSError("disk full")
            return real(path, data)

        with mock.patch.object(common, "atomic_write_bytes", side_effect=dying):
            with self.assertRaisesRegex(OSError, "disk full"):
                sync.sync(self.source, self.game, rev=REV_B)
        state = self.state()
        self.assertEqual(state["revision"], REV_A)  # the run did not finish, so it is not recorded as done
        self.assertIn("docs/new_0.md", state["files"])
        self.assertNotIn("docs/new_2.md", state["files"])
        retry = sync.sync(self.source, self.game, rev=REV_B)
        self.assertEqual(retry["conflicts"], [])
        self.assertEqual(self.state()["revision"], REV_B)
        self.assertEqual(self.state()["pending"], {})

    def test_a_crash_between_writing_a_file_and_recording_it_is_not_a_false_conflict(self):
        sync.sync(self.source, self.game, rev=REV_A)
        self.add_framework_file("docs/guide.md", "guide v1\n")
        sync.sync(self.source, self.game, rev=REV_A)
        self.add_framework_file("docs/guide.md", "guide v2\n")
        state = self.state()
        (self.game / "docs/guide.md").write_bytes(b"guide v2\n")  # the write happened ...
        state["pending"] = {"docs/guide.md": common.sha256_bytes(b"guide v2\n")}  # ... but the run died before recording it
        common.atomic_write_json(self.game / sync.STATE, state)
        self.add_framework_file("docs/guide.md", "guide v3\n")
        result = sync.sync(self.source, self.game, rev=REV_B)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual((self.game / "docs/guide.md").read_text(), "guide v3\n")

    def test_state_from_another_repository_is_refused(self):
        sync.sync(self.source, self.game)
        state = self.state()
        state["repository"] = "https://example.invalid/other.git"
        common.atomic_write_json(self.game / sync.STATE, state)
        with self.assertRaisesRegex(ValueError, "another repository"):
            sync.sync(self.source, self.game)


class HookTests(Fixture):
    def owned(self, path):
        settings = json.loads(Path(path).read_text())
        return [h for g in settings.get("hooks", {}).get("SessionStart", []) for h in g.get("hooks", [])
                if sync.OWNED_HOOK in h["command"]]

    def test_local_scope_writes_only_the_personal_claude_file_and_keeps_other_hooks(self):
        home = self.root / "home"
        result = sync.install_hooks(self.game, "local", home=home)
        self.assertEqual(len(self.owned(self.game / ".claude/settings.local.json")), 1)
        self.assertIn(sys.executable.replace("\\", "/"), self.owned(self.game / ".claude/settings.local.json")[0]["command"])
        self.assertEqual(self.owned(self.game / ".claude/settings.json"), [])
        self.assertFalse((self.game / ".codex/hooks.json").exists())
        self.assertFalse((home / ".codex/hooks.json").exists())
        self.assertTrue(any("--codex-user-hook" in n for n in result["notes"]))
        committed = json.loads((self.game / ".claude/settings.json").read_text())
        self.assertEqual(committed["permissions"]["allow"], ["Read"])
        self.assertEqual(committed["hooks"]["SessionStart"][0]["hooks"][0]["command"], "echo existing")

    def test_the_personal_claude_file_is_excluded_from_git_without_touching_gitignore(self):
        (self.game / ".git" / "info").mkdir(parents=True)
        (self.game / ".gitignore").write_bytes(b"build/\n")
        sync.install_hooks(self.game, "local", home=self.root / "home")
        sync.install_hooks(self.game, "local", home=self.root / "home")  # idempotent
        exclude = (self.game / ".git" / "info" / "exclude").read_text().splitlines()
        self.assertEqual(exclude.count(".claude/settings.local.json"), 1)
        self.assertEqual((self.game / ".gitignore").read_bytes(), b"build/\n")  # the project's own file is untouched

    def test_without_a_git_directory_the_user_is_told_to_keep_the_personal_file_out_of_version_control(self):
        result = sync.install_hooks(self.game, "local", home=self.root / "home")
        self.assertTrue(any("keep it out of version control" in n for n in result["notes"]))

    def test_the_codex_user_hook_is_written_only_when_asked_for(self):
        home = self.root / "home"
        sync.install_hooks(self.game, "local", codex_user_hook=True, home=home)
        self.assertEqual(len(self.owned(home / ".codex/hooks.json")), 1)
        self.assertEqual(sync.install_hooks(self.game, "local", codex_user_hook=True, home=home)["changed"], [])  # idempotent

    def test_project_scope_commits_nothing_machine_specific(self):
        sync.install_hooks(self.game, "project", python_command="python3", home=self.root / "home")
        for path in (self.game / ".claude/settings.json", self.game / ".codex/hooks.json"):
            command = self.owned(path)[0]["command"]
            self.assertTrue(command.startswith("python3 "))
            self.assertNotIn(sys.executable, command)
            self.assertNotIn(str(self.game), command)
            self.assertNotIn(self.game.as_posix(), command)
        self.assertIn("$CLAUDE_PROJECT_DIR", self.owned(self.game / ".claude/settings.json")[0]["command"])
        self.assertIn("git rev-parse --show-toplevel", self.owned(self.game / ".codex/hooks.json")[0]["command"])
        self.assertEqual(self.owned(self.game / ".claude/settings.local.json") if (self.game / ".claude/settings.local.json").exists() else [], [])

    def test_changing_scope_removes_the_previous_entries_and_none_removes_all(self):
        home = self.root / "home"
        sync.install_hooks(self.game, "project", home=home)
        sync.install_hooks(self.game, "local", home=home)
        self.assertEqual(self.owned(self.game / ".claude/settings.json"), [])
        self.assertEqual(self.owned(self.game / ".codex/hooks.json"), [])
        self.assertEqual(len(self.owned(self.game / ".claude/settings.local.json")), 1)
        sync.install_hooks(self.game, "none", home=home)
        self.assertEqual(self.owned(self.game / ".claude/settings.local.json"), [])
        committed = json.loads((self.game / ".claude/settings.json").read_text())
        self.assertEqual(committed["hooks"]["SessionStart"][0]["hooks"][0]["command"], "echo existing")

    def test_removing_when_nothing_is_installed_leaves_user_files_byte_identical(self):
        before = (self.game / ".claude/settings.json").read_bytes()
        result = sync.install_hooks(self.game, "none", home=self.root / "home")
        self.assertEqual(result["changed"], [])
        self.assertEqual((self.game / ".claude/settings.json").read_bytes(), before)

    def test_paths_with_shell_metacharacters_are_refused_not_mangled(self):
        weird = self.root / "my$game"
        weird.mkdir()
        with self.assertRaisesRegex(ValueError, "Cannot put this path"):
            sync.install_hooks(weird, "local", home=self.root / "home")

    def test_the_hook_matcher_uses_documented_session_sources(self):
        sync.install_hooks(self.game, "local", home=self.root / "home")
        groups = json.loads((self.game / ".claude/settings.local.json").read_text())["hooks"]["SessionStart"]
        self.assertEqual(groups[0]["matcher"], "startup|resume")

    def test_invalid_existing_json_is_reported_not_overwritten(self):
        (self.game / ".claude/settings.local.json").write_text("{not json")
        with self.assertRaises(ValueError):
            sync.install_hooks(self.game, "local", home=self.root / "home")
        self.assertEqual((self.game / ".claude/settings.local.json").read_text(), "{not json")


class BootstrapCommandTests(Fixture):
    def bootstrap(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "bootstrap", "--source", str(self.source), "--game-root", str(self.game), *extra],
                              capture_output=True, text=True)

    def test_bootstrap_keeps_the_system_folder_out_of_git_without_touching_gitignore(self):
        (self.game / ".git" / "info").mkdir(parents=True)
        (self.game / ".gitignore").write_bytes(b"build/\n")
        first = self.bootstrap("--hooks", "none")
        self.assertIn(first.returncode, (0, 2), first.stderr)
        self.assertEqual(json.loads(first.stdout)["system_folder"], "excluded from git through .git/info/exclude")
        self.bootstrap("--hooks", "none")  # idempotent
        lines = (self.game / ".git" / "info" / "exclude").read_text().splitlines()
        self.assertEqual(lines.count(".gamearts/system/"), 1)
        self.assertEqual((self.game / ".gitignore").read_bytes(), b"build/\n")

    def test_without_a_git_directory_the_user_is_told(self):
        result = json.loads(self.bootstrap("--hooks", "none").stdout)
        self.assertIn("keep it out of version control", result["system_folder"])


class UpdateTests(Fixture):
    def fetcher(self, rev=REV_A, source=None):
        def fetch(scratch):
            checkout = Path(scratch) / "GameArtsSkills"
            shutil.copytree(source or self.source, checkout)
            return checkout, rev
        return fetch

    def bootstrap(self):
        sync.sync(self.source, self.game)

    def test_update_requires_the_one_time_bootstrap(self):
        with self.assertRaisesRegex(ValueError, "bootstrap is required"):
            sync.update(self.game, fetcher=self.fetcher())

    def test_update_installs_then_reports_up_to_date_without_touching_anything(self):
        self.bootstrap()
        (self.source / ".claude/skills/game-arts/SKILL.md").write_text("version two\n")
        first = sync.update(self.game, fetcher=self.fetcher(REV_A))
        self.assertEqual(first["revision"], REV_A)
        self.assertEqual((self.game / ".claude/skills/game-arts/SKILL.md").read_text(), "version two\n")
        before = (self.game / sync.STATE).read_bytes()
        second = sync.update(self.game, fetcher=self.fetcher(REV_A))
        self.assertTrue(second["up_to_date"])
        self.assertEqual((self.game / sync.STATE).read_bytes(), before)

    def test_a_failed_fetch_changes_nothing_and_says_so(self):
        self.bootstrap()
        before = (self.game / sync.STATE).read_bytes()

        def offline(scratch):
            raise subprocess.CalledProcessError(128, "git clone", stderr="could not resolve host")

        with self.assertRaises(subprocess.CalledProcessError):
            sync.update(self.game, fetcher=offline)
        self.assertEqual((self.game / sync.STATE).read_bytes(), before)

    def test_an_unverifiable_revision_is_refused(self):
        self.bootstrap()
        with self.assertRaisesRegex(ValueError, "revision is unverified"):
            sync.update(self.game, fetcher=self.fetcher("trusted-local-source"))

    def test_a_run_with_conflicts_is_retried_not_declared_up_to_date(self):
        self.bootstrap()
        (self.game / ".claude/skills/game-arts/SKILL.md").write_text("my edit\n")
        (self.source / ".claude/skills/game-arts/SKILL.md").write_text("upstream\n")
        first = sync.update(self.game, fetcher=self.fetcher(REV_A))
        self.assertTrue(first["conflicts"])
        again = sync.update(self.game, fetcher=self.fetcher(REV_A))
        self.assertNotIn("up_to_date", again)

    def test_require_signed_refuses_an_unsigned_commit_and_changes_nothing(self):
        self.bootstrap()
        (self.source / ".claude/skills/game-arts/SKILL.md").write_text("version two\n")
        with mock.patch.object(sync.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "git", stderr="no signature")):
            with self.assertRaisesRegex(ValueError, "no valid signature"):
                sync.update(self.game, fetcher=self.fetcher(REV_A), require_signed=True)
        self.assertEqual((self.game / ".claude/skills/game-arts/SKILL.md").read_text(), "version one\n")

    def test_a_verified_signature_is_recorded_and_unrequested_verification_is_reported_as_such(self):
        self.bootstrap()
        with mock.patch.object(sync.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            signed = sync.update(self.game, fetcher=self.fetcher(REV_A), require_signed=True)
        self.assertEqual(signed["source_verification"], "signature_verified")
        self.assertEqual(self.state()["source_verification"], "signature_verified")
        (self.source / ".claude/skills/game-arts/SKILL.md").write_text("version two\n")
        plain = sync.update(self.game, fetcher=self.fetcher(REV_B))
        self.assertEqual(plain["source_verification"], "not_requested")

    def test_a_concurrent_update_is_refused_not_interleaved(self):
        self.bootstrap()
        started, release = threading.Event(), threading.Event()

        def slow(scratch):
            started.set()
            release.wait(10)
            return self.fetcher()(scratch)

        worker = threading.Thread(target=lambda: sync.update(self.game, fetcher=slow))
        worker.start()
        self.assertTrue(started.wait(10))
        try:
            with self.assertRaisesRegex(ValueError, "Another Game Arts sync"):
                sync.update(self.game, fetcher=self.fetcher())
        finally:
            release.set()
            worker.join()


class LegacyCompatibilityTests(unittest.TestCase):
    """Enrolled games run the OLD updater first. The tree it fetches must stay installable by it, and the hardened updater
    must take over its state without a false conflict."""

    def framework_copy(self, destination):
        for name in (".agents", ".claude", "scripts", "schemas", "docs"):
            shutil.copytree(ROOT / name, destination / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for master in ROOT.glob("GAME_ARTS_MASTER_STANDARD*.md"):
            shutil.copyfile(master, destination / master.name)

    def test_the_current_tree_installs_with_the_published_updater_and_hands_over_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            framework, game = Path(tmp) / "framework", Path(tmp) / "game"
            framework.mkdir()
            game.mkdir()
            self.framework_copy(framework)
            self.assertTrue((framework / legacy.MASTER).is_file(),
                            "the published updater requires a file under the old master name (the small bridge); keep it "
                            "until every enrolled game runs the hardened updater")
            self.assertTrue((framework / "GAME_ARTS_MASTER_STANDARD.md").is_file())
            first = legacy.sync(framework, game)
            self.assertEqual(first["conflicts"], [])
            self.assertTrue((game / legacy.MASTER).is_file())  # the old updater installed the bridge as the master
            second = sync.sync(framework, game)
            self.assertEqual(second["conflicts"], [])
            self.assertEqual(second["new"], ["GAME_ARTS_MASTER_STANDARD.md"])  # the real standard arrives
            self.assertEqual(second["removed"], [legacy.MASTER])  # and the bridge a game received is cleaned up
            self.assertEqual(second["updated"], [])
            self.assertFalse((game / legacy.MASTER).exists())
            (framework / "docs" / "COMMANDS.md").unlink()
            third = sync.sync(framework, game)
            self.assertEqual(third["removed"], ["docs/COMMANDS.md"])


if __name__ == "__main__":
    unittest.main()
