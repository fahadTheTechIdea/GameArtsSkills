#!/usr/bin/env python3
"""Opt-in Game Arts local updater for Claude Code + Codex (Python standard library).

Bootstrap once, from a trusted local copy of GameArtsSkills:
  python scripts/sync_local_agents.py bootstrap --source PATH_TO_GAME_ARTS --game-root PATH_TO_GAME
After you trust both tools' SessionStart hooks, they check the framework main
branch at the beginning of each local session. Network/offline failures never
claim a successful update. All personal game settings/assets are preserved.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

REPO = "https://github.com/fahadTheTechIdea/GameArtsSkills.git"
BRANCH = "main"
MASTER = "GAME_ARTS_MASTER_STANDARD_v7.7.md"
STATE = Path(".gamearts/system/agent-sync-state.json")
BEGIN = "<!-- GAMEARTS-SYNC-START -->"
END = "<!-- GAMEARTS-SYNC-END -->"
PREFIXES = (".agents/skills/", ".claude/skills/", "scripts/", "schemas/",
            "docs/", "godot/addons/gamearts/")
EXTS = (".md", ".py", ".json", ".gd", ".gdshader", ".tscn", ".yaml", ".yml")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atom(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".gamearts-pending")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def load_state(root):
    file = root / STATE
    if not file.is_file():
        return {"repository": REPO, "files": {}, "revision": None}
    state = json.loads(file.read_text(encoding="utf-8"))
    if state.get("repository") != REPO or not isinstance(state.get("files"), dict):
        raise ValueError("Existing sync state is invalid or from another repository")
    return state


def candidates(source):
    result = [Path(MASTER)]
    for dirname in PREFIXES:
        directory = source / dirname
        if directory.is_dir():
            result += [p.relative_to(source) for p in directory.rglob("*")
                       if p.is_file() and p.suffix in EXTS]
    for rel in result:
        p = source / rel
        if not p.is_file() or p.is_symlink():
            raise ValueError("Missing or unsafe framework file: " + str(rel))
    return sorted(set(result))


@contextmanager
def lock(root):
    path = root / ".gamearts/system/agent-sync.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Another Game Arts sync is running; try next session") from None
    try:
        with os.fdopen(fd, "w") as fp:
            fp.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def revision(source):
    try:
        r = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True, timeout=5)
        return r.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "trusted-local-source"


def managed_block(rev):
    return ("\n" + BEGIN + "\n"
            "Game Arts managed setup: for game-art work, apply the current "
            "\`GAME_ARTS_MASTER_STANDARD_v7.7.md\` and the "
            "\`.agents/skills/game-arts/SKILL.md\` (Codex) or "
            "\`.claude/skills/game-arts/SKILL.md\` (Claude Code). "
            "Use this game's saved settings, applicable instructions, approved "
            "mockups and generated/approved/revoked lifecycle. "
            "Both local agent skill trees are synced at session start when configured.\n"
            "Revision: " + rev + "\n" + END + "\n")


def merge_instructions(game, name, rev):
    path = game / name
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = managed_block(rev)
    if BEGIN in existing or END in existing:
        if existing.count(BEGIN) != 1 or existing.count(END) != 1:
            raise ValueError("Ambiguous Game Arts managed block in " + name)
        a, b = existing.index(BEGIN), existing.index(END) + len(END)
        result = existing[:a] + block.strip("\n") + existing[b:]
    else:
        result = existing.rstrip("\n") + block
    if existing != result:
        atom(path, result.encode("utf-8"))


def sync(source, game, *, adopt=False, rev=None):
    source, game = source.resolve(), game.resolve()
    if source == game or not (source / MASTER).is_file():
        raise ValueError("Source must be a separate complete GameArtsSkills checkout")
    if not game.is_dir():
        raise ValueError("Game project does not exist: " + str(game))
    state = load_state(game)
    tracked = dict(state["files"])
    changes = {"new": [], "updated": [], "conflicts": [], "unchanged": []}
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = game / ".gamearts/system/backups" / timestamp
    for rel in candidates(source):
        key = rel.as_posix()
        dest = game / rel
        raw = (source / rel).read_bytes()
        hash_new = sha(raw)
        if dest.is_symlink():
            changes["conflicts"].append(key + " (symlink)")
            continue
        if dest.exists():
            hash_current = sha(dest.read_bytes())
            if hash_current == hash_new:
                tracked[key] = hash_new
                changes["unchanged"].append(key)
                continue
            if tracked.get(key) != hash_current:
                if not adopt:
                    changes["conflicts"].append(key + " (local change or unowned file)")
                    continue
                preserved = backup / rel
                preserved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, preserved)
            changes["updated"].append(key)
        else:
            changes["new"].append(key)
        atom(dest, raw)
        tracked[key] = hash_new
    current_rev = rev or revision(source)
    for name in ("AGENTS.md", "CLAUDE.md"):
        try:
            merge_instructions(game, name, current_rev)
        except (ValueError, OSError) as exc:
            changes["conflicts"].append(name + ": " + str(exc))
    state.update({"repository": REPO, "branch": BRANCH, "revision": current_rev,
                  "files": tracked, "conflicts": changes["conflicts"],
                  "last_sync_utc": datetime.now(timezone.utc).isoformat()})
    atom(game / STATE, (json.dumps(state, indent=2) + "\n").encode("utf-8"))
    return changes


def hook_command(game):
    exe = game / "scripts/sync_local_agents.py"
    parts = [sys.executable, str(exe.resolve()), "update",
             "--game-root", str(game.resolve()), "--quiet"]
    return subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)


def install_hooks(game):
    command = hook_command(game)
    installed = []
    for relative in (".claude/settings.json", ".codex/hooks.json"):
        path = game / relative
        obj = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if not isinstance(obj, dict):
            raise ValueError("Invalid JSON settings at " + relative)
        hooks = obj.setdefault("hooks", {})
        sessions = hooks.setdefault("SessionStart", [])
        if not isinstance(hooks, dict) or not isinstance(sessions, list):
            raise ValueError("Existing SessionStart hook config invalid: " + relative)
        # Remove only prior Game Arts commands, retain third-party hooks.
        remaining = []
        for group in sessions:
            if not isinstance(group, dict):
                remaining.append(group)
                continue
            copy = dict(group)
            inner = group.get("hooks", [])
            copy["hooks"] = [handler for handler in inner
                             if not (isinstance(handler, dict)
                                     and "sync_local_agents.py" in str(handler.get("command", "")))]
            if copy["hooks"]:
                remaining.append(copy)
        remaining.append({"matcher": "startup|resume|clear|fork",
                          "hooks": [{"type": "command", "command": command,
                                     "timeout": 45,
                                     "statusMessage": "Game Arts local update check"}]})
        hooks["SessionStart"] = remaining
        atom(path, (json.dumps(obj, indent=2) + "\n").encode("utf-8"))
        installed.append(relative)
    return installed


def update(game):
    if not (game / STATE).is_file():
        raise ValueError("One-time trusted Game Arts bootstrap is required")
    with lock(game):
        with tempfile.TemporaryDirectory(prefix="gamearts-fetch-") as scratch:
            checkout = Path(scratch) / "GameArtsSkills"
            subprocess.run(["git", "clone", "--depth", "1", "--single-branch",
                            "--branch", BRANCH, REPO, str(checkout)],
                           check=True, timeout=35, capture_output=True, text=True)
            rev = revision(checkout)
            if not re.fullmatch("[0-9a-f]{40,64}", rev):
                raise ValueError("Fetched repository revision is unverified")
            state = load_state(game)
            if state.get("revision") == rev and not state.get("conflicts"):
                return {"revision": rev, "up_to_date": True, "conflicts": []}
            result = sync(checkout, game, rev=rev)
            result["revision"] = rev
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    first = subs.add_parser("bootstrap")
    first.add_argument("--source", type=Path, required=True)
    first.add_argument("--game-root", type=Path, required=True)
    first.add_argument("--adopt-existing", action="store_true",
                       help="Back up and update framework-path files already installed")
    upd = subs.add_parser("update")
    upd.add_argument("--game-root", type=Path, required=True)
    upd.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        game = args.game_root.expanduser().resolve()
        if args.mode == "bootstrap":
            with lock(game):
                result = sync(args.source.expanduser(), game, adopt=args.adopt_existing)
                result["hooks_installed"] = install_hooks(game)
            result["note"] = "Review and trust new hooks in Claude and Codex; auto-sync runs on session start."
        else:
            result = update(game)
        if not getattr(args, "quiet", False):
            print(json.dumps(result, indent=2))
        else:
            print("Game Arts sync " + ("up to date" if result.get("up_to_date")
                  else "updated to " + str(result["revision"]) + ", conflicts="
                  + str(len(result.get("conflicts", [])))))
        if result.get("conflicts"):
            print("Local modified/unowned framework files were preserved; check sync-state conflicts.", file=sys.stderr)
        return 0 if not result.get("conflicts") else 2
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, json.JSONDecodeError) as err:
        print("Game Arts local sync unavailable: " + str(err), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
