"""The settings wizard as a page: answers go through the setup wizard's own code, the owner's click is their words, and what is saved or confirmed is exactly
what they were shown. Everything runs through the real server and the real command line; the suite never opens a real browser."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import gamearts_testkit  # noqa: F401  (puts scripts/ on sys.path)
from gamearts_testkit import write_settings

import gamearts_approval as approval  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_setup as wizard  # noqa: E402
import gamearts_setup_form as form  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def call(url, payload=None, headers=None):
    """(status, parsed body) of one request, an error status included."""
    data = None if payload is None else (payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8"))
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})} if data is not None else (headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw)
    except urllib.error.HTTPError as failure:
        with failure:
            raw = failure.read()
            return failure.code, (json.loads(raw) if "json" in failure.headers.get("Content-Type", "") else raw)


def pick(question):
    """The choice a test owner makes: the first option that needs no words, else the first, with words."""
    option = next((o for o in question["options"] if o["value"] not in question["needs_words"]), question["options"][0])
    return {"id": question["id"], "value": option["value"], **({"text": "Sunny Farm" if question["id"] == "project_name" else "x"} if option["value"] in question["needs_words"] else {})}


def change(link, name):
    """Answer `name` again with a different option than before."""
    question = next(q for q in call(link + "state.json")[1]["questions"] if q["id"] == name)
    earlier = (question["answered"] or {}).get("value")
    return call(link + "answer", {"id": name, "value": next(o["value"] for o in question["options"] if o["value"] != earlier)})


def answer_everything(link, then=None):
    """The page's own steps: read the state, answer the first open question, repeat; then press `then` (save, confirm or leave)."""
    while True:
        _, state = call(link + "state.json")
        open_question = next((q for q in state["questions"] if not q["answered"]), None)
        if open_question is None:
            break
        status, body = call(link + "answer", pick(open_question))
        assert status == 200, body
    if then:
        return call(link + then, {})


def scripted_owner(then, before=None):
    def opener(link):
        def act():
            if before:
                before(link)
            answer_everything(link, then)
        threading.Thread(target=act, daemon=True).start()
        return True
    return opener


class EmptyGame(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "game"
        self.root.mkdir()

    def run_form(self, then, before=None, timeout=60):
        return form.run(self.root, timeout, opener=scripted_owner(then, before), echo=lambda text: None)

    def project(self):
        return common.read_json(self.root / ".gamearts" / "project.json")


class SessionCase(EmptyGame):
    def setUp(self):
        super().setUp()
        self.session = form.SetupSession(self.root)
        self.session.start()
        self.addCleanup(self.session.close)
        self.link = self.session.link


class PageTests(SessionCase):
    def test_the_page_is_served_with_the_shared_look_and_a_script_that_only_its_nonce_allows(self):
        request = urllib.request.Request(self.link)
        with urllib.request.urlopen(request, timeout=10) as response:
            page, policy = response.read().decode("utf-8"), response.headers["Content-Security-Policy"]
        nonce = policy.split("script-src 'nonce-")[1].split("'")[0]
        self.assertIn(f'<script nonce="{nonce}">', page)
        self.assertIn(f'<style nonce="{nonce}">', page)
        self.assertIn("--accent:", page)  # the shared stylesheet is in it
        self.assertNotIn("{{", page)  # and nothing was left unfilled
        self.assertIn("form-action 'none'", policy)

    def test_a_wrong_address_or_host_gets_nothing(self):
        base = f"http://127.0.0.1:{self.session.port}"
        self.assertEqual(call(base + "/a/wrong/state.json")[0], 404)
        self.assertEqual(call(self.link + "state.json", headers={"Host": f"attacker.example:{self.session.port}"})[0], 421)
        self.assertEqual(call(self.link + "answer", {"id": "world_kind", "value": "grid_world"}, {"Origin": "http://attacker.example"})[0], 403)
        self.assertEqual(call(self.link + "elsewhere", {})[0], 404)

    def test_a_new_game_starts_with_the_first_questions_and_nothing_chosen(self):
        status, state = call(self.link + "state.json")
        self.assertEqual(status, 200)
        self.assertEqual([q["id"] for q in state["questions"]], ["project_name", "world_kind"])
        self.assertEqual((state["complete"], state["has_settings"], state["summary"]), (False, False, None))
        self.assertTrue(all(q["answered"] is None and q["current"] is None for q in state["questions"]))


class AnswerTests(SessionCase):
    def test_a_click_is_recorded_through_the_wizards_own_code_as_the_owners_act(self):
        status, state = call(self.link + "answer", {"id": "project_name", "value": "name", "text": "Sunny Farm"})
        self.assertEqual(status, 200)
        recorded = wizard.load_answers(self.root)["project_name"]
        self.assertEqual((recorded["value"], recorded["text"]), ("name", "Sunny Farm"))
        self.assertEqual(recorded["said"], "Chose “Type the name” on the Game Arts settings page: “Sunny Farm”")
        self.assertEqual(state["questions"][0]["answered"]["value"], "name")

    def test_an_answer_that_is_not_an_option_or_lacks_its_words_is_refused_and_records_nothing(self):
        for payload, why in (({"id": "world_kind", "value": "flying_island"}, "not one of the options"), ({"id": "project_name", "value": "name"}, "needs the owner's own words"),
                             ({"id": "palette", "value": "none"}, "does not apply"), ({"id": 3, "value": "x"}, "missing its question"), ({"value": "x"}, "missing its question")):
            with self.subTest(payload=payload):
                status, body = call(self.link + "answer", payload)
                self.assertEqual(status, 400)
                self.assertIn(why, body["error"])
        self.assertEqual(wizard.load_answers(self.root), {})

    def test_changing_an_answer_resets_only_what_depends_on_it(self):
        call(self.link + "answer", {"id": "project_name", "value": "name", "text": "Sunny Farm"})
        call(self.link + "answer", {"id": "world_kind", "value": "grid_world"})
        _, state = call(self.link + "state.json")
        look = next(q for q in state["questions"] if q["id"] == "look")
        call(self.link + "answer", {"id": "look", "value": look["options"][0]["value"]})
        call(self.link + "answer", {"id": "world_kind", "value": "free_world"})
        answers = wizard.load_answers(self.root)
        self.assertIn("project_name", answers)
        self.assertNotIn("look", answers)

    def test_saving_or_confirming_before_the_last_answer_is_refused_and_the_page_stays_open(self):
        for route in ("save", "confirm"):
            status, body = call(self.link + route, {})
            self.assertEqual(status, 400)
            self.assertIn("Not every setting is answered", body["error"])
        self.assertIsNone(self.session.outcome)
        self.assertFalse((self.root / ".gamearts" / "project.json").exists())


class RunTests(EmptyGame):
    def test_saving_writes_the_settings_for_review_and_reports_where_the_answers_stand(self):
        result = self.run_form("save")
        self.assertEqual((result["outcome"], result["complete"], result["unanswered"], result["settings_status"]), ("saved", True, [], "inferred"))
        self.assertEqual(result["answered"][0], "project_name")
        self.assertEqual(result["version"], wizard.status(self.root)["version"])
        self.assertEqual(self.project()["settings_status"], "inferred")  # written by the wizard, not yet confirmed
        self.assertFalse((self.root / ".gamearts" / "approvals").exists())

    def test_confirming_records_what_the_owner_was_shown_and_confirms_it_through_the_form(self):
        result = self.run_form("confirm")
        self.assertEqual((result["outcome"], result["settings_status"]), ("confirmed", "owner_confirmed"))
        settings = self.project()
        self.assertEqual((settings["settings_status"], settings["confirmed_by"]), ("owner_confirmed", "owner"))
        self.assertIn(result["approval_id"], settings["confirmation_ref"])
        decision = common.read_json(self.root / approval.APPROVALS / result["approval_id"] / "decision.json")
        (item,) = decision["items"]
        self.assertEqual((decision["via"], item["kind"], item["id"], item["decision"], item["revision"]), ("approval_form", "settings", "project", "approved", result["version"]))
        request = common.read_json(self.root / approval.APPROVALS / result["approval_id"] / "request.json")
        self.assertIn("Sunny Farm", json.dumps(request["items"][0]["facts"]))  # the owner confirmed their own picks
        self.assertTrue(common.load_project_settings(self.root)[0])  # and every later command accepts the settings as the owner's

    def test_leaving_keeps_the_answers_writes_no_settings_and_exits_with_the_status_for_not_finished(self):
        result = self.run_form("leave")
        self.assertEqual((result["outcome"], result["complete"], result["settings_status"]), ("left", True, None))
        self.assertFalse((self.root / ".gamearts" / "project.json").exists())
        self.assertTrue(wizard.load_answers(self.root))
        done = subprocess.run([sys.executable, str(SCRIPTS / "gamearts_setup_form.py"), "run", "--game-root", str(self.root), "--timeout", "0.3"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)  # nobody answered
        self.assertEqual(json.loads(done.stdout)["outcome"], "timed_out")

    def test_a_second_visit_starts_from_the_answers_and_a_changed_one_needs_confirming_again(self):
        first = self.run_form("confirm")
        self.assertEqual(first["settings_status"], "owner_confirmed")
        again = self.run_form("confirm")  # nothing changed: the earlier confirmation stands and no second approval is made
        self.assertEqual((again["outcome"], again["approval_id"], again["settings_status"]), ("confirmed", None, "owner_confirmed"))
        changed = self.run_form("save", before=lambda link: change(link, "animation"))
        self.assertEqual(changed["settings_status"], "needs_review")

    def test_the_marks_on_an_existing_games_settings_are_shown_and_never_counted_as_answers(self):
        write_settings(self.root)
        session = form.SetupSession(self.root)
        session.start()
        self.addCleanup(session.close)
        _, state = call(session.link + "state.json")
        self.assertTrue(state["has_settings"])
        self.assertEqual(state["answered"], [])
        self.assertFalse(state["complete"])
        marked = [q["id"] for q in state["questions"] if q["current"]]
        self.assertIn("world_kind", marked)
        self.assertTrue(all(q["answered"] is None for q in state["questions"]))

    def test_a_finished_page_takes_no_more(self):
        session = form.SetupSession(self.root)
        session.start()
        self.addCleanup(session.close)
        self.assertEqual(call(session.link + "leave", {})[0], 200)
        self.assertEqual(call(session.link + "answer", {"id": "world_kind", "value": "grid_world"})[0], 409)
        self.assertEqual(session.outcome, "left")

    def test_no_browser_is_an_error_not_a_silence(self):
        with self.assertRaisesRegex(ValueError, "No browser could be opened"):
            form.run(self.root, 0.3, opener=lambda link: False, echo=lambda text: None)

    def test_a_missing_page_is_explained(self):
        from unittest import mock
        with mock.patch.object(form, "TEMPLATE", self.root / "nothing.html"), self.assertRaisesRegex(ValueError, "nothing.html is not installed.*current updater"):
            form.run(self.root, 0.3, opener=lambda link: True, echo=lambda text: None)


class SharedLookTests(EmptyGame):
    def test_a_missing_shared_stylesheet_is_explained_before_anything_is_shown(self):
        from unittest import mock
        import gamearts_local_page as local_page
        with mock.patch.object(local_page, "BASE_CSS", self.root / "nothing.css"), self.assertRaisesRegex(ValueError, "nothing.css is not installed.*current updater"):
            form.run(self.root, 0.3, opener=lambda link: True, echo=lambda text: None)


class ProjectSettingsOwnerTests(unittest.TestCase):
    def test_only_the_setup_wizard_and_the_confirmation_write_the_project_settings(self):
        """Every wizard page (this one, an approval, any later one) submits to the project settings through gamearts_setup; none keeps or writes its own copy."""
        import re
        writers = sorted(path.name for path in SCRIPTS.glob("*.py")
                         if re.search(r"(atomic_write_json|write_text|write_bytes|open)\([^\n]*project\.json", path.read_text(encoding="utf-8")))
        self.assertEqual(writers, ["gamearts_asset_lifecycle.py", "gamearts_setup.py"])  # the lifecycle one is confirm_settings: it adds the owner's confirmation and nothing else

    def test_the_settings_page_writes_nothing_itself(self):
        source = (SCRIPTS / "gamearts_setup_form.py").read_text(encoding="utf-8")
        self.assertNotIn("atomic_write_json", source)
        self.assertIn("wizard.answer(", source)
        self.assertIn("wizard.finish(", source)


if __name__ == "__main__":
    unittest.main()
