"""The approval form: one page template, shown for anything the owner approves, taking their decision from that same page; the commands that approve
things read that decision instead of typed words. The server is the real one, answered the way the page answers it."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from gamearts_testkit import key_image, make_mockup, shaded_picture, write_settings

import gamearts_approval as approval  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_local_page as local_page  # noqa: E402
import gamearts_setup as wizard  # noqa: E402
import gamearts_storyboard as board  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
OUT = ".gamearts/outputs"


def call(url, data=None, headers=None):
    """(status, body, headers) of one request, an error status included."""
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as failure:
        with failure:
            return failure.code, failure.read(), dict(failure.headers)


def post(url, payload, headers=None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return call(url + "decision", body, {"Content-Type": "application/json", **(headers or {})})


def everything(request, decision="approved", comment=""):
    return {"outcome": "decided", "items": [{"index": at, "decision": decision, "comment": comment} for at in range(len(request["items"]))]}


def owner(chooser):
    """An opener that answers the page the way the page does: read the request, then send the decision `chooser` makes of it."""
    def opener(link):
        def answer():
            request = json.loads(call(link + "request.json")[1])
            post(link, chooser(request))
        threading.Thread(target=answer, daemon=True).start()
        return True
    return opener


def run(script, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True)
    return result


class GameCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "game"
        self.root.mkdir()
        write_settings(self.root)

    def picture(self, name="art/market.png", colour=(120, 60, 40)):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shaded_picture((24, 16), colour).save(path)
        return name

    def spec(self, *items, **more):
        return {"schema_version": "1.0", "title": "Approve the market", "items": list(items), **more}

    def market(self, **more):
        return {"kind": "mockups", "id": "market", "revision": "v001", "title": "Market square", "images": [{"path": self.picture(), "caption": "The mockup"}], **more}

    def ask(self, spec, chooser=everything, timeout=20):
        return approval.ask(self.root, spec, timeout, opener=owner(chooser), echo=lambda text: None)


class PrepareTests(GameCase):
    def test_a_picture_is_found_inside_the_game_and_fingerprinted(self):
        request = approval.prepare(self.root, self.spec(self.market()))
        image = request["items"][0]["images"][0]
        self.assertEqual((image["width"], image["height"]), (24, 16))
        self.assertEqual(image["sha256"], common.sha256_file(self.root / "art/market.png"))
        self.assertEqual(image["bytes"], (self.root / "art/market.png").stat().st_size)

    def test_a_picture_the_form_cannot_honestly_show_is_refused(self):
        self.picture()  # makes the art folder
        (self.root / "art/notes.png").write_text("not a picture", encoding="utf-8")
        (self.root / "art/readme.txt").write_text("words", encoding="utf-8")
        outside = Path(self._tmp.name) / "elsewhere.png"
        shaded_picture((8, 8), (1, 2, 3)).save(outside)
        for path, why in (("art/notes.png", "cannot be read as a picture"), ("art/readme.txt", "not a picture the form can show"), ("art/missing.png", "not a file"),
                          ("../elsewhere.png", "stay inside"), (str(outside), "stay inside")):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, why):
                approval.prepare(self.root, self.spec({"kind": "mockups", "id": "x", "images": [{"path": path}]}))

    def test_a_picture_that_is_cut_short_is_refused_even_though_its_header_reads(self):
        name = self.picture()
        whole = (self.root / name).read_bytes()
        (self.root / "art/cut.png").write_bytes(whole[: len(whole) // 2])
        with self.assertRaisesRegex(ValueError, "cannot be read as a picture"):
            approval.prepare(self.root, self.spec({"kind": "mockups", "id": "x", "images": [{"path": "art/cut.png"}]}))

    def test_the_request_must_keep_to_its_contract(self):
        for bad in (self.spec(), self.spec({"kind": "dessert", "id": "x"}), self.spec({"kind": "other", "id": "has space"}),
                    {"schema_version": "1.0", "title": "", "items": [{"kind": "other", "id": "x"}]}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "contract violation"):
                approval.prepare(self.root, bad)

    def test_the_same_item_twice_in_one_request_is_refused(self):
        with self.assertRaisesRegex(ValueError, "listed twice"):
            approval.prepare(self.root, self.spec({"kind": "other", "id": "x", "revision": "v1"}, {"kind": "other", "id": "x", "revision": "v1"}))

    def test_a_game_folder_is_required(self):
        with self.assertRaises(ValueError):
            approval.prepare(SCRIPTS.parent, self.spec(self.market()))


class ServerCase(GameCase):
    def setUp(self):
        super().setUp()
        self.request = approval.prepare(self.root, self.spec(self.market(), {"kind": "other", "id": "palette", "title": "Palette", "facts": [{"label": "Colours", "value": "<b>12</b>"}]}))
        self.request.update(approval_id=approval.new_id(), created_at_utc="2026-10-30T00:00:00+00:00")
        self.folder = self.root / approval.APPROVALS / self.request["approval_id"]
        common.atomic_write_json(self.folder / "request.json", self.request)
        self.session = approval.Session(self.root, self.request, self.folder)
        self.session.start()
        self.addCleanup(self.session.close)
        self.link = self.session.link

    def decision(self):
        return common.read_json(self.folder / "decision.json")


class PageTests(ServerCase):
    def test_the_one_template_is_served_at_the_secret_address_only_with_a_fresh_nonce_and_a_strict_policy(self):
        status, body, headers = call(self.link)
        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        self.assertNotIn("{{nonce}}", page)
        nonce = headers["Content-Security-Policy"].split("script-src 'nonce-")[1].split("'")[0]
        self.assertIn(f'<script nonce="{nonce}">', page)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertNotEqual(nonce, call(self.link)[2]["Content-Security-Policy"].split("script-src 'nonce-")[1].split("'")[0])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_the_server_listens_on_this_computer_only(self):
        self.assertEqual(self.session.server.server_address[0], "127.0.0.1")

    def test_a_wrong_secret_or_a_wrong_host_gets_nothing(self):
        base = self.link.rsplit("/a/", 1)[0]
        for url in (base + "/", base + "/a/wrong/", base + "/a/", self.link.replace(self.session.token, self.session.token[:-1])):
            with self.subTest(url=url):
                self.assertEqual(call(url)[0], 404)
                self.assertEqual(call(url + "request.json")[0], 404)
        self.assertEqual(call(self.link, headers={"Host": "attacker.example"})[0], 421)
        self.assertEqual(call(self.link + "request.json", headers={"Host": f"attacker.example:{self.session.port}"})[0], 421)
        self.assertEqual(call(self.link, headers={"Host": f"localhost:{self.session.port}"})[0], 200)

    def test_the_request_is_served_with_its_pictures_and_facts_as_data(self):
        served = json.loads(call(self.link + "request.json")[1])
        self.assertEqual(served["items"][0]["images"][0]["caption"], "The mockup")
        self.assertEqual(served["items"][1]["facts"][0]["value"], "<b>12</b>")  # data, which the page shows as text and never as markup

    def test_the_page_puts_request_text_on_the_page_as_text_only(self):
        page = (SCRIPTS / "gamearts_approval_form.html").read_text(encoding="utf-8")
        for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(unsafe, page)
        for outside in ("http://", "https://", "//cdn"):
            self.assertNotIn(outside, page)  # nothing is fetched from anywhere but this computer

    def test_a_picture_is_served_exactly_as_saved_and_only_by_its_place_in_the_request(self):
        status, body, headers = call(self.link + "image/0/0")
        self.assertEqual((status, headers["Content-Type"]), (200, "image/png"))
        self.assertEqual(body, (self.root / "art/market.png").read_bytes())
        for url in ("image/0/1", "image/1/0", "image/9/0", "image/0/x", "image/-1/0", "image/0/0/extra"):
            self.assertEqual(call(self.link + url)[0], 404, url)

    def test_a_picture_that_changed_after_the_request_is_not_shown_in_its_place(self):
        shaded_picture((24, 16), (9, 9, 9)).save(self.root / "art/market.png")
        self.assertEqual(call(self.link + "image/0/0")[0], 409)


class DecisionTests(ServerCase):
    def test_the_decision_file_is_written_once_by_whoever_records_it(self):
        """The page is not the only caller: the settings wizard records its own decision through the same function."""
        payload = {"outcome": "decided", "items": [{"index": 0, "decision": "approved", "comment": ""}, {"index": 1, "decision": "approved", "comment": ""}]}
        approval.record_decision(self.request, self.folder, payload)
        before = (self.folder / "decision.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "already sent"):
            approval.record_decision(self.request, self.folder, dict(payload, items=[dict(entry, decision="rejected", comment="no") for entry in payload["items"]]))
        self.assertEqual((self.folder / "decision.json").read_bytes(), before)

    def test_a_decision_is_written_once_with_the_pictures_it_named_and_nothing_later_replaces_it(self):
        status, body, _ = post(self.link, {"outcome": "decided", "items": [{"index": 0, "decision": "approved", "comment": "love it"},
                                                                           {"index": 1, "decision": "changes", "comment": "fewer colours"}]})
        self.assertEqual(status, 200)
        written = self.decision()
        common.validate_schema(written, "gamearts-approval-decision")
        self.assertEqual((written["via"], written["outcome"], written["approval_id"]), ("approval_form", "decided", self.request["approval_id"]))
        self.assertEqual(written["request_sha256"], common.sha256_file(self.folder / "request.json"))
        first = written["items"][0]
        self.assertEqual((first["kind"], first["id"], first["revision"], first["decision"], first["comment"]), ("mockups", "market", "v001", "approved", "love it"))
        self.assertEqual(first["images"], [{"path": "art/market.png", "sha256": common.sha256_file(self.root / "art/market.png")}])
        self.assertTrue(self.session.finished.is_set())
        before = (self.folder / "decision.json").read_bytes()
        self.assertEqual(post(self.link, everything(self.request, "rejected", "no"))[0], 409)
        self.assertEqual((self.folder / "decision.json").read_bytes(), before)

    def test_deferring_records_that_nothing_was_decided(self):
        self.assertEqual(post(self.link, {"outcome": "deferred", "items": []})[0], 200)
        written = self.decision()
        self.assertEqual((written["outcome"], written["items"]), ("deferred", []))

    def test_an_incomplete_or_malformed_decision_is_refused_and_nothing_is_written(self):
        good = {"index": 0, "decision": "approved", "comment": ""}
        for payload, why in (({"outcome": "decided", "items": [good]}, "Every item"),
                             ({"outcome": "decided", "items": [good, good]}, "Every item"),
                             ({"outcome": "decided", "items": [good, {"index": True, "decision": "approved"}]}, "Every item"),
                             ({"outcome": "decided", "items": [good, {"index": "1", "decision": "approved"}]}, "Every item"),
                             ({"outcome": "decided", "items": "all"}, "Every item"),
                             ({"outcome": "decided", "items": [good, "approved"]}, "Every item"),
                             ({"outcome": "decided", "items": [good, None]}, "Every item"),
                             ({"outcome": "decided", "items": [good, {"index": 1, "decision": "maybe"}]}, "needs one of"),
                             ({"outcome": "decided", "items": [good, {"index": 1, "decision": "approved", "comment": 7}]}, "needs one of"),
                             ({"outcome": "decided", "items": [good, {"index": 1, "decision": "changes", "comment": "  "}]}, "Say what should change"),
                             ({"outcome": "decided", "items": [{"index": 0, "decision": "rejected"}, {"index": 1, "decision": "approved"}]}, "Say what should change"),
                             ({"outcome": "later"}, "outcome"), ([], "outcome"), ("approve", "outcome")):
            with self.subTest(payload=payload):
                status, body, _ = post(self.link, payload)
                self.assertEqual(status, 400)
                self.assertIn(why, json.loads(body)["error"])
        self.assertFalse((self.folder / "decision.json").exists())
        self.assertFalse(self.session.finished.is_set())

    def test_a_decision_that_did_not_come_from_the_page_is_refused(self):
        everyone = everything(self.request)
        self.assertEqual(post(self.link, everyone, {"Origin": "http://attacker.example"})[0], 403)
        self.assertEqual(post(self.link, everyone, {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(post(self.link, b"{not json")[0], 400)
        self.assertEqual(post(self.link, b"\xff\xfe")[0], 400)
        self.assertEqual(post(self.link, b"x" * (local_page.MAX_BODY_BYTES + 1))[0], 413)
        self.assertEqual(post(self.link.replace(self.session.token, "wrong"), everyone)[0], 404)
        self.assertEqual(call(self.link + "decision")[0], 404)  # nothing is decided by a GET
        self.assertFalse((self.folder / "decision.json").exists())
        self.assertEqual(post(self.link, everyone, {"Origin": f"http://127.0.0.1:{self.session.port}"})[0], 200)

    def test_two_answers_at_once_record_one_decision(self):
        results = []
        threads = [threading.Thread(target=lambda: results.append(post(self.link, everything(self.request))[0])) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [200] + [409] * 5)


class AskTests(GameCase):
    def test_the_owner_approves_and_the_agent_gets_the_decision_without_the_secret_address(self):
        said = []
        result = approval.ask(self.root, self.spec(self.market()), 20, opener=owner(lambda r: everything(r, comment="yes")), echo=said.append)
        self.assertEqual(result["outcome"], "decided")
        self.assertEqual(result["decisions"], [{"kind": "mockups", "id": "market", "revision": "v001", "decision": "approved", "comment": "yes"}])
        self.assertEqual(said, [])  # the address is the secret: it is never printed unless asked for
        self.assertTrue((self.root / result["decision_file"]).is_file())
        self.assertNotIn("/a/", json.dumps(result))
        self.assertEqual(approval.status(self.root, result["approval_id"])["outcome"], "decided")

    def test_the_address_is_printed_only_on_request(self):
        said = []
        approval.ask(self.root, self.spec(self.market()), 20, print_link=True, opener=owner(everything), echo=said.append)
        self.assertEqual(len(said), 1)
        self.assertRegex(said[0], r"http://127\.0\.0\.1:\d+/a/[\w-]+/$")

    def test_deciding_later_is_an_outcome_of_its_own(self):
        result = self.ask(self.spec(self.market()), lambda r: {"outcome": "deferred", "items": []})
        self.assertEqual((result["outcome"], result["decisions"]), ("deferred", []))

    def test_no_answer_in_time_is_timed_out_and_records_no_decision(self):
        result = approval.ask(self.root, self.spec(self.market()), 0.3, opener=lambda link: True, echo=lambda text: None)
        self.assertEqual((result["outcome"], result["decision_file"]), ("timed_out", None))
        self.assertEqual(approval.status(self.root, result["approval_id"])["outcome"], "pending")

    def test_a_missing_page_template_is_explained(self):
        with mock.patch.object(approval, "TEMPLATE", self.root / "nothing.html"), self.assertRaisesRegex(ValueError, "nothing.html is not installed beside the Game Arts scripts.*current updater"):
            approval.ask(self.root, self.spec(self.market()), 0.3, opener=lambda link: True, echo=lambda text: None)
        self.assertFalse((self.root / approval.APPROVALS).exists())  # nothing was started

    def test_no_browser_to_open_is_an_error_not_a_silence(self):
        with self.assertRaisesRegex(ValueError, "No browser could be opened"):
            approval.ask(self.root, self.spec(self.market()), 0.3, opener=lambda link: False, echo=lambda text: None)

    def test_every_asking_has_its_own_approval(self):
        first, second = (self.ask(self.spec(self.market())) for _ in range(2))
        self.assertNotEqual(first["approval_id"], second["approval_id"])


class ReferenceTests(GameCase):
    def decided(self, decision="approved", comment="", **market):
        return self.ask(self.spec(self.market(**market), {"kind": "settings", "id": "project", "revision": "abc123def456"}),
                        lambda r: {"outcome": "decided", "items": [{"index": 0, "decision": decision, "comment": comment}, {"index": 1, "decision": "approved", "comment": ""}]})["approval_id"]

    def test_an_approved_item_gives_the_words_recorded_with_the_approval(self):
        approval_id = self.decided(comment="exactly the mood")
        words = approval.reference(self.root, approval_id, "mockups", "market", "v001")
        self.assertIn(approval_id, words)
        self.assertIn("exactly the mood", words)
        self.assertIn(approval_id, approval.reference(self.root, approval_id, "settings", "project", "abc123def456"))
        self.assertIn(approval_id, approval.reference(self.root, approval_id, "mockups", "market"))  # a revision need not be named

    def test_anything_but_approve_gives_no_approval(self):
        for decision in ("changes", "rejected"):
            with self.subTest(decision=decision):
                approval_id = self.decided(decision, "too dark")
                with self.assertRaisesRegex(ValueError, "did not approve.*too dark"):
                    approval.reference(self.root, approval_id, "mockups", "market", "v001")

    def test_it_approves_exactly_what_was_shown_and_nothing_else(self):
        approval_id = self.decided()
        for args, why in ((("mockups", "market", "v002"), "does not ask about"), (("mockups", "tavern", "v001"), "does not ask about"),
                          (("assets", "market", "v001"), "does not ask about"), (("settings", "project", "000000000000"), "does not ask about")):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, why):
                approval.reference(self.root, approval_id, *args)

    def test_a_decision_that_is_missing_deferred_or_tampered_with_approves_nothing(self):
        pending = approval.ask(self.root, self.spec(self.market()), 0.3, opener=lambda link: True, echo=lambda text: None)["approval_id"]
        with self.assertRaisesRegex(ValueError, "no decision yet"):
            approval.reference(self.root, pending, "mockups", "market", "v001")
        later = self.ask(self.spec(self.market()), lambda r: {"outcome": "deferred", "items": []})["approval_id"]
        with self.assertRaisesRegex(ValueError, "decide later"):
            approval.reference(self.root, later, "mockups", "market", "v001")
        edited = self.decided()
        request_file = self.root / approval.APPROVALS / edited / "request.json"
        request = common.read_json(request_file)
        request["items"][0]["title"] = "Something else"
        common.atomic_write_json(request_file, request)
        with self.assertRaisesRegex(ValueError, "changed after the owner decided"):
            approval.reference(self.root, edited, "mockups", "market", "v001")
        for bad in ("nope", "../x", "20261030T101500Z-ZZZZZZ", "", None):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "not an approval id"):
                approval.reference(self.root, bad, "mockups", "market", "v001")
        with self.assertRaisesRegex(ValueError, "no approval"):
            approval.reference(self.root, "20261030T101500Z-abcdef", "mockups", "market", "v001")

    def test_a_decision_copied_from_another_approval_is_not_taken(self):
        one, two = self.decided(), self.decided()
        (self.root / approval.APPROVALS / two / "decision.json").write_bytes((self.root / approval.APPROVALS / one / "decision.json").read_bytes())
        with self.assertRaisesRegex(ValueError, "belongs to approval"):
            approval.reference(self.root, two, "mockups", "market", "v001")

    def test_a_picture_that_changed_or_vanished_after_the_owner_saw_it_is_not_approved(self):
        approval_id = self.decided()
        shaded_picture((24, 16), (200, 200, 10)).save(self.root / "art/market.png")
        with self.assertRaisesRegex(ValueError, "not the picture the owner approved"):
            approval.reference(self.root, approval_id, "mockups", "market", "v001")
        (self.root / "art/market.png").unlink()
        with self.assertRaisesRegex(ValueError, "no longer where the owner saw it"):
            approval.reference(self.root, approval_id, "mockups", "market", "v001")

    def test_shown_lists_what_the_owner_was_shown_of_one_kind(self):
        approval_id = self.decided()
        self.assertEqual(approval.shown(self.root, approval_id, "mockups"), [("market", "v001")])
        self.assertEqual(approval.shown(self.root, approval_id, "assets"), [])


class ExpectedDecisionTests(GameCase):
    """What a caller that acts on a change request or a rejection (not only on an approval) asks of the same decision."""

    def decided(self, *choices):
        items = [{"kind": "other", "id": f"change-request-{at}", "title": f"Change {at}"} for at in range(len(choices))]
        return self.ask(self.spec(*items), lambda r: {"outcome": "decided", "items": [{"index": at, "decision": choice, "comment": f"because {at}"} for at, choice in enumerate(choices)]})["approval_id"]

    def test_a_caller_can_ask_for_a_rejection_or_a_change_and_gets_those_words(self):
        approval_id = self.decided("rejected", "changes", "approved")
        rejected = approval.reference(self.root, approval_id, "other", "change-request-0", expected="rejected")
        self.assertTrue(rejected.startswith("Rejected in the Game Arts approval form"))
        self.assertIn("because 0", rejected)
        self.assertTrue(approval.reference(self.root, approval_id, "other", "change-request-1", expected="changes").startswith("Asked for changes"))
        self.assertTrue(approval.reference(self.root, approval_id, "other", "change-request-2").startswith("Approved"))

    def test_a_choice_other_than_the_one_asked_for_is_refused_by_name(self):
        approval_id = self.decided("rejected", "approved")
        with self.assertRaisesRegex(ValueError, "did not approve other change-request-0.*they chose rejected: because 0"):
            approval.reference(self.root, approval_id, "other", "change-request-0")
        with self.assertRaisesRegex(ValueError, "did not choose rejected for other change-request-1.*they chose approved"):
            approval.reference(self.root, approval_id, "other", "change-request-1", expected="rejected")
        with self.assertRaisesRegex(ValueError, "expected must be one of"):
            approval.reference(self.root, approval_id, "other", "change-request-0", expected="maybe")

    def test_several_items_give_their_words_joined_without_repeats_and_one_wrong_item_refuses_all(self):
        approval_id = self.decided("approved", "approved", "rejected")
        both = approval.references(self.root, approval_id, [("other", "change-request-0", None), ("other", "change-request-1", None)])
        self.assertEqual(both.count(" | "), 1)
        self.assertEqual(approval.references(self.root, approval_id, [("other", "change-request-0", None)] * 2), approval.reference(self.root, approval_id, "other", "change-request-0"))
        with self.assertRaisesRegex(ValueError, "change-request-2"):
            approval.references(self.root, approval_id, [("other", "change-request-0", None), ("other", "change-request-2", None)])
        with self.assertRaisesRegex(ValueError, "at least one item"):
            approval.references(self.root, approval_id, [])

    def test_a_rejection_does_not_need_the_pictures_to_be_unchanged(self):
        picture = self.picture()
        approval_id = self.ask(self.spec({"kind": "mockups", "id": "market", "revision": "v001", "images": [{"path": picture}]}), lambda r: everything(r, "rejected", "no"))["approval_id"]
        shaded_picture((24, 16), (1, 1, 1)).save(self.root / picture)
        self.assertIn("no", approval.reference(self.root, approval_id, "mockups", "market", "v001", expected="rejected"))


class CommandCase(GameCase):
    def register(self, mockup_id, approved=False):
        image, metadata = make_mockup(self.root, mockup_id, "v001", "world")
        life.register_mockup(self.root, metadata, image)
        if approved:
            life.approve_mockup(self.root, mockup_id, "v001", "approved in the test")
        return image.relative_to(self.root).as_posix()

    def mockup_item(self, mockup_id, image):
        return {"kind": "mockups", "id": mockup_id, "revision": "v001", "title": mockup_id, "images": [{"path": image}]}

    def lifecycle(self, operation, *args):
        return run("gamearts_asset_lifecycle.py", operation, "--game-root", self.root, *args)


class MockupCommandTests(CommandCase):
    def manifest(self):
        return common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"]

    def record(self, mockup_id):
        return next(row for row in self.manifest() if row["mockup_id"] == mockup_id)

    def test_a_mockup_the_owner_approved_in_the_form_is_approved_and_the_record_names_the_form(self):
        approval_id = self.ask(self.spec(self.mockup_item("market", self.register("market"))), lambda r: everything(r, comment="yes, that one"))["approval_id"]
        done = self.lifecycle("approve-mockup", "--id", "market", "--revision", "v001", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 0, done.stderr)
        record = self.record("market")
        self.assertEqual(record["status"], "approved")
        self.assertIn(approval_id, record["approval_reference"])
        self.assertIn("yes, that one", record["approval_reference"])

    def test_a_mockup_the_owner_asked_to_change_stays_as_it_was(self):
        approval_id = self.ask(self.spec(self.mockup_item("market", self.register("market"))), lambda r: everything(r, "changes", "warmer light"))["approval_id"]
        done = self.lifecycle("approve-mockup", "--id", "market", "--revision", "v001", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 1)
        self.assertIn("did not approve", done.stderr)
        self.assertIn("warmer light", done.stderr)
        self.assertEqual(self.record("market")["status"], "generated")

    def test_the_decision_for_one_mockup_does_not_approve_another(self):
        image = self.register("market")
        self.register("tavern")
        approval_id = self.ask(self.spec(self.mockup_item("market", image)))["approval_id"]
        done = self.lifecycle("approve-mockup", "--id", "tavern", "--revision", "v001", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.record("tavern")["status"], "generated")

    def test_the_owners_words_still_work_and_one_of_the_two_is_needed(self):
        self.register("market")
        words = self.lifecycle("approve-mockup", "--id", "market", "--revision", "v001", "--user-approval-ref", "yes please")
        self.assertEqual(words.returncode, 0, words.stderr)
        self.register("tavern")
        neither = self.lifecycle("approve-mockup", "--id", "tavern", "--revision", "v001")
        self.assertEqual(neither.returncode, 2)
        both = self.lifecycle("approve-mockup", "--id", "tavern", "--revision", "v001", "--user-approval-ref", "yes", "--approval-id", "20261030T101500Z-abcdef")
        self.assertEqual(both.returncode, 2)
        self.assertEqual(self.record("tavern")["status"], "generated")

    def test_a_batch_approves_what_the_owner_approved_and_leaves_the_rest_with_the_reason(self):
        items = [self.mockup_item("market", self.register("market")), self.mockup_item("tavern", self.register("tavern"))]
        approval_id = self.ask(self.spec(*items), lambda r: {"outcome": "decided", "items": [
            {"index": 0, "decision": "approved", "comment": ""}, {"index": 1, "decision": "changes", "comment": "door too small"}]})["approval_id"]
        done = self.lifecycle("approve-batch", "--kind", "mockups", "--item", "market:v001", "--item", "tavern:v001", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 1)
        result = json.loads(done.stdout)
        self.assertEqual(result["approved"], ["market:v001"])
        self.assertIn("door too small", result["not_approved"][0]["reason"])
        self.assertEqual((self.record("market")["status"], self.record("tavern")["status"]), ("approved", "generated"))

    def test_a_batch_cannot_approve_what_the_form_did_not_show(self):
        image = self.register("market")
        self.register("tavern")
        approval_id = self.ask(self.spec(self.mockup_item("market", image)))["approval_id"]
        done = self.lifecycle("approve-batch", "--kind", "mockups", "--item", "market:v001", "--item", "tavern:v001", "--approval-id", approval_id)
        result = json.loads(done.stdout)
        self.assertEqual(result["approved"], ["market:v001"])
        self.assertIn("not among the items shown", result["not_approved"][0]["reason"])
        self.assertEqual(self.record("tavern")["status"], "generated")

    def test_a_batch_takes_what_was_shown_from_the_form_or_from_the_agent_never_both(self):
        image = self.register("market")
        approval_id = self.ask(self.spec(self.mockup_item("market", image)))["approval_id"]
        both = self.lifecycle("approve-batch", "--kind", "mockups", "--item", "market:v001", "--shown", "market:v001", "--approval-id", approval_id)
        self.assertEqual(both.returncode, 2)
        self.assertIn("--shown goes with the owner's words", both.stderr)
        unshown = self.lifecycle("approve-batch", "--kind", "mockups", "--item", "market:v001", "--user-approval-ref", "yes")
        self.assertEqual(unshown.returncode, 2)
        self.assertEqual(self.record("market")["status"], "generated")

    def test_a_revoked_mockup_is_restored_on_the_owners_decision_in_the_form(self):
        self.register("market", approved=True)
        life.revoke(self.root, "mockups", "market", "the light was wrong", "v001")
        approval_id = self.ask(self.spec({"kind": "restore", "id": "market", "revision": "v001", "title": "Bring back the market"}))["approval_id"]
        done = self.lifecycle("restore", "--kind", "mockups", "--id", "market", "--revision", "v001", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.record("market")["status"], "generated")  # a restored picture is back for review, as with the owner's words
        self.assertIn(approval_id, self.record("market")["restore_reference"])


class AssetCommandTests(CommandCase):
    def bundle(self):
        """An approved mockup and a real sheet bundle made from it, registered and waiting for approval; returns the sheet's path."""
        self.register("hero", approved=True)
        frames = self.root / "work" / "frames"
        frames.mkdir(parents=True)
        for at in range(2):
            key_image((12, 10), {(3 + at, 2): (180, 30, 30, 255)}).save(frames / f"walk{at}.png")
        job = {"name": "hero_v001", "asset_id": "hero_v001", "columns": 2, "padding": 2, "spacing": 3, "source_mockups": [{"mockup_id": "hero", "revision": "v001"}],
               "frames": [{"file": f"walk{at}.png", "name": f"S{at}", "direction": "S", "pivot": [4, 9], "duration_ms": 100} for at in range(2)]}
        (frames / "hero.job.json").write_text(json.dumps(job), encoding="utf-8")
        folder = self.root / OUT / "assets" / "generated" / "hero_v001"
        folder.mkdir(parents=True)
        built = run("build_sheet_atlas.py", frames / "hero.job.json", "--output-dir", folder)
        self.assertEqual(built.returncode, 0, built.stderr)
        registered = self.lifecycle("register-asset", "--id", "hero_v001", "--revision", "v001", "--bundle", f"{OUT}/assets/generated/hero_v001", "--source-mockup", "hero:v001")
        self.assertEqual(registered.returncode, 0, registered.stderr)
        return (folder / "hero_v001.png").relative_to(self.root).as_posix()

    def status(self):
        return next(row for row in common.read_json(self.root / OUT / "manifests" / "assets.json")["assets"] if row["asset_id"] == "hero_v001")["status"]

    def test_an_asset_is_approved_at_the_revision_the_owner_saw_and_not_at_another(self):
        sheet = self.bundle()
        other = self.ask(self.spec({"kind": "assets", "id": "hero_v001", "revision": "v009", "images": [{"path": sheet}]}))["approval_id"]
        refused = self.lifecycle("approve", "--id", "hero_v001", "--approval-id", other)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("does not ask about", refused.stderr)
        self.assertEqual(self.status(), "generated")
        seen = self.ask(self.spec({"kind": "assets", "id": "hero_v001", "revision": "v001", "title": "The hero walking", "images": [{"path": sheet, "caption": "Sheet"}]}),
                        lambda r: everything(r, comment="walks well"))["approval_id"]
        done = self.lifecycle("approve", "--id", "hero_v001", "--approval-id", seen)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.status(), "approved")


class SettingsCommandTests(CommandCase):
    PLAN = [("project_name", "name", "Demo Game"), ("world_kind", "grid_world", None), ("look", "pixel_mid", None), ("viewpoint", "oblique", None),
            ("tile_size", "32x32", None), ("directions", "dirs_4", None), ("animation", "hybrid", None), ("image_generator", "user_supplied", None),
            ("engine", "generic", None), ("palette", "none", None)]

    def written_settings(self):
        for name, value, text in self.PLAN:
            wizard.answer(self.root, name, value, text, "the owner's own words")
        wizard.finish(self.root)
        answers = common.read_json(self.root / ".gamearts" / "project.json")["setup"]["answers"]
        return wizard.version(answers), wizard.summary(answers)

    def test_the_settings_are_confirmed_on_the_decision_to_exactly_the_version_shown(self):
        version, lines = self.written_settings()
        asked = {"kind": "settings", "id": "project", "revision": version, "title": "Your game's settings", "facts": [{"label": "Setting", "value": line} for line in lines[:5]]}
        approval_id = self.ask(self.spec(asked), lambda r: everything(r, comment="these are right"))["approval_id"]
        wizard.answer(self.root, "animation", "frame_based", None, "the owner's own words")  # the settings change after the owner looked at them
        wizard.finish(self.root)
        newer = wizard.version(common.read_json(self.root / ".gamearts" / "project.json")["setup"]["answers"])
        self.assertNotEqual(newer, version)
        wrong = self.lifecycle("confirm-settings", "--approval-id", approval_id, "--presented-version", newer)
        self.assertEqual(wrong.returncode, 1)
        self.assertIn("does not ask about", wrong.stderr)
        self.assertNotEqual(common.read_json(self.root / ".gamearts" / "project.json")["settings_status"], "owner_confirmed")
        wizard.answer(self.root, "animation", "hybrid", None, "the owner's own words")
        wizard.finish(self.root)
        done = self.lifecycle("confirm-settings", "--approval-id", approval_id, "--presented-version", version)
        self.assertEqual(done.returncode, 0, done.stderr)
        settings = common.read_json(self.root / ".gamearts" / "project.json")
        self.assertEqual((settings["settings_status"], settings["confirmed_by"]), ("owner_confirmed", "owner"))
        self.assertIn(approval_id, settings["confirmation_ref"])


class ImportCommandTests(CommandCase):
    """Art the owner brings: the owner's decision in the form stands in for the words that say it is theirs and approved."""

    def sheet(self):
        from test_import_asset import write_sheet
        supplied = self.root / "supplied"
        supplied.mkdir(exist_ok=True)
        return write_sheet(supplied / "hero.png")

    def import_asset(self, *words):
        return self.lifecycle("import-asset", "--source", self.sheet(), "--id", "hero", "--revision", "v001", "--grid", "2x2", "--rights", "owned", *words)

    def test_an_imported_sheet_is_approved_on_the_decision_the_owner_made_for_that_asset(self):
        approval_id = self.ask(self.spec({"kind": "other", "id": "import-asset-hero", "revision": "v001", "title": "My hero sheet is mine and approved"}),
                               lambda r: everything(r, comment="mine, I drew it"))["approval_id"]
        done = self.import_asset("--approval-id", approval_id)
        self.assertEqual(done.returncode, 0, done.stderr)
        mockups = common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"]
        self.assertIn(approval_id, json.dumps(mockups))
        self.assertIn("mine, I drew it", json.dumps(mockups))

    def test_a_decision_for_another_asset_or_a_refusal_imports_nothing(self):
        other = self.ask(self.spec({"kind": "other", "id": "import-asset-villain", "revision": "v001", "title": "Villain"}))["approval_id"]
        refused = self.ask(self.spec({"kind": "other", "id": "import-asset-hero", "revision": "v001", "title": "Hero"}), lambda r: everything(r, "rejected", "not mine"))["approval_id"]
        later = self.ask(self.spec({"kind": "other", "id": "import-asset-hero", "revision": "v002", "title": "Hero, the next revision"}))["approval_id"]
        for approval_id in (other, refused, later):
            with self.subTest(approval_id=approval_id):
                done = self.import_asset("--approval-id", approval_id)
                self.assertEqual(done.returncode, 1)
                self.assertFalse((self.root / OUT / "manifests" / "mockups.json").exists())
        self.assertEqual(self.import_asset().returncode, 2)  # one of the owner's words or the form is needed

    def test_a_picture_imported_as_a_mockup_is_approved_only_when_the_owner_decided_in_the_form(self):
        source = self.root / "supplied" / "tavern.png"
        source.parent.mkdir()
        shaded_picture((48, 32), (90, 50, 30)).save(source)
        arguments = ("import-mockup", "--source", source, "--id", "tavern", "--revision", "v001", "--scope", "scene")
        left = self.lifecycle(*arguments)
        self.assertEqual(left.returncode, 0, left.stderr)
        self.assertEqual(json.loads(left.stdout)["status"], "generated")  # no approval given: left for review
        approval_id = self.ask(self.spec({"kind": "other", "id": "import-mockup-tavern2", "revision": "v001", "title": "Tavern"}))["approval_id"]
        done = self.lifecycle("import-mockup", "--source", source, "--id", "tavern2", "--revision", "v001", "--scope", "scene", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "approved")
        mismatch = self.lifecycle("import-mockup", "--source", source, "--id", "tavern3", "--revision", "v001", "--scope", "scene", "--approval-id", approval_id)
        self.assertEqual(mismatch.returncode, 1)

    def test_a_limited_facing_profile_is_approved_on_the_owners_decision(self):
        approval_id = self.ask(self.spec({"kind": "other", "id": "limited-profile-hero", "revision": "v001", "title": "Four directions only"}))["approval_id"]
        done = self.lifecycle("register-asset", "--id", "hero", "--revision", "v001", "--bundle", "nowhere", "--source-mockup", "none:v001",
                              "--limited-profile-approval-id", approval_id)
        self.assertEqual(done.returncode, 1)
        self.assertNotIn("limited-profile-hero", done.stderr)  # the owner's decision was found and used; it is this bundle that does not exist
        elsewhere = self.ask(self.spec({"kind": "other", "id": "limited-profile-villain", "revision": "v001", "title": "Villain"}))["approval_id"]
        wrong = self.lifecycle("register-asset", "--id", "hero", "--revision", "v001", "--bundle", "nowhere", "--source-mockup", "none:v001", "--limited-profile-approval-id", elsewhere)
        self.assertEqual(wrong.returncode, 1)
        self.assertIn("limited-profile-hero", wrong.stderr)  # a decision about another asset is not this asset's approval
        both = self.lifecycle("register-asset", "--id", "hero", "--revision", "v001", "--bundle", "x", "--source-mockup", "none:v001", "--limited-profile-ref", "yes",
                              "--limited-profile-approval-id", approval_id)
        self.assertEqual(both.returncode, 2)


class VisualReviewCommandTests(CommandCase):
    """The owner's visual review of an extraction: the form shows both boards and the decision file is written from what they chose."""

    def packet(self):
        import visual_review_cleanup as review
        from test_visual_review_cleanup import fixture
        cleanup, spec, _ = fixture(self.root)
        return review.prepare(cleanup, spec, self.root / "review")

    def script(self, command, *args):
        return run("visual_review_cleanup.py", command, *args)

    def request(self, packet):
        done = self.script("request", "--game-root", self.root, "--packet", packet)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["items"]

    def test_the_request_shows_both_boards_what_is_approved_and_what_is_not_assessed(self):
        (item,) = self.request(self.packet())
        self.assertEqual((item["kind"], item["id"], item["revision"]), ("other", "visual-review-test_workshop", "v002"))
        self.assertEqual([image["path"] for image in item["images"]], ["review/visual_review_board.png", "review/visual_review_props.png"])
        facts = {fact["label"]: fact["value"] for fact in item["facts"]}
        self.assertEqual((facts["Parts approved"], facts["Uncertain regions acknowledged"]), ("workbench", "tabletop"))
        self.assertIn("no object recognition", facts["Not assessed"])

    def test_the_decision_is_written_from_the_owners_approval_and_passes_verification(self):
        packet = self.packet()
        approval_id = self.ask(self.spec(*self.request(packet)), lambda r: everything(r, comment="looks right"))["approval_id"]
        done = self.script("decide", "--game-root", self.root, "--packet", packet, "--approval-id", approval_id)
        self.assertEqual(done.returncode, 0, done.stderr)
        vote = common.read_json(self.root / "review" / "decision.json")
        self.assertEqual((vote["decision"], vote["reviewer_type"], vote["packet_sha256"]), ("approved", "user", common.sha256_file(packet)))
        self.assertIn(approval_id, vote["user_approval_reference"])
        self.assertIn("looks right", vote["user_approval_reference"])
        self.assertEqual(json.loads(done.stdout)["review_status"], "user_visual_approval_recorded")

    def test_no_decision_file_is_written_when_the_owner_did_not_approve_or_the_boards_changed(self):
        packet = self.packet()
        declined = self.ask(self.spec(*self.request(packet)), lambda r: everything(r, "changes", "the bench is cut off"))["approval_id"]
        done = self.script("decide", "--game-root", self.root, "--packet", packet, "--approval-id", declined)
        self.assertEqual(done.returncode, 1)
        self.assertIn("the bench is cut off", done.stderr)
        approved = self.ask(self.spec(*self.request(packet)))["approval_id"]
        board = self.root / "review" / "visual_review_board.png"
        shaded_picture((900, 40), (1, 2, 3)).save(board)  # the board changed after the owner saw it
        changed = self.script("decide", "--game-root", self.root, "--packet", packet, "--approval-id", approved)
        self.assertEqual(changed.returncode, 1)
        self.assertFalse((self.root / "review" / "decision.json").exists())

    def test_a_decision_for_another_revision_is_not_this_reviews_approval(self):
        packet = self.packet()
        item = dict(self.request(packet)[0], revision="v999")
        approval_id = self.ask(self.spec(item))["approval_id"]
        done = self.script("decide", "--game-root", self.root, "--packet", packet, "--approval-id", approval_id)
        self.assertEqual(done.returncode, 1)
        self.assertFalse((self.root / "review" / "decision.json").exists())

    def test_a_decision_for_another_asset_is_not_this_reviews_approval(self):
        packet = self.packet()
        elsewhere = self.ask(self.spec({"kind": "other", "id": "visual-review-other_asset", "revision": "v002", "title": "Another"}))["approval_id"]
        done = self.script("decide", "--game-root", self.root, "--packet", packet, "--approval-id", elsewhere)
        self.assertEqual(done.returncode, 1)
        self.assertIn("visual-review-test_workshop", done.stderr)


class StoryboardCommandTests(CommandCase):
    def setUp(self):
        super().setUp()
        board.write(self.root, {"title": "A coach's first season", "origin": "agent_authored", "brief": "a quiet town",
                                "scenes": [{"id": "arrival", "title": "Arrival", "summary": "The coach steps off the bus."},
                                           {"id": "first-match", "title": "First match", "summary": "Rain, a late goal."}]}, "agent", "drafted")

    def scenes(self):
        """The items exactly as `approval-request` gives them for the form."""
        done = run("gamearts_storyboard.py", "approval-request", "--game-root", self.root, "--scenes", "arrival,first-match")
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["items"]

    def test_the_request_for_the_form_names_each_scene_with_its_words_and_revision(self):
        arrival, first = self.scenes()
        self.assertEqual((arrival["kind"], arrival["id"], arrival["title"]), ("storyboard", "arrival", "Arrival"))
        self.assertEqual(arrival["facts"], [{"label": "Summary", "value": "The coach steps off the bus."}])
        self.assertEqual(len(arrival["revision"]), 12)
        self.assertNotEqual(arrival["revision"], first["revision"])
        self.assertEqual(run("gamearts_storyboard.py", "approval-request", "--game-root", self.root, "--scenes", "nowhere").returncode, 1)

    def test_a_long_scene_field_is_shortened_on_the_page_but_the_revision_covers_all_of_it(self):
        def revision_of(tail):
            data = board.load(self.root)
            data["scenes"][0]["summary"] = "x" * 450 + tail
            board.write(self.root, {key: data[key] for key in ("title", "origin", "brief", "scenes")}, "agent", "a long summary")
            return self.scenes()[0]
        first, second = revision_of(" one"), revision_of(" two")
        value = first["facts"][0]["value"]
        self.assertEqual((len(value), value[-1]), (400, "\u2026"))
        self.assertNotEqual(first["revision"], second["revision"])  # the owner saw the same 399 characters, but these are different scenes

    def test_a_scene_edited_after_the_owner_saw_it_is_not_approved_by_that_decision(self):
        approval_id = self.ask(self.spec(*self.scenes()))["approval_id"]
        edited = board.load(self.root)
        edited["scenes"][0]["summary"] = "The coach is late and the bus leaves."
        board.write(self.root, {key: edited[key] for key in ("title", "origin", "brief", "scenes")}, "agent", "changed after the owner saw it")
        done = run("gamearts_storyboard.py", "approve", "--game-root", self.root, "--scenes", "arrival,first-match", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 1)
        self.assertIn("storyboard arrival", done.stderr)
        self.assertNotEqual(board.load(self.root)["sequence"]["status"], "approved")

    def test_the_scenes_the_owner_approved_become_the_approved_sequence(self):
        approval_id = self.ask(self.spec(*self.scenes()))["approval_id"]
        done = run("gamearts_storyboard.py", "approve", "--game-root", self.root, "--scenes", "arrival,first-match", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(board.load(self.root)["sequence"]["order"], ["arrival", "first-match"])

    def test_one_scene_the_owner_did_not_approve_keeps_the_sequence_from_being_approved(self):
        approval_id = self.ask(self.spec(*self.scenes()), lambda r: {"outcome": "decided", "items": [
            {"index": 0, "decision": "approved", "comment": ""}, {"index": 1, "decision": "rejected", "comment": "cut it"}]})["approval_id"]
        done = run("gamearts_storyboard.py", "approve", "--game-root", self.root, "--scenes", "arrival,first-match", "--approval-id", approval_id)
        self.assertEqual(done.returncode, 1)
        self.assertIn("cut it", done.stderr)
        self.assertNotEqual(board.load(self.root)["sequence"]["status"], "approved")


class CommandLineTests(GameCase):
    def main(self, *args, opener=None):
        """The command line, in this process, with the browser replaced by `opener`: the suite never opens a real one."""
        out = io.StringIO()
        with mock.patch.object(local_page.webbrowser, "open", side_effect=opener or (lambda link: True)), mock.patch.object(sys, "argv", ["gamearts_approval.py", *map(str, args)]), \
                contextlib.redirect_stdout(out):
            code = approval.main()
        return code, out.getvalue()

    def test_the_command_line_asks_then_shows_what_was_decided(self):
        request = self.root / "request.json"
        request.write_text(json.dumps(self.spec(self.market())), encoding="utf-8")
        code, printed = self.main("ask", "--game-root", self.root, "--request", request, opener=owner(everything))
        result = json.loads(printed)
        self.assertEqual((code, result["outcome"]), (0, "decided"))
        code, printed = self.main("show", "--game-root", self.root, "--approval-id", result["approval_id"])
        self.assertEqual((code, json.loads(printed)["decisions"][0]["decision"]), (0, "approved"))

    def test_an_unanswered_asking_exits_with_a_status_that_is_not_success(self):
        request = self.root / "request.json"
        request.write_text(json.dumps(self.spec(self.market())), encoding="utf-8")
        code, printed = self.main("ask", "--game-root", self.root, "--request", request, "--timeout", "0.3")
        self.assertEqual((code, json.loads(printed)["outcome"]), (2, "timed_out"))

    def reference(self, approval_id, *args):
        return run("gamearts_approval.py", "reference", "--game-root", self.root, "--approval-id", approval_id, *args)

    def test_the_reference_command_prints_the_owners_words_only_when_every_item_is_as_asked(self):
        approval_id = self.ask(self.spec({"kind": "other", "id": "story-settings-1", "title": "Story"}, {"kind": "other", "id": "scene-list"},
                                         {"kind": "other", "id": "change-request-9"}),
                               lambda r: {"outcome": "decided", "items": [{"index": 0, "decision": "approved", "comment": "good"}, {"index": 1, "decision": "approved", "comment": "good"},
                                                                         {"index": 2, "decision": "rejected", "comment": "not now"}]})["approval_id"]
        done = self.reference(approval_id, "--item", "other:story-settings-1", "--item", "other:scene-list")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual((result["approval_id"], result["decision"]), (approval_id, "approved"))
        self.assertEqual(result["reference"].count(" | "), 0)  # the same words twice are given once
        self.assertIn("good", result["reference"])
        rejected = self.reference(approval_id, "--item", "other:change-request-9", "--decision", "rejected")
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertIn("not now", json.loads(rejected.stdout)["reference"])
        for args in (("--item", "other:story-settings-1", "--item", "other:change-request-9"), ("--item", "other:change-request-9"), ("--item", "other:story-settings-1:v2"),
                     ("--item", "other:missing"), ("--item", "other:story-settings-1", "--decision", "rejected")):
            with self.subTest(args=args):
                refused = self.reference(approval_id, *args)
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(refused.stdout, "")
                self.assertIn("BLOCKED", refused.stderr)

    def test_the_reference_command_refuses_an_approval_that_is_missing_deferred_or_edited(self):
        later = self.ask(self.spec({"kind": "other", "id": "x"}), lambda r: {"outcome": "deferred", "items": []})["approval_id"]
        edited = self.ask(self.spec({"kind": "other", "id": "x"}))["approval_id"]
        request_file = self.root / approval.APPROVALS / edited / "request.json"
        request = common.read_json(request_file)
        request["title"] = "Something else"
        common.atomic_write_json(request_file, request)
        for approval_id in (later, edited, "20261030T101500Z-abcdef"):
            with self.subTest(approval_id=approval_id):
                refused = self.reference(approval_id, "--item", "other:x")
                self.assertEqual((refused.returncode, refused.stdout), (1, ""))

    def test_the_reference_command_needs_a_known_kind_and_an_item(self):
        approval_id = self.ask(self.spec({"kind": "other", "id": "x"}))["approval_id"]
        for args in (("--item", "dessert:x"), ("--item", "other"), ("--item", "other:"), ()):
            with self.subTest(args=args):
                self.assertEqual(self.reference(approval_id, *args).returncode, 2)

    def test_an_unknown_approval_is_reported_as_blocked(self):
        unknown = run("gamearts_approval.py", "show", "--game-root", self.root, "--approval-id", "20261030T101500Z-abcdef")
        self.assertEqual(unknown.returncode, 1)
        self.assertIn("no approval", unknown.stderr)


if __name__ == "__main__":
    unittest.main()
