"""The living campaign storyboard: supplied or agent-authored, approved as an ordered set, edited in place, never versioned."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import make_mockup, write_settings

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_storyboard as board  # noqa: E402


def draft(**changes):
    body = {"title": "A coach's first season", "origin": "agent_authored", "brief": "a quiet town, a small football club",
            "scenes": [{"id": "arrival", "title": "Arrival", "summary": "The coach steps off the bus.", "location": "bus stop"},
                       {"id": "first-training", "title": "First training", "summary": "A muddy pitch and eleven strangers."},
                       {"id": "first-match", "title": "First match", "summary": "Rain, a late goal, a handshake."}]}
    body.update(changes)
    return body


class StoryboardCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        write_settings(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def scene(self, scene_id):
        return next(s for s in board.load(self.root)["scenes"] if s["id"] == scene_id)

    def revise(self, scene_id, **fields):
        data = board.load(self.root)
        scenes = [dict(s) for s in data["scenes"]]
        next(s for s in scenes if s["id"] == scene_id).update(fields)
        return board.write(self.root, {"title": data["title"], "origin": data["origin"], "brief": data["brief"], "scenes": scenes},
                           "user", f"edited {scene_id}")


class WriteTests(StoryboardCase):
    def test_an_agent_authored_storyboard_starts_proposed_with_no_approval_and_no_version(self):
        result = board.write(self.root, draft(), "agent", "storyboard drafted from the user's prompt")
        self.assertEqual(result["scenes"], 3)
        data = board.load(self.root)
        self.assertEqual({s["status"] for s in data["scenes"]}, {"proposed"})
        self.assertEqual(data["sequence"], {"order": [], "status": "pending"})
        self.assertFalse(any("version" in key.lower() for key in data))
        self.assertEqual(board.audit(self.root), [])
        self.assertEqual(sorted(p.name for p in board.folder(self.root).iterdir()), ["storyboard.json"])  # one file, no copies

    def test_a_draft_cannot_approve_itself(self):
        sneaky = draft()
        sneaky["scenes"][0]["status"] = "approved"
        sneaky["scenes"][0]["approval"] = {"reference": "x", "at_utc": "now", "content_sha256": "0" * 64}
        sneaky["sequence"] = {"order": ["arrival"], "status": "approved"}
        board.write(self.root, sneaky, "agent", "tries to approve")
        data = board.load(self.root)
        self.assertEqual(self.scene("arrival")["status"], "proposed")
        self.assertNotIn("approval", self.scene("arrival"))
        self.assertEqual(data["sequence"]["status"], "pending")

    def test_the_change_log_grows_and_every_save_is_backed_up(self):
        board.write(self.root, draft(), "agent", "first draft")
        self.revise("arrival", summary="The coach steps off the bus in the rain.")
        data = board.load(self.root)
        self.assertEqual([c["summary"] for c in data["changes"]], ["first draft", "edited arrival"])
        self.assertEqual([c["by"] for c in data["changes"]], ["agent", "user"])
        backups = list((self.root / ".gamearts/system/backups").glob("storyboard_*.json"))
        self.assertEqual(len(backups), 1)

    def test_duplicate_scene_ids_and_invalid_shapes_are_refused(self):
        bad = draft()
        bad["scenes"].append(dict(bad["scenes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate scene IDs"):
            board.write(self.root, bad, "agent", "dup")
        with self.assertRaisesRegex(ValueError, "contract violation"):
            board.write(self.root, {"title": "No origin", "scenes": []}, "agent", "bad")
        with self.assertRaises(ValueError):
            board.write(self.root, "not an object", "agent", "bad")
        self.assertFalse(board.exists(self.root))

    def test_a_missing_storyboard_is_a_clear_error(self):
        with self.assertRaisesRegex(ValueError, "no storyboard yet"):
            board.load(self.root)
        self.assertEqual(board.audit(self.root), ["This game has no storyboard yet"])


class ImportTests(StoryboardCase):
    def test_a_supplied_storyboard_is_imported_as_a_hashed_managed_copy(self):
        source = self.root / "my story.md"
        source.write_text("Scene 1: the arrival\n")
        result = board.import_sources(self.root, [source], title="My story", origin="user_provided")
        self.assertEqual(result["imported"], ["my_story.md"])
        data = board.load(self.root)
        record = data["source_files"][0]
        self.assertEqual(record["sha256"], common.sha256_file(source))
        self.assertEqual((board.folder(self.root) / record["path"]).read_bytes(), source.read_bytes())
        self.assertEqual(data["origin"], "user_provided")
        self.assertTrue(source.exists())  # the original is never moved or modified
        self.assertEqual(board.audit(self.root), [])

    def test_importing_the_same_file_twice_adds_nothing_and_a_name_clash_is_refused(self):
        source = self.root / "story.md"
        source.write_text("one\n")
        board.import_sources(self.root, [source], title="S")
        self.assertEqual(board.import_sources(self.root, [source])["skipped_duplicates"], 1)
        other = self.root / "elsewhere"
        other.mkdir()
        (other / "story.md").write_text("two\n")
        with self.assertRaisesRegex(ValueError, "different file named story.md"):
            board.import_sources(self.root, [other / "story.md"])

    def test_a_title_is_required_for_the_first_import_and_only_regular_files_are_taken(self):
        source = self.root / "story.md"
        source.write_text("one\n")
        with self.assertRaisesRegex(ValueError, "--title is required"):
            board.import_sources(self.root, [source])
        with self.assertRaisesRegex(ValueError, "regular file"):
            board.import_sources(self.root, [self.root], title="S")

    def test_importing_after_the_agent_drafted_marks_the_storyboard_hybrid(self):
        board.write(self.root, draft(), "agent", "drafted")
        source = self.root / "notes.txt"
        source.write_text("the user's own notes\n")
        board.import_sources(self.root, [source])
        self.assertEqual(board.load(self.root)["origin"], "hybrid")

    def test_a_changed_source_file_is_reported_by_the_audit(self):
        source = self.root / "story.md"
        source.write_text("one\n")
        board.import_sources(self.root, [source], title="S")
        (board.folder(self.root) / "sources/story.md").write_text("tampered\n")
        self.assertTrue(any("source file missing or changed" in i for i in board.audit(self.root)))


class ApprovalTests(StoryboardCase):
    def setUp(self):
        super().setUp()
        board.write(self.root, draft(), "agent", "drafted")

    def test_the_user_approves_an_ordered_subset_and_only_those_scenes_are_in_the_sequence(self):
        board.approve(self.root, ["arrival", "first-match"], "user said: yes to arrival and first match")
        data = board.load(self.root)
        self.assertEqual(data["sequence"]["order"], ["arrival", "first-match"])
        self.assertEqual(data["sequence"]["status"], "approved")
        self.assertEqual(self.scene("first-training")["status"], "proposed")
        self.assertEqual(self.scene("arrival")["approval"]["content_sha256"], board.scene_hash(self.scene("arrival")))
        self.assertEqual(board.audit(self.root), [])

    def test_approval_needs_a_real_reference_known_scenes_and_no_duplicates(self):
        with self.assertRaisesRegex(ValueError, "approval message reference"):
            board.approve(self.root, ["arrival"], " ")
        with self.assertRaisesRegex(ValueError, "Unknown scene"):
            board.approve(self.root, ["nope"], "ok")
        with self.assertRaisesRegex(ValueError, "once, in playing order"):
            board.approve(self.root, ["arrival", "arrival"], "ok")
        self.assertEqual(board.load(self.root)["sequence"]["status"], "pending")

    def test_editing_an_approved_scene_returns_it_to_review_and_suspends_the_sequence(self):
        board.approve(self.root, ["arrival", "first-match"], "ok")
        result = self.revise("arrival", summary="Night. The bus is late.")
        self.assertEqual(result["needs_review"], ["arrival"])
        self.assertEqual(result["sequence_status"], "pending")
        self.assertEqual(self.scene("arrival")["status"], "needs_review")
        self.assertNotIn("approval", self.scene("arrival"))
        self.assertEqual(self.scene("first-match")["status"], "approved")  # untouched scenes keep their approval
        self.assertTrue(any("needs renewed approval" in c["summary"] for c in board.load(self.root)["changes"]))
        board.approve(self.root, ["arrival", "first-match"], "ok again")
        self.assertEqual(board.load(self.root)["sequence"]["status"], "approved")

    def test_editing_private_notes_does_not_cost_an_approval(self):
        board.approve(self.root, ["arrival"], "ok")
        self.revise("arrival", notes="remember to ask about the bus colour")
        self.assertEqual(self.scene("arrival")["status"], "approved")
        self.assertEqual(board.load(self.root)["sequence"]["status"], "approved")

    def test_rejecting_removes_the_scene_from_the_sequence_and_blocks_its_approval(self):
        board.approve(self.root, ["arrival", "first-training"], "ok")
        board.reject(self.root, ["first-training"], "the training scene is too slow")
        data = board.load(self.root)
        self.assertEqual(data["sequence"], {"order": ["arrival"], "status": "pending"})
        self.assertEqual(self.scene("first-training")["status"], "rejected")
        with self.assertRaisesRegex(ValueError, "was rejected"):
            board.approve(self.root, ["arrival", "first-training"], "ok")
        with self.assertRaisesRegex(ValueError, "reason is required"):
            board.reject(self.root, ["arrival"], "")
        self.revise("first-training", summary="A short, funny training session.")
        self.assertEqual(self.scene("first-training")["status"], "proposed")  # a revised rejected scene is a fresh proposal

    def test_tampering_with_an_approved_scene_on_disk_is_caught_by_the_audit(self):
        board.approve(self.root, ["arrival"], "ok")
        path = board.document(self.root)
        data = common.read_json(path)
        data["scenes"][0]["summary"] = "Something the user never approved."
        common.atomic_write_json(path, data)
        self.assertTrue(any("approved content changed since approval" in i for i in board.audit(self.root)))
        with self.assertRaisesRegex(ValueError, "not approved in its current form"):
            board.scene_gate(self.root, "scene", "arrival")

    def test_scene_panels_are_hash_checked(self):
        panel = board.folder(self.root) / "panels/arrival.png"
        panel.parent.mkdir(parents=True)
        panel.write_bytes(b"rough sketch")
        scenes = draft()["scenes"]
        scenes[0]["panel"] = {"path": "panels/arrival.png", "sha256": common.sha256_file(panel)}
        board.write(self.root, draft(scenes=scenes), "agent", "with a rough panel")
        panel.write_bytes(b"changed")
        self.assertTrue(any("panel image is missing or its hash differs" in i for i in board.audit(self.root)))
        with self.assertRaisesRegex(ValueError, "panel image is missing"):
            board.approve(self.root, ["arrival"], "ok")


class SequencingTests(StoryboardCase):
    def test_next_lists_approved_scenes_in_order_until_their_mockups_exist(self):
        board.write(self.root, draft(), "agent", "drafted")
        self.assertEqual(board.next_scenes(self.root), [])  # nothing approved yet
        board.approve(self.root, ["first-match", "arrival"], "ok")
        self.assertEqual([s["id"] for s in board.next_scenes(self.root)], ["first-match", "arrival"])
        image, metadata = make_mockup(self.root, "match-scene", scope="scene", scene="first-match")
        life.register_mockup(self.root, metadata, image)
        self.assertEqual([s["id"] for s in board.next_scenes(self.root)], ["arrival"])
        self.assertEqual(board.status(self.root)["waiting_for_mockup"], ["arrival"])
        life.revoke(self.root, "mockups", "match-scene", "wrong mood", "v001")
        self.assertEqual([s["id"] for s in board.next_scenes(self.root)], ["first-match", "arrival"])

    def test_the_audit_flags_a_mockup_for_a_scene_that_lost_its_approval(self):
        board.write(self.root, draft(), "agent", "drafted")
        board.approve(self.root, ["arrival"], "ok")
        image, metadata = make_mockup(self.root, "arrival-scene", scope="scene", scene="arrival")
        life.register_mockup(self.root, metadata, image)
        self.revise("arrival", summary="Changed after the mockup was made.")
        self.assertTrue(any("depicts scene arrival which is needs_review" in i for i in board.audit(self.root)))

    def test_links_must_name_real_scenes(self):
        board.write(self.root, draft(links=[{"from": "arrival", "to": "first-training"}]), "agent", "linked")
        self.assertEqual(board.audit(self.root), [])
        data = board.load(self.root)
        data["links"].append({"from": "arrival", "to": "ghost"})
        common.atomic_write_json(board.document(self.root), data)
        self.assertTrue(any("link names unknown scene ghost" in i for i in board.audit(self.root)))


class ReportingTests(StoryboardCase):
    def test_write_reports_the_status_of_every_scene(self):
        result = board.write(self.root, draft(), "agent", "drafted")
        self.assertEqual(result["by_status"], {"proposed": 3})

    def test_status_shows_the_proposed_order_before_anything_is_approved(self):
        board.write(self.root, draft(), "agent", "drafted")
        status = board.status(self.root)
        self.assertEqual(status["proposed_order"], ["arrival", "first-training", "first-match"])
        self.assertEqual(status["approved_order"], [])

    def test_an_empty_next_always_says_why(self):
        board.write(self.root, draft(), "agent", "drafted")
        self.assertIn("no sequence is approved", board.next_report(self.root)["reason"])
        board.approve(self.root, ["arrival"], "ok")
        report = board.next_report(self.root)
        self.assertEqual([s["id"] for s in report["next"]], ["arrival"])
        self.assertIn("waiting", report["reason"])
        image, metadata = make_mockup(self.root, "arrival-scene", scope="scene", scene="arrival")
        life.register_mockup(self.root, metadata, image)
        self.assertEqual(board.next_report(self.root)["next"], [])
        self.assertIn("already has a mockup", board.next_report(self.root)["reason"])


class CommandLineTests(StoryboardCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "gamearts_storyboard.py"), *args], capture_output=True, text=True)

    def test_write_approve_status_audit_and_blocked_exit_codes(self):
        draft_file = self.root / "draft.json"
        draft_file.write_text(json.dumps(draft()))
        game = ["--game-root", str(self.root)]
        written = self.run_cli("write", *game, "--from", str(draft_file), "--summary", "first draft")
        self.assertEqual(written.returncode, 0, written.stderr)
        approved = self.run_cli("approve", *game, "--scenes", "arrival,first-match", "--user-approval-ref", "ok in chat")
        self.assertEqual(approved.returncode, 0, approved.stderr)
        status = json.loads(self.run_cli("status", *game).stdout)
        self.assertEqual((status["sequence"], status["approved_order"]), ("approved", ["arrival", "first-match"]))
        self.assertEqual(self.run_cli("audit", *game).returncode, 0)
        missing = self.run_cli("approve", *game, "--scenes", "ghost", "--user-approval-ref", "ok")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("BLOCKED", missing.stderr)
        board.document(self.root).write_text("{broken")
        self.assertEqual(self.run_cli("status", *game).returncode, 1)


if __name__ == "__main__":
    unittest.main()
