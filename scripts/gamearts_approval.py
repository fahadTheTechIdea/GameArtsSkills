#!/usr/bin/env python3
"""Single owner of the approval form: one page template, shown whenever the owner is asked to approve anything (a mockup, an asset, a storyboard
scene, the saved settings, a restore), with the pictures in front of them, taking their decision from that same page.

  python scripts/gamearts_approval.py ask  --game-root GAME --request REQUEST.json [--timeout SECONDS] [--print-link]
  python scripts/gamearts_approval.py show --game-root GAME --approval-id ID
  python scripts/gamearts_approval.py reference --game-root GAME --approval-id ID --item KIND:ID[:REVISION] [--item ...] [--decision approved|changes|rejected]

`ask` saves the request under GAME/.gamearts/approvals/<id>/, serves the page on this computer only (127.0.0.1, a port the system picks, a secret
address that is never printed unless --print-link is given), opens the owner's browser and waits for the decision. The decision is written by this
server and by nothing else; the commands that approve things take it with --approval-id instead of the owner's typed words. Run `ask` in the
background: the owner may take minutes. A decision is only as strong as the computer it was made on: an agent with file access could write
a decision file, exactly as it can quote an approval the owner never gave, so the form raises the bar and does not claim to remove it.
"""
import argparse
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import gamearts_common as common
import gamearts_local_page as local_page

APPROVALS = Path(".gamearts") / "approvals"
TEMPLATE = Path(__file__).with_name("gamearts_approval_form.html")
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
DECISIONS = ("approved", "changes", "rejected")
KINDS = ("mockups", "assets", "storyboard", "settings", "restore", "other")
NEEDS_A_REASON = ("changes", "rejected")  # the agent can do nothing with a bare "no"
DEFAULT_WAIT_SECONDS = 1800.0
ID_PATTERN = r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}$"


def _now():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


def approval_folder(root, approval_id):
    if not isinstance(approval_id, str) or not re.fullmatch(ID_PATTERN, approval_id):
        raise ValueError(f"{approval_id!r} is not an approval id (it looks like 20261030T101500Z-ab12cd)")
    return common.game_root(root) / APPROVALS / approval_id


# ------------------------------------------------------------------------------------------------ the request
def _fingerprint(root, image):
    """Find a picture the request names, inside the game, and say exactly which file it is."""
    path = common.safe_member(root, image["path"], "a picture path")
    if path.suffix.lower() not in IMAGE_TYPES:
        raise ValueError(f"{image['path']!r} is not a picture the form can show (png, jpg, webp or gif)")
    if not path.is_file():
        raise ValueError(f"{image['path']!r} is not a file in the game folder")
    size = path.stat().st_size
    if not 0 < size <= MAX_IMAGE_BYTES:
        raise ValueError(f"{image['path']!r} is {size} bytes; a picture shown in the form must be between 1 byte and {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
    from PIL import Image
    try:
        with Image.open(path) as opened:
            width, height = opened.size
            opened.verify()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError(f"{image['path']!r} cannot be read as a picture: {exc}") from exc
    return path, {"sha256": common.sha256_file(path), "bytes": size, "width": width, "height": height}


def prepare(root, spec):
    """The request as it is saved: checked against its contract, every picture found inside the game, confirmed to be one, and fingerprinted,
    so the page shows and the decision records exactly the files that were named."""
    common.validate_schema(spec, "gamearts-approval-request")
    root = common.game_root(root)
    request = json.loads(json.dumps(spec))
    seen = set()
    for item in request["items"]:
        key = (item["kind"], item["id"], item.get("revision"))
        if key in seen:
            raise ValueError(f"{item['kind']} {item['id']}" + (f" {item['revision']}" if item.get("revision") else "") + " is listed twice in one request")
        seen.add(key)
        for image in item.get("images", []):
            image.update(_fingerprint(root, image)[1])
    return request


# ------------------------------------------------------------------------------------------------ the server
class Session(local_page.LocalSession):
    """One request being shown: the page, its secret address and the single decision it will accept."""

    template = TEMPLATE
    post_routes = ("decision",)

    def __init__(self, root, request, folder):
        super().__init__(Path(root))
        self.request, self.folder = request, Path(folder)
        self.result = None

    def get(self, rest):
        if rest == ["request.json"]:
            return 200, json.dumps(self.request).encode("utf-8"), "application/json; charset=utf-8"
        if len(rest) == 3 and rest[0] == "image" and rest[1].isdigit() and rest[2].isdigit():
            return self._image(int(rest[1]), int(rest[2]))
        return None

    def _image(self, item_at, image_at):
        try:
            image = self.request["items"][item_at]["images"][image_at]
        except (IndexError, KeyError):
            return None
        path = common.safe_member(self.root, image["path"], "a picture path")
        data = path.read_bytes() if path.is_file() else b""
        if common.sha256_bytes(data) != image["sha256"]:  # the owner must see what the decision will name
            return 409, b"This picture changed after the approval was requested"
        return 200, data, IMAGE_TYPES[path.suffix.lower()]

    def post(self, name, payload):
        return self.decide(payload)

    def decide(self, payload):
        """(status, body) for what the page sent. The first valid decision is written and nothing later replaces it."""
        with self.lock:
            if self.result is not None:
                return 409, {"error": "A decision was already sent for this approval."}
            try:
                self.result = record_decision(self.request, self.folder, payload)
            except ValueError as exc:  # a refusal the page shows to the owner: what to fix
                return 400, {"error": str(exc)}
            except OSError as exc:  # the decision could not be saved: the owner is told, nothing was recorded
                return 500, {"error": f"The decision could not be saved ({exc.strerror or exc}); try again."}
            self.finished.set()
            return 200, {"ok": True}


def build_decision(request, folder, payload):
    """The decision a page sent, checked against the request it answers: every item decided, a reason for anything but approval, pictures as they were shown."""
    if not isinstance(payload, dict) or payload.get("outcome") not in ("decided", "deferred"):
        raise ValueError("The decision is missing its outcome.")
    decision = {"schema_version": "1.0", "approval_id": request["approval_id"],
                "request_sha256": common.sha256_file(Path(folder) / "request.json"), "decided_at_utc": _now(),
                "via": "approval_form", "outcome": payload["outcome"], "items": []}
    if payload["outcome"] == "deferred":
        return decision
    sent = payload.get("items")
    wanted = request["items"]
    whole = isinstance(sent, list) and all(isinstance(entry, dict) and type(entry.get("index")) is int for entry in sent)  # then the indexes must be exactly 0..n-1
    if not whole or sorted(entry["index"] for entry in sent) != list(range(len(wanted))):
        raise ValueError("Every item needs a decision.")
    for entry in sorted(sent, key=lambda entry: entry["index"]):
        item = wanted[entry["index"]]
        comment = entry.get("comment", "")
        if entry.get("decision") not in DECISIONS or not isinstance(comment, str):
            raise ValueError(f"“{item.get('title') or item['id']}” needs one of: approve, needs changes, reject.")
        comment = comment.strip()
        if entry["decision"] in NEEDS_A_REASON and not comment:
            raise ValueError(f"Say what should change for “{item.get('title') or item['id']}”.")
        row = {"kind": item["kind"], "id": item["id"], "decision": entry["decision"], "comment": comment[:2000]}
        if item.get("revision"):
            row["revision"] = item["revision"]
        if item.get("images"):
            row["images"] = [{"path": image["path"], "sha256": image["sha256"]} for image in item["images"]]
        decision["items"].append(row)
    return decision


def record_decision(request, folder, payload):
    """Write the decision the owner sent, once: the single place a decision file comes from. Raises ValueError for a payload that is not a decision or when one
    was already recorded for this approval."""
    decision = build_decision(request, folder, payload)
    path = Path(folder) / "decision.json"
    if path.exists():
        raise ValueError("A decision was already sent for this approval.")
    common.validate_schema(decision, "gamearts-approval-decision")
    common.atomic_write_json(path, decision)
    return decision


# ------------------------------------------------------------------------------------------------ asking
def _summary(approval_id, outcome, decision, root, folder):
    rows = [{"kind": row["kind"], "id": row["id"], "revision": row.get("revision"), "decision": row["decision"], "comment": row.get("comment", "")}
            for row in (decision or {}).get("items", [])]
    return {"approval_id": approval_id, "outcome": outcome, "decisions": rows,
            "decision_file": (folder / "decision.json").relative_to(root).as_posix() if decision else None}


def ask(game_root, spec, timeout=DEFAULT_WAIT_SECONDS, print_link=False, opener=None, echo=None):
    """Show the owner `spec` in the form and wait for their decision. Returns the outcome: decided, deferred (they chose to decide later) or
    timed_out (nobody answered; nothing was recorded). Raises when no page could be shown, so a silence is never mistaken for an answer."""
    root = common.game_root(game_root)
    local_page.require_installed(TEMPLATE)
    request, folder = save_request(root, spec)
    session = Session(root, request, folder)
    if not local_page.show(session, timeout, print_link, opener, echo):
        return _summary(request["approval_id"], "timed_out", None, root, folder)
    return _summary(request["approval_id"], session.result["outcome"], session.result, root, folder)


def save_request(root, spec):
    """Check `spec`, give it an approval id and save it under the game; returns the saved request and its folder. Nothing is shown here."""
    root = common.game_root(root)
    request = prepare(root, spec)
    approval_id = new_id()
    folder = root / APPROVALS / approval_id
    request.update(approval_id=approval_id, created_at_utc=_now())
    common.validate_schema(request, "gamearts-approval-request")
    common.atomic_write_json(folder / "request.json", request)
    return request, folder


# ------------------------------------------------------------------------------------------------ using a decision
def _load(root, approval_id):
    folder = approval_folder(root, approval_id)
    request_file, decision_file = folder / "request.json", folder / "decision.json"
    if not request_file.is_file():
        raise ValueError(f"There is no approval {approval_id} in this game")
    if not decision_file.is_file():
        raise ValueError(f"Approval {approval_id} has no decision yet: the owner has not sent one")
    decision = common.validate_schema(common.read_json(decision_file), "gamearts-approval-decision")
    if decision["approval_id"] != approval_id:
        raise ValueError(f"The decision file of approval {approval_id} belongs to approval {decision['approval_id']}")
    if decision["request_sha256"] != common.sha256_file(request_file):
        raise ValueError(f"Approval {approval_id}: the request was changed after the owner decided, so the decision no longer matches what they were shown")
    if decision["outcome"] != "decided":
        raise ValueError(f"Approval {approval_id}: the owner chose to decide later; nothing in it approves anything")
    return decision


def _item(decision, kind, item_id, revision):
    for row in decision["items"]:
        if row["kind"] == kind and row["id"] == item_id and (revision is None or row.get("revision") == revision):
            return row
    wording = f"{kind} {item_id}" + (f" {revision}" if revision else "")
    raise ValueError(f"Approval {decision['approval_id']} does not ask about {wording}: the owner was shown something else")


CHOSE = {"approved": "approved", "changes": "needs changes", "rejected": "rejected"}
RECORDED_AS = {"approved": "Approved", "changes": "Asked for changes", "rejected": "Rejected"}


def reference(game_root, approval_id, kind, item_id, revision=None, expected="approved"):
    """The owner's decision on exactly this item, as the words recorded with the approval, or a ValueError saying why it is not what was asked for:
    no decision, a decision to wait, another item or revision, another choice than `expected` (approved unless a caller acts on a change or a
    rejection), or, for an approval, a picture that is not the one they were shown. A command that takes --approval-id calls this instead of
    being told what the owner said."""
    if expected not in DECISIONS:
        raise ValueError(f"expected must be one of {', '.join(DECISIONS)}")
    root = common.game_root(game_root)
    decision = _load(root, approval_id)
    row = _item(decision, kind, item_id, revision)
    wording = f"{kind} {item_id}" + (f" {row['revision']}" if row.get("revision") else "")
    if row["decision"] != expected:
        said = f": {row['comment']}" if row.get("comment") else ""
        refused = "approve" if expected == "approved" else f"choose {CHOSE[expected]} for"
        raise ValueError(f"The owner did not {refused} {wording} in approval {approval_id}; they chose {CHOSE[row['decision']]}{said}")
    for image in row.get("images", []) if expected == "approved" else []:
        path = common.safe_member(root, image["path"], "a picture path")
        if not path.is_file():
            raise ValueError(f"{image['path']} is no longer where the owner saw it; ask for a new approval of {wording}")
        if common.sha256_file(path) != image["sha256"]:
            raise ValueError(f"{image['path']} is not the picture the owner approved in approval {approval_id}; it changed afterwards, so ask again")
    said = f': "{row["comment"]}"' if row.get("comment") else ""
    return f"{RECORDED_AS[expected]} in the Game Arts approval form {approval_id} on {decision['decided_at_utc'][:10]}{said}"


def references(game_root, approval_id, items, expected="approved"):
    """The words for several (kind, id, revision) items at once, joined and without repeats. One item that is not as asked refuses them all."""
    if not items:
        raise ValueError("Name at least one item")
    return " | ".join(dict.fromkeys(reference(game_root, approval_id, kind, item_id, revision, expected) for kind, item_id, revision in items))


def item_spec(text):
    """`KIND:ID` or `KIND:ID:REVISION` as a command line names an item."""
    kind, _, rest = text.partition(":")
    item_id, _, revision = rest.partition(":")
    if kind not in KINDS or not item_id:
        raise argparse.ArgumentTypeError(f"use KIND:ID or KIND:ID:REVISION, with KIND one of {', '.join(KINDS)}")
    return kind, item_id, revision or None


def shown(game_root, approval_id, kind):
    """The (id, revision) pairs of one kind that the owner was shown in an approval, for a batch."""
    return [(row["id"], row.get("revision")) for row in _load(common.game_root(game_root), approval_id)["items"] if row["kind"] == kind]


def status(game_root, approval_id):
    folder = approval_folder(game_root, approval_id)
    if not (folder / "request.json").is_file():
        raise ValueError(f"There is no approval {approval_id} in this game")
    if not (folder / "decision.json").is_file():
        return {"approval_id": approval_id, "outcome": "pending", "decisions": [], "decision_file": None}
    decision = common.validate_schema(common.read_json(folder / "decision.json"), "gamearts-approval-decision")
    return _summary(approval_id, decision["outcome"], decision, common.game_root(game_root), folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ops = parser.add_subparsers(dest="operation", required=True)
    ask_parser = ops.add_parser("ask")
    ask_parser.add_argument("--request", type=Path, required=True, help="The request: see schemas/gamearts-approval-request.schema.json")
    ask_parser.add_argument("--timeout", type=float, default=DEFAULT_WAIT_SECONDS, help="Seconds to wait for the owner (default 1800)")
    ask_parser.add_argument("--print-link", action="store_true", help="Also print the secret address, for an owner who reaches this computer through a forwarded port")
    show_parser = ops.add_parser("show")
    show_parser.add_argument("--approval-id", required=True)
    reference_parser = ops.add_parser("reference", help="The owner's words for items decided as asked; nothing is printed unless every item is")
    reference_parser.add_argument("--approval-id", required=True)
    reference_parser.add_argument("--item", type=item_spec, action="append", required=True, metavar="KIND:ID[:REVISION]", help="An item the owner decided (repeatable)")
    reference_parser.add_argument("--decision", choices=DECISIONS, default="approved", help="The choice the items must have (default approved)")
    for sub in (ask_parser, show_parser, reference_parser):
        sub.add_argument("--game-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "reference":
            words = references(args.game_root, args.approval_id, args.item, args.decision)
            print(json.dumps({"approval_id": args.approval_id, "decision": args.decision, "reference": words}, indent=2))
            return 0
        if args.operation == "ask":
            result = ask(args.game_root, common.read_json(args.request), args.timeout, args.print_link)
        else:
            result = status(args.game_root, args.approval_id)
        print(json.dumps(result, indent=2))
        return 0 if args.operation == "show" or result["outcome"] == "decided" else 2  # asked and not decided: deferred or timed out
    except (OSError, ValueError, TypeError, KeyError) as exc:  # ValueError covers JSON, contract and path errors
        print("BLOCKED", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
