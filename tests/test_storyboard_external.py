"""Scenes decided by another tool: Game Arts adopts them with the developer's words, makes pictures for them, and never writes, approves or rejects them
itself."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)

import gamearts_storyboard as board  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_storyboard.py"
OWNER = "storyboard-framework"
WORDS = "the developer: these are the scenes, go ahead"
DOCUMENT = {"title": "Cozy Soccer", "scenes": [
    {"id": "intro", "title": "Intro", "summary": "The coach arrives at the training ground at dawn."},
    {"id": "match", "title": "First match", "summary": "The team plays its first match in the rain."}], "order": ["intro", "match"]}


class GameCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def adopt(self, document=None, owner=OWNER, words=WORDS):
        return board.adopt_external(self.root, owner, DOCUMENT if document is None else document, words)

    def stored(self):
        return board.load(self.root)


class AdoptTests(GameCase):
    def test_the_owners_scenes_are_recorded_approved_with_their_owner_the_words_and_a_hash_of_the_text(self):
        result = self.adopt()
        self.assertEqual(result, {"adopted": ["intro", "match"], "owner": OWNER})
        data = self.stored()
        self.assertEqual(data["external_owner"]["id"], OWNER)
        self.assertEqual(data["sequence"]["order"], ["intro", "match"])
        self.assertEqual((data["sequence"]["status"], data["sequence"]["approval"]["owner"]), ("approved", OWNER))
        for scene in data["scenes"]:
            self.assertEqual(scene["status"], "approved")
            self.assertEqual((scene["approval"]["owner"], scene["approval"]["reference"]), (OWNER, WORDS))
            self.assertEqual(scene["approval"]["content_sha256"], board.scene_hash(scene))

    def test_the_mockup_gate_accepts_an_adopted_scene_and_refuses_one_the_owner_did_not_list(self):
        self.adopt()
        board.scene_gate(self.root, "scene", "intro")
        with self.assertRaisesRegex(ValueError, "Unknown storyboard scene"):
            board.scene_gate(self.root, "scene", "finale")

    def test_the_audit_is_consistent(self):
        self.adopt()
        self.assertEqual(board.audit(self.root), [])

    def test_the_developers_words_and_a_clear_owner_are_required(self):
        for words in (None, "", "  "):
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, "own words"):
                self.adopt(words=words)
        for owner in ("", "has space", None):
            with self.subTest(owner=owner), self.assertRaisesRegex(ValueError, "short id"):
                self.adopt(owner=owner)
        self.assertFalse(board.exists(self.root))

    def test_an_order_that_does_not_name_every_scene_once_is_refused(self):
        with self.assertRaisesRegex(ValueError, "every scene exactly once"):
            self.adopt(dict(DOCUMENT, order=["intro"]))
        with self.assertRaisesRegex(ValueError, "duplicate scene IDs"):
            self.adopt(dict(DOCUMENT, scenes=DOCUMENT["scenes"] + [DOCUMENT["scenes"][0]]))


class AuthorityTests(GameCase):
    def test_game_arts_does_not_write_approve_or_reject_scenes_another_tool_owns(self):
        self.adopt()
        before = json.dumps(self.stored(), sort_keys=True)
        with self.assertRaisesRegex(ValueError, f"belong to {OWNER}"):
            board.write(self.root, {"title": "x", "origin": "agent_authored", "scenes": [{"id": "a", "title": "A", "summary": "s"}]})
        with self.assertRaisesRegex(ValueError, f"belong to {OWNER}"):
            board.approve(self.root, ["intro"], "someone")
        with self.assertRaisesRegex(ValueError, f"belong to {OWNER}"):
            board.reject(self.root, ["intro"], "no")
        self.assertEqual(json.dumps(self.stored(), sort_keys=True), before)

    def test_the_owner_changes_a_scene_by_adopting_again_and_the_hash_follows(self):
        self.adopt()
        first = self.stored()["scenes"][0]["approval"]["content_sha256"]
        changed = json.loads(json.dumps(DOCUMENT))
        changed["scenes"][0]["summary"] = "The coach arrives at dusk instead."
        self.adopt(changed, words="the developer: yes, dusk")
        scene = self.stored()["scenes"][0]
        self.assertNotEqual(scene["approval"]["content_sha256"], first)
        self.assertEqual(scene["approval"]["reference"], "the developer: yes, dusk")
        self.assertEqual(board.audit(self.root), [])

    def test_another_owner_and_a_storyboard_game_arts_made_are_not_replaced(self):
        self.adopt()
        with self.assertRaisesRegex(ValueError, f"belong to {OWNER}, not other-tool"):
            self.adopt(owner="other-tool")
        own = self.root / "own"
        own.mkdir()
        board.write(own, {"title": "Mine", "origin": "agent_authored", "scenes": [{"id": "a", "title": "A", "summary": "s"}]})
        with self.assertRaisesRegex(ValueError, "already has a storyboard Game Arts made"):
            board.adopt_external(own, OWNER, DOCUMENT, WORDS)

    def test_source_files_can_still_be_attached_to_an_adopted_storyboard(self):
        self.adopt()
        note = self.root / "notes.txt"
        note.write_text("reference", encoding="utf-8")
        self.assertEqual(board.import_sources(self.root, [note])["imported"], ["notes.txt"])


class AuditTests(GameCase):
    def test_a_scene_text_changed_by_hand_after_adoption_is_found(self):
        self.adopt()
        data = self.stored()
        data["scenes"][0]["summary"] = "Edited behind the owner's back."
        path = board.document(self.root)
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("changed since approval" in issue for issue in board.audit(self.root)))
        with self.assertRaisesRegex(ValueError, "not approved in its current form"):
            board.scene_gate(self.root, "scene", "intro")

    def test_a_scene_not_approved_by_the_owner_is_found(self):
        self.adopt()
        data = self.stored()
        del data["scenes"][1]["approval"]["owner"]
        board.document(self.root).write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any(f"not approved by {OWNER}" in issue for issue in board.audit(self.root)))


class CommandTests(GameCase):
    def test_the_command_adopts_and_the_game_arts_commands_then_refuse(self):
        document = self.root / "scenes.json"
        document.write_text(json.dumps(DOCUMENT), encoding="utf-8")
        run = lambda *args: subprocess.run([sys.executable, str(SCRIPT), *args, "--game-root", str(self.root)], capture_output=True, text=True)  # noqa: E731
        done = run("adopt-external", "--owner", OWNER, "--from", str(document), "--user-approval-ref", WORDS)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(run("audit").stdout)["status"], "consistent")
        refused = run("approve", "--scenes", "intro", "--user-approval-ref", "me")
        self.assertEqual(refused.returncode, 1)
        self.assertIn(f"belong to {OWNER}", refused.stderr)


if __name__ == "__main__":
    unittest.main()
