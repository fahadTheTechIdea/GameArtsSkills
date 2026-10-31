"""Tests for keeping every generated sprite picture with its prompt, its measurements and the reason it was kept or rejected (scripts/gamearts_candidates.py)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from gamearts_testkit import write_settings

import gamearts_candidates as gc
import gamearts_common as common

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_candidates.py"
KEY = (255, 0, 255, 255)
BODY = (40, 60, 160, 255)
SKIN = (200, 150, 100, 255)


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.root = self.dir / "game"
        self.root.mkdir()
        write_settings(self.root)
        (self.root / "art").mkdir()
        Image.new("RGBA", (64, 32), (10, 20, 30, 255)).save(self.root / "art" / "turnaround.png")
        self.prompt = self.dir / "prompt.txt"
        self.prompt.write_text("LAYOUT: EXACTLY 4 complete figures", encoding="utf-8")

    def strip(self, xs, name="tool.png", heights=None):
        image = Image.new("RGBA", (400, 100), KEY)
        draw = ImageDraw.Draw(image)
        for number, x in enumerate(xs):
            height = (heights or {}).get(number, 60)
            draw.rectangle((x, 90 - height + 1, x + 40, 90), fill=BODY)
            draw.rectangle((x + 10, 90 - height - 19, x + 30, 90 - height), fill=SKIN)
        path = self.dir / name
        image.save(path)
        return path

    def record(self, picture=None, **more):
        args = dict(image=picture or self.strip([20, 120, 220, 320]), group="oilco-tanker-e-clap", frames=4, facing="E", action="clap", prompt_file=self.prompt,
                    generated_with="Codex built-in image tool", refs=["turnaround=art/turnaround.png"])
        args.update(more)
        return gc.record(self.root, args.pop("image"), args.pop("group"), args.pop("frames"), **args)

    FINDINGS = ["facing=pass:only the back of the head and the heels show", "elevation=pass:the roof shows at the same angle as the turnaround", "identity=pass:same truck, same green and the same markings", "motion=pass:the arms alternate"]

    def review(self, candidate_id, findings=None, **more):
        more.setdefault("compared_with", ["turnaround=art/turnaround.png"])
        return gc.review(self.root, candidate_id, more.pop("reviewer", "agent"), more.pop("compared_with"), findings or self.FINDINGS, **more)

    def folder(self, candidate_id):
        return self.root / ".gamearts" / "outputs" / "candidates" / candidate_id


class RecordTests(Case):
    def test_a_good_picture_is_kept_unchanged_with_everything_that_made_it(self):
        picture = self.strip([20, 120, 220, 320])
        body = self.record(picture, crown=30)
        self.assertEqual((body["candidate_id"], body["status"], body["revision"]), ("oilco-tanker-e-clap-v001", "generated", 1))
        kept = self.root / body["file"]
        self.assertEqual(common.sha256_file(kept), common.sha256_file(picture))
        self.assertEqual((body["sha256"], body["original_sha256"], body["original_name"]), (common.sha256_file(kept), common.sha256_file(picture), "tool.png"))
        self.assertEqual((body["width"], body["height"]), (400, 100))
        self.assertGreater(body["exact_key_fraction"], 0.5)
        self.assertEqual(body["prompt"], "LAYOUT: EXACTLY 4 complete figures")
        self.assertEqual(body["prompt_sha256"], common.sha256_bytes(b"LAYOUT: EXACTLY 4 complete figures"))
        self.assertEqual(body["generated_with"], "Codex built-in image tool")
        self.assertEqual(body["references"], [{"role": "turnaround", "path": "art/turnaround.png", "sha256": common.sha256_file(self.root / "art" / "turnaround.png")}])
        self.assertEqual(body["check"]["status"], "passed")
        self.assertEqual(len(body["check"]["measured"]), 4)
        self.assertTrue(all("crown" in item for item in body["check"]["measured"]))
        self.assertEqual(body["check"]["parameters"]["crown"], 30)
        self.assertNotIn("rejection", body)
        common.validate_schema(common.read_json(self.folder(body["candidate_id"]) / "candidate.json"), "gamearts-candidate")

    def test_a_picture_the_check_refuses_is_kept_as_rejected_with_the_measurement_as_the_reason(self):
        body = self.record(self.strip([0, 120, 220, 320]))
        self.assertEqual(body["status"], "rejected")
        self.assertEqual(body["check"]["status"], "refused")
        self.assertIn("touches the picture's edge", body["check"]["refusal"])
        self.assertEqual(body["rejection"]["reason"], body["check"]["refusal"])
        self.assertEqual(body["rejection"]["by"], "automatic check")
        self.assertTrue((self.root / body["file"]).is_file())  # nothing is deleted

    def test_the_neutral_ends_and_the_head_width_are_checked_on_every_picture(self):
        shorter = self.strip([20, 120, 220, 320], heights={3: 40}, name="short.png")
        self.assertIn("same neutral pose", self.record(shorter, neutral_ends=True)["check"]["refusal"])

    def test_each_new_picture_of_a_group_gets_the_next_revision_and_never_overwrites(self):
        first, second = self.record(), self.record(self.strip([20, 120, 220, 320], name="again.png"))
        self.assertEqual((first["revision"], second["revision"]), (1, 2))
        self.assertNotEqual(first["file"], second["file"])
        self.assertEqual(self.record(group="other-group")["candidate_id"], "other-group-v001")

    def test_the_record_refuses_what_would_make_it_unreadable_later(self):
        for more, text in (({"generated_with": " "}, "say what produced the picture"), ({"group": "Bad Name"}, "the group is a lowercase name"), ({"facing": "east"}, "the facing is a direction"),
                           ({"refs": ["turnaround"]}, "must be ROLE=PATH"), ({"refs": ["turnaround=art/none.png"]}, "does not exist inside the game"),
                           ({"refs": ["turnaround=../outside.png"]}, "must stay inside its folder"), ({"image": self.dir / "missing.png"}, "does not exist"),
                           ({"prompt_file": self.dir / "missing.txt"}, "--prompt-file must name the file")):
            with self.subTest(more=more), self.assertRaisesRegex(ValueError, text):
                self.record(**more)
        empty = self.dir / "empty.txt"
        empty.write_text("  ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "prompt file is empty"):
            self.record(prompt_file=empty)
        jpeg = self.dir / "photo.png"
        Image.new("RGB", (40, 40)).save(jpeg, "JPEG")
        with self.assertRaisesRegex(ValueError, "must be a PNG"):
            self.record(jpeg)
        self.assertFalse((self.root / ".gamearts" / "outputs" / "candidates").exists() and any((self.root / ".gamearts" / "outputs" / "candidates").iterdir()))

    def test_a_game_that_is_not_a_game_folder_is_refused(self):
        with self.assertRaisesRegex(ValueError, "is not a set-up game"):
            gc.record(self.dir / "nowhere", self.strip([20]), "g", 1, prompt_file=self.prompt, generated_with="x")
        self.assertFalse((self.dir / "nowhere").exists())
        with self.assertRaisesRegex(ValueError, "is not a set-up game"):
            gc.listing(self.dir / "nowhere")


class JudgementTests(Case):
    def test_a_person_rejects_with_a_reason_and_the_picture_stays(self):
        body = self.record()
        rejected = gc.reject(self.root, body["candidate_id"], "the camera is lower than the approved pictures")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["rejection"]["by"], "judgement")
        self.assertEqual(rejected["rejection"]["reason"], "the camera is lower than the approved pictures")
        self.assertTrue((self.root / body["file"]).is_file())
        with self.assertRaisesRegex(ValueError, "is rejected, so it cannot be rejected again"):
            gc.reject(self.root, body["candidate_id"], "again")
        with self.assertRaisesRegex(ValueError, "say why the picture is rejected"):
            gc.reject(self.root, self.record()["candidate_id"], "  ")

    def test_selecting_supersedes_the_earlier_selection_and_keeps_it(self):
        first, second = self.record(), self.record()
        self.review(first["candidate_id"])
        self.review(second["candidate_id"])
        gc.select(self.root, first["candidate_id"], "closest to the turnaround")
        chosen = gc.select(self.root, second["candidate_id"])
        self.assertEqual(chosen["status"], "selected")
        earlier = common.read_json(self.folder(first["candidate_id"]) / "candidate.json")
        self.assertEqual(earlier["status"], "superseded")
        self.assertEqual(earlier["selection"]["superseded_by"], second["candidate_id"])
        self.assertEqual(earlier["selection"]["note"], "closest to the turnaround")
        self.assertEqual([row["status"] for row in gc.listing(self.root, "oilco-tanker-e-clap")], ["superseded", "selected"])

    def test_a_picture_that_failed_its_check_or_was_rejected_cannot_be_selected(self):
        refused = self.record(self.strip([0, 120, 220, 320]))
        with self.assertRaisesRegex(ValueError, "is rejected: only a generated picture can be selected"):
            gc.select(self.root, refused["candidate_id"])
        body = self.record()
        gc.reject(self.root, body["candidate_id"], "wrong facing")
        with self.assertRaisesRegex(ValueError, "only a generated picture can be selected"):
            gc.select(self.root, body["candidate_id"])

    def test_an_id_that_is_not_a_candidate_is_refused(self):
        for candidate_id, text in (("../x-v001", "is not a candidate id"), ("nothing-v001", "there is no candidate"), ("bad", "is not a candidate id")):
            with self.subTest(candidate_id=candidate_id), self.assertRaisesRegex(ValueError, text):
                gc.select(self.root, candidate_id)

    def test_the_listing_gives_every_status_and_reason(self):
        self.record()
        self.record(self.strip([0, 120, 220, 320], name="edge.png"))
        rows = gc.listing(self.root)
        self.assertEqual([(row["candidate_id"], row["status"], row["check"]) for row in rows], [("oilco-tanker-e-clap-v001", "generated", "passed"), ("oilco-tanker-e-clap-v002", "rejected", "refused")])
        self.assertIn("touches the picture's edge", rows[1]["reason"])
        self.assertEqual(gc.listing(self.root, "no-such-group"), [])


class ReviewTests(Case):
    """A picture is selected only after someone compared it with the approved pictures and said, in words, why the facing, the elevation and the figure are right."""

    def test_a_passing_review_records_what_was_compared_and_what_was_found(self):
        body = self.record()
        reviewed = self.review(body["candidate_id"])
        entry = reviewed["reviews"][-1]
        self.assertEqual((reviewed["status"], entry["overall"], entry["reviewer"], entry["candidate_sha256"]), ("generated", "pass", "agent", body["sha256"]))
        self.assertEqual(entry["compared_with"], [{"role": "turnaround", "path": "art/turnaround.png", "sha256": common.sha256_file(self.root / "art" / "turnaround.png")}])
        self.assertEqual(entry["findings"]["facing"], {"verdict": "pass", "reason": "only the back of the head and the heels show"})
        self.assertEqual(gc.select(self.root, body["candidate_id"])["status"], "selected")

    def test_a_failing_finding_rejects_the_picture_with_the_reasons(self):
        body = self.record()
        findings = ["facing=fail:the front of the chest shows", "elevation=fail:the roof shows from almost straight above", "identity=pass:same truck", "motion=not_applicable:a single pose"]
        rejected = self.review(body["candidate_id"], findings)
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["rejection"]["by"], "review")
        self.assertEqual(rejected["rejection"]["reason"], "facing: the front of the chest shows; elevation: the roof shows from almost straight above")
        self.assertEqual(rejected["reviews"][-1]["overall"], "fail")
        with self.assertRaisesRegex(ValueError, "is rejected: only a generated picture can be selected"):
            gc.select(self.root, body["candidate_id"])

    def test_a_picture_is_not_selected_without_a_passing_review_of_this_exact_file(self):
        body = self.record()
        with self.assertRaisesRegex(ValueError, "has no passing review"):
            gc.select(self.root, body["candidate_id"])
        self.review(body["candidate_id"])
        (self.root / body["file"]).write_bytes(self.strip([20, 120, 220, 320], name="changed.png", heights={0: 50}).read_bytes())
        with self.assertRaisesRegex(ValueError, "changed after its review"):
            gc.select(self.root, body["candidate_id"])
        with self.assertRaisesRegex(ValueError, "no longer matches the hash recorded"):
            self.review(body["candidate_id"])

    def test_a_review_judges_all_four_aspects_each_with_a_reason(self):
        body = self.record()["candidate_id"]
        for findings, text in ((self.FINDINGS[:3], "missing: motion"), (self.FINDINGS + ["facing=pass:again"], "must be ASPECT=VERDICT:reason"), (["facing=pass: "] + self.FINDINGS[1:], "must be ASPECT=VERDICT:reason"),
                               (["facing=maybe:unsure"] + self.FINDINGS[1:], "must be ASPECT=VERDICT:reason"), (["colour=pass:fine"] + self.FINDINGS[1:], "must be ASPECT=VERDICT:reason"),
                               (["facing=not_applicable:skipped"] + self.FINDINGS[1:], "facing cannot be not_applicable")):
            with self.subTest(findings=findings), self.assertRaisesRegex(ValueError, text):
                self.review(body, findings)
        self.assertNotIn("reviews", common.read_json(self.folder(body) / "candidate.json"))

    def test_a_review_names_real_pictures_it_was_compared_with(self):
        body = self.record()["candidate_id"]
        for compared, text in (([], "not a comparison"), (["turnaround"], "must be ROLE=PATH"), (["turnaround=art/none.png"], "cannot have been compared"), (["turnaround=../x.png"], "must stay inside its folder")):
            with self.subTest(compared=compared), self.assertRaisesRegex(ValueError, text):
                self.review(body, compared_with=compared)
        with self.assertRaisesRegex(ValueError, "the reviewer is agent or owner"):
            self.review(body, reviewer="robot")

    def test_measured_flags_must_be_explained_or_a_finding_must_fail(self):
        reference = self.root / "art" / "neutral.png"
        Image.new("RGBA", (60, 90), (200, 30, 30, 255)).save(reference)  # a red figure against the blue strip
        body = self.record(reference="art/neutral.png")
        self.assertTrue(any("mean colour" in flag for flag in body["check"]["match_flags"]), body["check"]["match_flags"])
        with self.assertRaisesRegex(ValueError, "explain them in --flags-explained"):
            self.review(body["candidate_id"])
        explained = self.review(body["candidate_id"], flags_explained="the reference is a red variant; the strip is the approved blue one")
        self.assertEqual(explained["reviews"][-1]["flags_explained"], "the reference is a red variant; the strip is the approved blue one")
        failing = ["facing=pass:ok", "elevation=pass:ok", "identity=fail:wrong colour", "motion=pass:ok"]
        self.assertEqual(self.review(self.record(reference="art/neutral.png")["candidate_id"], failing)["status"], "rejected")

    def test_only_a_generated_picture_is_reviewed_and_an_owner_may_review_too(self):
        body = self.record()["candidate_id"]
        self.assertEqual(self.review(body, reviewer="owner")["reviews"][-1]["reviewer"], "owner")
        gc.reject(self.root, body, "wrong facing")
        with self.assertRaisesRegex(ValueError, "is rejected: only a generated picture is reviewed"):
            self.review(body)


class CommandLineTests(Case):
    def args(self, picture):
        return ["record", "--game-root", self.root, "--image", picture, "--group", "g-e-clap", "--frames", 4, "--facing", "E", "--action", "clap", "--prompt-file", self.prompt,
                "--generated-with", "Codex", "--ref", "turnaround=art/turnaround.png", "--crown", 30]

    def test_a_passing_picture_exits_zero_and_says_what_a_person_still_judges(self):
        result = run(*self.args(self.strip([20, 120, 220, 320])))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["candidate_id"], report["status"]), ("g-e-clap-v001", "generated"))
        self.assertIn("run `review`", report["next"])
        self.assertEqual(report["match_flags"], [])
        self.assertIn("whether the picture shows the right facing, the same camera elevation and the same figure: that is the review, not the measurements", report["not_assessed"])

    def test_a_refused_picture_exits_three_and_is_still_recorded(self):
        result = run(*self.args(self.strip([0, 120, 220, 320])))
        self.assertEqual(result.returncode, 3, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "rejected")
        self.assertIn("rejected by the check", report["next"])
        self.assertTrue(self.folder("g-e-clap-v001").is_dir())

    def test_reject_select_and_list_work_from_the_command_line(self):
        self.assertEqual(run(*self.args(self.strip([20, 120, 220, 320]))).returncode, 0)
        no_review = run("select", "--game-root", self.root, "--candidate-id", "g-e-clap-v001")
        self.assertEqual(no_review.returncode, 1)
        self.assertIn("has no passing review", no_review.stderr)
        reviewed = run("review", "--game-root", self.root, "--candidate-id", "g-e-clap-v001", "--reviewer", "agent", "--compared-with", "turnaround=art/turnaround.png",
                       *[item for finding in self.FINDINGS for item in ("--finding", finding)])
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        self.assertEqual(json.loads(reviewed.stdout)["overall"], "pass")
        self.assertEqual(json.loads(run("select", "--game-root", self.root, "--candidate-id", "g-e-clap-v001", "--note", "ok").stdout)["status"], "selected")
        self.assertEqual(run(*self.args(self.strip([20, 120, 220, 320], name="second.png"))).returncode, 0)
        failing = run("review", "--game-root", self.root, "--candidate-id", "g-e-clap-v002", "--reviewer", "agent", "--compared-with", "turnaround=art/turnaround.png",
                      "--finding", "facing=fail:the front of the chest shows", "--finding", "elevation=pass:ok", "--finding", "identity=pass:ok", "--finding", "motion=pass:ok")
        self.assertEqual(failing.returncode, 3, failing.stderr)
        self.assertEqual((json.loads(failing.stdout)["status"], json.loads(failing.stdout)["overall"]), ("rejected", "fail"))
        self.assertIn("rejected by the review", json.loads(failing.stdout)["next"])
        self.assertEqual(run(*self.args(self.strip([20, 120, 220, 320], name="third.png"))).returncode, 0)
        self.assertEqual(json.loads(run("list", "--game-root", self.root, "--group", "g-e-clap").stdout)[0]["status"], "selected")
        rejected = run("reject", "--game-root", self.root, "--candidate-id", "g-e-clap-v001", "--reason", "wrong facing")
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)["status"], "rejected")
        again = run("reject", "--game-root", self.root, "--candidate-id", "g-e-clap-v001", "--reason", "again")
        self.assertEqual(again.returncode, 1)
        self.assertIn("is rejected, so it cannot be rejected again", again.stderr)

if __name__ == "__main__":
    unittest.main()
