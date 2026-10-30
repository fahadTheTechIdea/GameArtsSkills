#!/usr/bin/env python3
"""The settings wizard as a page: the same questions as `gamearts_setup.py`, answered by choosing on one page in the owner's browser, so creating or changing a
game's Game Arts settings is a few clicks instead of a conversation.

  python scripts/gamearts_setup_form.py run --game-root GAME [--timeout SECONDS] [--print-link]

`run` serves the page on this computer only (see gamearts_local_page.py), opens the owner's browser and waits. Every answer goes through
`gamearts_setup.answer`, the one code path the command line uses, with the owner's own click recorded as their words; nothing is stored anywhere else. The page
starts from the game's current answers and marks what an existing project.json holds, never choosing it for the owner. When the last question is answered the
owner sees the written summary and either saves the settings (`finish`) or saves and confirms them: that writes an approval of the settings the owner was shown
(gamearts_approval.py, kind settings) and confirms through `confirm-settings`'s own function, so the confirmation names the form it came from.

The result on stdout is {outcome, complete, version, answered, unanswered, settings_status}; the exit status is 0 when the owner saved the settings and 2 when
they left, or nobody answered, before that.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_approval as approval  # noqa: E402
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_local_page as local_page  # noqa: E402
import gamearts_setup as wizard  # noqa: E402

TEMPLATE = Path(__file__).with_name("gamearts_setup_form.html")
DEFAULT_WAIT_SECONDS = approval.DEFAULT_WAIT_SECONDS


class SetupSession(local_page.LocalSession):
    """The wizard being shown: the page, its secret address and the owner's one way out (saved, confirmed or left)."""

    template = TEMPLATE
    post_routes = ("answer", "save", "confirm", "leave")

    def __init__(self, root):
        super().__init__(Path(root))
        self.outcome = None
        self.approval_id = None

    def get(self, rest):
        if rest == ["state.json"]:
            return 200, json.dumps(wizard.form_state(self.root), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"
        return None

    def post(self, name, payload):
        with self.lock:
            if self.outcome is not None:
                return 409, {"error": "This settings page is already finished."}
            try:
                body = getattr(self, "_" + name)(payload if isinstance(payload, dict) else {})
            except ValueError as exc:  # a refusal the page shows to the owner: what to fix
                return 400, {"error": str(exc)}
            except OSError as exc:  # the answer or the settings could not be written: the owner is told
                return 500, {"error": f"That could not be saved ({exc.strerror or exc}); try again."}
            return 200, body

    def _answer(self, payload):
        name, value, text = payload.get("id"), payload.get("value"), payload.get("text")
        if not isinstance(name, str) or not isinstance(value, str) or not (text is None or isinstance(text, str)):
            raise ValueError("The answer is missing its question or its choice.")
        asked = wizard.question(name, wizard.load_answers(self.root))
        label = next((option["label"] for option in (asked or {"options": []})["options"] if option["value"] == value), value)
        said = f"Chose “{label}” on the Game Arts settings page" + (f": “{text.strip()}”" if text and text.strip() else "")
        wizard.answer(self.root, name, value, text, said)
        return wizard.form_state(self.root)

    def _save(self, payload):
        result = wizard.finish(self.root)
        self._end("saved")
        return {"saved": True, "settings_status": result["settings_status"], "version": result["version"]}

    def _confirm(self, payload):
        result = wizard.finish(self.root)
        version = result["version"]
        if result["settings_status"] != "owner_confirmed":  # unchanged settings the owner already confirmed need no second confirmation
            request, folder = approval.save_request(self.root, self._request(version))
            approval.record_decision(request, folder, {"outcome": "decided", "items": [{"index": 0, "decision": "approved", "comment": ""}]})
            words = approval.reference(self.root, request["approval_id"], "settings", "project", version)
            life.confirm_settings(self.root, "owner", words, version)
            self.approval_id = request["approval_id"]
        self._end("confirmed")
        return {"confirmed": True, "version": version, "approval_id": self.approval_id}

    def _leave(self, payload):
        self._end("left")
        return {"left": True}

    def _end(self, outcome):
        self.outcome = outcome
        self.finished.set()

    def _request(self, version):
        """What the owner confirms, as an approval request: the picks they made as facts, the consequences as the message."""
        lines = wizard.summary(wizard.load_answers(self.root))
        picks = [line for line in lines if not line.startswith("Consequence: ")]
        facts = [{"label": label[:60], "value": value[:400]} for label, _, value in (line.partition(": ") for line in picks)][:20]
        message = "\n".join(line[len("Consequence: "):] for line in lines if line.startswith("Consequence: "))[:2000]
        return {"schema_version": "1.0", "title": "Confirm the Game Arts settings", "message": message,
                "items": [{"kind": "settings", "id": "project", "revision": version, "title": "Game Arts settings", "facts": facts}]}


def run(game_root, timeout=DEFAULT_WAIT_SECONDS, print_link=False, opener=None, echo=None):
    """Show the settings wizard and wait for the owner. Returns the outcome (saved, confirmed, left or timed_out) with where the answers stand, so a caller can
    tell whether to go on."""
    root = common.game_root(game_root)
    local_page.require_installed(TEMPLATE)
    session = SetupSession(root)
    answered = local_page.show(session, timeout, print_link, opener, echo)
    state = wizard.form_state(root)
    return {"outcome": session.outcome if answered else "timed_out", "complete": state["complete"], "version": state["version"], "answered": state["answered"],
            "unanswered": state["unanswered"], "settings_status": state["settings_status"], "approval_id": session.approval_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    sub = ops.add_parser("run")
    sub.add_argument("--game-root", type=Path, required=True)
    sub.add_argument("--timeout", type=float, default=DEFAULT_WAIT_SECONDS, help="Seconds to wait for the owner (default 1800)")
    sub.add_argument("--print-link", action="store_true", help="Print the secret address on stderr, for an owner who reaches this computer's localhost another way")
    args = parser.parse_args()
    try:
        result = run(args.game_root, args.timeout, args.print_link)
    except (OSError, ValueError, KeyError) as exc:
        print("BLOCKED", exc, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["outcome"] in ("saved", "confirmed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
