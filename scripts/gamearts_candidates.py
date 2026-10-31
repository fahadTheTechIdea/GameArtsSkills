#!/usr/bin/env python3
"""The record of every picture an image tool returns for a sprite strip, grid, turnaround or edit. The owner of the automatic check that follows every generation.

  record   python scripts/gamearts_candidates.py record --game-root GAME --image PIC --group NAME --frames N [--columns C] [--facing E] [--action clap]
                  --prompt-file PROMPT.txt --generated-with "the tool" [--ref ROLE=PATH ...] [--reference NEUTRAL.png --neutral-ends --crown 30 --planted]
  reject   python scripts/gamearts_candidates.py reject --game-root GAME --candidate-id ID --reason "too close to a side profile"
  review   python scripts/gamearts_candidates.py review --game-root GAME --candidate-id ID --reviewer agent --compared-with turnaround=art/turnaround.png [--compared-with ...]
                  --finding "facing=pass:only the back of the head and the heels show" --finding "elevation=pass:..." --finding "identity=pass:..." --finding "motion=pass:..."
                  [--flags-explained "why each measured flag is not a mismatch"]
  select   python scripts/gamearts_candidates.py select --game-root GAME --candidate-id ID [--note "..."]
  list     python scripts/gamearts_candidates.py list --game-root GAME [--group NAME]

Run `record` on every picture the moment the tool returns it, before anyone is shown it, and never wait to be asked. It does three things:
1. Keeps the picture unchanged (the original name and hash too) with the prompt that made it, the pictures the tool was given (role, path, hash), what the tool
   was, the size and how much of it is transparent or exact key, under `.gamearts/outputs/candidates/<group>-vNNN/`. A picture is never overwritten.
2. Runs the measured check of `slice_generated_strip.py` (gutters, a figure touching the edge, one scale, neutral ends, head width, planted feet) and stores
   what it measured or why it refused.
3. A picture the check refuses is recorded as rejected, with the measurement as the reason: exit code 3 says so. A picture that passes stays `generated`
   until a person selects or rejects it: `reject` needs a reason, `select` supersedes the group's earlier selection and keeps it. Nothing is deleted.
4. A picture that passes the measurements is then REVIEWED, by looking at it beside the approved pictures it must match (open both as images): `review` records, for
   the facing, the camera elevation, the identity and the motion, a verdict (pass, fail, or for motion not_applicable) with the reason in words, the pictures it was
   compared with (path and hash) and the hash of the candidate it judged. A failing finding rejects the candidate with those reasons. `select` needs a passing review
   of this exact file, and when the measurements raised flags (colour, proportions, top lighting) the review has to explain them. The record cannot prove the
   reviewer looked, only what they wrote and what they compared; the owner still approves the selected picture.
This is how the football project keeps every candidate ("rejected for integration: ...", unselected ones kept with their reasons).
The measurements never judge whether the facing or the figure is right; they only flag likely differences. The review does that.
"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import gamearts_common as common
import slice_generated_strip as slicer

STORE = Path(".gamearts") / "outputs" / "candidates"
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ROLE = re.compile(r"^[a-z][a-z-]*$")
REFUSED = 3
ASPECTS = ("facing", "elevation", "identity", "motion")
VERDICTS = ("pass", "fail", "not_applicable")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _game(game_root):
    """The game's folder, which must already hold its saved settings: a mistyped path never creates a new game's art folders."""
    root = common.game_root(game_root)
    if not (root / ".gamearts" / "project.json").is_file():
        raise ValueError(f"{root} has no .gamearts/project.json, so it is not a set-up game: pass the game's own folder as --game-root")
    return root


def _folder(root, candidate_id):
    if not isinstance(candidate_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*-v[0-9]{3}", candidate_id):
        raise ValueError(f"{candidate_id!r} is not a candidate id (the group name, then -v and three digits)")
    return common.safe_member(root / STORE, candidate_id, "the candidate id")


def _load(root, candidate_id):
    path = _folder(root, candidate_id) / "candidate.json"
    if not path.is_file():
        raise ValueError(f"there is no candidate {candidate_id}")
    record = common.read_json(path)
    common.validate_schema(record, "gamearts-candidate")
    return record, path


def _save(path, record):
    common.validate_schema(record, "gamearts-candidate")
    common.atomic_write_json(path, record)


def _facts(image):
    """Size and how much of the picture is background: fully transparent when it has alpha, exact key when it does not."""
    width, height = image.size
    total = width * height
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return {"width": width, "height": height, "transparent_fraction": round(alpha.histogram()[0] / total, 4)}
    return {"width": width, "height": height, "exact_key_fraction": round(1 - common.nonkey_mask(image).histogram()[255] / total, 4)}


def _revision(root, group):
    store = root / STORE
    taken = [int(match.group(1)) for path in (store.iterdir() if store.is_dir() else ()) for match in [re.fullmatch(re.escape(group) + r"-v([0-9]{3})", path.name)] if match]
    return max(taken, default=0) + 1


def record(game_root, image, group, frames, columns=None, facing=None, action=None, prompt_file=None, generated_with=None, refs=(), reference=None,
           planted=False, tolerance=0.05, neutral_ends=False, crown=None, crown_tolerance=slicer.CROWN_TOLERANCE):
    """Keep the picture, run the measured check and write the record. Returns the record; a refused picture is stored as rejected, not raised."""
    from PIL import Image
    root = _game(game_root)
    if not isinstance(group, str) or not NAME.fullmatch(group):
        raise ValueError("the group is a lowercase name of letters, digits, dots, dashes and underscores (for example oilco-tanker-e-clap)")
    if facing is not None and not re.fullmatch(r"[A-Z]{1,2}", facing):
        raise ValueError("the facing is a direction such as E, SE or N")
    if not isinstance(generated_with, str) or not generated_with.strip():
        raise ValueError("say what produced the picture (--generated-with): the record must name the tool, never assume it")
    image = Path(image)
    if not image.is_file():
        raise ValueError(f"the picture {image} does not exist")
    if not prompt_file or not Path(prompt_file).is_file():
        raise ValueError("--prompt-file must name the file holding the prompt that was actually sent to the tool")
    prompt = Path(prompt_file).read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError("the prompt file is empty: a candidate without the prompt that made it cannot be repeated or judged")
    references = []
    for item in refs:
        role, separator, path = item.partition("=")
        if not separator or not ROLE.fullmatch(role):
            raise ValueError(f"--ref must be ROLE=PATH (for example turnaround=art/turnaround.png), not {item!r}")
        full = common.safe_member(root, path, f"the {role} picture")
        if not full.is_file():
            raise ValueError(f"the {role} picture {path!r} does not exist inside the game")
        references.append({"role": role, "path": Path(path).as_posix(), "sha256": common.sha256_file(full)})
    reference_path = common.safe_member(root, reference, "the reference picture") if reference else None
    with Image.open(image) as opened:
        if opened.format != "PNG":
            raise ValueError(f"the tool's picture must be a PNG, this is {opened.format}: have the tool save a PNG")
        picture = opened.convert("RGBA")
    revision = _revision(root, group)
    candidate_id = f"{group}-v{revision:03d}"
    folder = _folder(root, candidate_id)
    parameters = {"frames": frames, "columns": columns or frames, "planted": planted, "tolerance": tolerance, "neutral_ends": neutral_ends, "crown": crown,
                  **({"reference": Path(reference).as_posix()} if reference else {})}
    try:
        measured = slicer.slice_strip(image, frames, columns, reference_path, planted, tolerance, neutral_ends, crown, crown_tolerance)
        check = {"status": "passed", "parameters": parameters, "warnings": measured["warnings"], "scale": measured["scale"], "match": measured["match"], "match_flags": measured["match_flags"],
                 "measured": [{key: figure[key] for key in ("index", "size", "root_x", "crown") if key in figure} for figure in measured["frames"]]}
    except ValueError as exc:  # the refusal is the finding, kept as the reason the picture was rejected
        check = {"status": "refused", "parameters": parameters, "refusal": str(exc)}
    folder.mkdir(parents=True, exist_ok=False)
    stored = f"{candidate_id}.png"
    shutil.copyfile(image, folder / stored)
    original_hash = common.sha256_file(image)
    body = {"schema_version": "1.0", "candidate_id": candidate_id, "group": group, "revision": revision, "status": "generated", **({"facing": facing} if facing else {}),
            **({"action": action} if action else {}), "file": (STORE / candidate_id / stored).as_posix(), "sha256": common.sha256_file(folder / stored), "original_name": image.name,
            "original_sha256": original_hash, **_facts(picture), "prompt": prompt, "prompt_sha256": common.sha256_bytes(prompt.encode("utf-8")), "generated_with": generated_with.strip(),
            "references": references, "check": check, "created_at_utc": _now()}
    if check["status"] == "refused":
        body["status"] = "rejected"
        body["rejection"] = {"reason": check["refusal"], "by": "automatic check", "at_utc": _now()}
    _save(folder / "candidate.json", body)
    return body


def reject(game_root, candidate_id, reason):
    """A person's judgement that the picture is wrong (the facing, the figure, the camera), with the reason. The picture and its record stay."""
    root = _game(game_root)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("say why the picture is rejected: a rejection without a reason cannot be learned from")
    body, path = _load(root, candidate_id)
    if body["status"] not in ("generated", "selected"):
        raise ValueError(f"{candidate_id} is {body['status']}, so it cannot be rejected again")
    body["status"] = "rejected"
    body["rejection"] = {"reason": reason.strip(), "by": "judgement", "at_utc": _now()}
    body.pop("selection", None)
    _save(path, body)
    return body


def _compared(root, items):
    found = []
    for item in items:
        role, separator, path = item.partition("=")
        if not separator or not ROLE.fullmatch(role):
            raise ValueError(f"--compared-with must be ROLE=PATH (for example turnaround=art/turnaround.png), not {item!r}")
        full = common.safe_member(root, path, f"the {role} picture")
        if not full.is_file():
            raise ValueError(f"the {role} picture {path!r} does not exist inside the game, so it cannot have been compared")
        found.append({"role": role, "path": Path(path).as_posix(), "sha256": common.sha256_file(full)})
    if not found:
        raise ValueError("name the approved picture(s) the candidate was compared with (--compared-with ROLE=PATH): a review without one is not a comparison")
    return found


def _findings(items):
    findings = {}
    for item in items:
        name, separator, rest = item.partition("=")
        verdict, colon, reason = rest.partition(":")
        if not separator or not colon or name not in ASPECTS or verdict not in VERDICTS or not reason.strip() or name in findings:
            raise ValueError(f"--finding must be ASPECT=VERDICT:reason once per aspect, ASPECT one of {', '.join(ASPECTS)} and VERDICT one of {', '.join(VERDICTS)}, with the reason in words, not {item!r}")
        if verdict == "not_applicable" and name != "motion":
            raise ValueError(f"{name} cannot be not_applicable: the facing, the elevation and the identity of every picture can be compared")
        findings[name] = {"verdict": verdict, "reason": reason.strip()}
    missing = [name for name in ASPECTS if name not in findings]
    if missing:
        raise ValueError(f"a review judges all four aspects; missing: {', '.join(missing)}")
    return findings


def review(game_root, candidate_id, reviewer, compared_with, findings, flags_explained=""):
    """A reviewer's comparison of the candidate with the approved pictures it must match: facing, camera elevation, identity and motion, each with its reason.
    A failing finding rejects the candidate. A pass is the only thing `select` accepts, and only for the exact file that was judged."""
    root = _game(game_root)
    if reviewer not in ("agent", "owner"):
        raise ValueError("the reviewer is agent or owner")
    body, path = _load(root, candidate_id)
    if body["status"] != "generated":
        raise ValueError(f"{candidate_id} is {body['status']}: only a generated picture is reviewed")
    if common.sha256_file(root / body["file"]) != body["sha256"]:
        raise ValueError(f"{candidate_id}'s picture no longer matches the hash recorded when it was kept; it was changed after it was generated")
    judged = _findings(findings)
    flags = body["check"].get("match_flags") or []
    failed = [name for name in ASPECTS if judged[name]["verdict"] == "fail"]
    explained = (flags_explained or "").strip()
    if flags and not failed and not explained:
        raise ValueError("the measurements flagged differences from the reference (" + "; ".join(flags) + "): explain them in --flags-explained, or fail the aspect they show")
    entry = {"reviewer": reviewer, "at_utc": _now(), "candidate_sha256": body["sha256"], "compared_with": _compared(root, compared_with), "findings": judged,
             **({"flags_explained": explained} if explained else {}), "overall": "fail" if failed else "pass"}
    body.setdefault("reviews", []).append(entry)
    if failed:
        body["status"] = "rejected"
        body["rejection"] = {"reason": "; ".join(f"{name}: {judged[name]['reason']}" for name in failed), "by": "review", "at_utc": _now()}
    _save(path, body)
    return body


def select(game_root, candidate_id, note=""):
    """The one picture of its group that production uses. A picture the check refused is already stored as rejected, so it cannot be selected; the earlier selection is kept as superseded."""
    root = _game(game_root)
    body, path = _load(root, candidate_id)
    if body["status"] != "generated":
        raise ValueError(f"{candidate_id} is {body['status']}: only a generated picture can be selected")
    latest = (body.get("reviews") or [None])[-1]  # a failing review rejects the picture, so a generated one has either no review or a passing one
    if latest is None:
        raise ValueError(f"{candidate_id} has no passing review: compare it with the approved pictures (review) before it is selected")
    if latest["candidate_sha256"] != common.sha256_file(root / body["file"]):
        raise ValueError(f"{candidate_id}'s picture changed after its review; review it again")
    for other in _group(root, body["group"]):
        if other["status"] == "selected":
            earlier, earlier_path = _load(root, other["candidate_id"])
            earlier["status"] = "superseded"
            earlier["selection"] = {**earlier["selection"], "superseded_by": candidate_id}
            _save(earlier_path, earlier)
    body["status"] = "selected"
    body["selection"] = {"note": note.strip() if isinstance(note, str) else "", "at_utc": _now()}
    _save(path, body)
    return body


def _group(root, group):
    store = root / STORE
    found = []
    for folder in sorted(store.iterdir()) if store.is_dir() else ():
        if re.fullmatch(re.escape(group) + r"-v[0-9]{3}", folder.name) and (folder / "candidate.json").is_file():
            found.append(common.read_json(folder / "candidate.json"))
    return found


def listing(game_root, group=None):
    root = _game(game_root)
    store = root / STORE
    rows = []
    for folder in sorted(store.iterdir()) if store.is_dir() else ():
        if (folder / "candidate.json").is_file():
            body = common.read_json(folder / "candidate.json")
            if group is None or body["group"] == group:
                rows.append({key: body[key] for key in ("candidate_id", "status", "facing", "action", "file", "width", "height") if key in body}
                            | {"check": body["check"]["status"], "reason": (body.get("rejection") or {}).get("reason")})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="op", required=True)
    one = sub.add_parser("record", help="Keep a generated picture and run the check, now")
    one.add_argument("--game-root", type=Path, required=True)
    one.add_argument("--image", type=Path, required=True, help="The PNG the tool returned (it is copied; the original stays where the tool saved it)")
    one.add_argument("--group", required=True, help="Which strip this is a candidate for, such as oilco-tanker-e-clap; revisions are numbered inside it")
    one.add_argument("--frames", type=int, required=True)
    one.add_argument("--columns", type=int)
    one.add_argument("--facing")
    one.add_argument("--action")
    one.add_argument("--prompt-file", type=Path, required=True, help="The file holding the prompt that was actually sent")
    one.add_argument("--generated-with", required=True, help="What produced the picture, in words")
    one.add_argument("--ref", action="append", default=[], help="A picture the tool was given: ROLE=PATH inside the game; repeat for each")
    one.add_argument("--reference", help="One approved pose of the same figure inside the game, to measure the scale")
    one.add_argument("--planted", action="store_true")
    one.add_argument("--neutral-ends", action="store_true")
    one.add_argument("--crown", type=int)
    one.add_argument("--tolerance", type=float, default=0.05)
    one.add_argument("--crown-tolerance", type=float, default=slicer.CROWN_TOLERANCE)
    rev = sub.add_parser("review", help="Record the comparison of a picture with the approved pictures it must match")
    rev.add_argument("--game-root", type=Path, required=True)
    rev.add_argument("--candidate-id", required=True)
    rev.add_argument("--reviewer", required=True, choices=("agent", "owner"))
    rev.add_argument("--compared-with", action="append", default=[], help="An approved picture the candidate was compared with: ROLE=PATH inside the game; repeat for each")
    rev.add_argument("--finding", action="append", default=[], help="ASPECT=VERDICT:reason, once each for facing, elevation, identity and motion (motion may be not_applicable)")
    rev.add_argument("--flags-explained", default="", help="Why the measured flags are not a mismatch (needed when the measurements raised flags)")
    two = sub.add_parser("reject", help="Reject a picture with a reason")
    two.add_argument("--game-root", type=Path, required=True)
    two.add_argument("--candidate-id", required=True)
    two.add_argument("--reason", required=True)
    three = sub.add_parser("select", help="Select the picture production uses")
    three.add_argument("--game-root", type=Path, required=True)
    three.add_argument("--candidate-id", required=True)
    three.add_argument("--note", default="")
    four = sub.add_parser("list", help="Every candidate, with its status and reason")
    four.add_argument("--game-root", type=Path, required=True)
    four.add_argument("--group")
    args = parser.parse_args(argv)
    try:
        if args.op == "record":
            result = record(args.game_root, args.image, args.group, args.frames, args.columns, args.facing, args.action, args.prompt_file, args.generated_with, args.ref, args.reference,
                            args.planted, args.tolerance, args.neutral_ends, args.crown, args.crown_tolerance)
            refused = result["check"]["status"] == "refused"
            print(json.dumps({"candidate_id": result["candidate_id"], "status": result["status"], "check": result["check"], "file": result["file"],
                              "next": ("rejected by the check: say what it measured, then ask the tool again or repair the picture (respace, repair, fix); this candidate stays on record" if refused
                                       else "passed the measurements: now open the picture and the approved pictures it must match as images and run `review` (facing, camera elevation, identity, motion), then select it"),
                              "match_flags": result["check"].get("match_flags") or [],
                              "not_assessed": ["whether the picture shows the right facing, the same camera elevation and the same figure: that is the review, not the measurements"]}, indent=2))
            return REFUSED if refused else 0
        if args.op == "review":
            result = review(args.game_root, args.candidate_id, args.reviewer, args.compared_with, args.finding, args.flags_explained)
            print(json.dumps({"candidate_id": result["candidate_id"], "status": result["status"], "overall": result["reviews"][-1]["overall"],
                              "next": ("rejected by the review: ask the tool again or repair the picture, keeping this one on record" if result["status"] == "rejected"
                                       else "the review passed: select it, then show the owner the picture beside the turnaround for approval")}, indent=2))
            return REFUSED if result["status"] == "rejected" else 0
        if args.op == "reject":
            result = reject(args.game_root, args.candidate_id, args.reason)
        elif args.op == "select":
            result = select(args.game_root, args.candidate_id, args.note)
        else:
            result = listing(args.game_root, args.group)
    except (ValueError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result if args.op == "list" else {"candidate_id": result["candidate_id"], "status": result["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
