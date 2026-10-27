#!/usr/bin/env python3
"""FROZEN, trimmed copy of the updater that enrolled games already run (its install path: state, candidates, sync; the hook
installer, fetch and CLI are omitted). It is the version published before the updater was hardened.

Do not edit and do not use it for new work: tests/test_sync_local_agents.py runs it against the CURRENT framework tree to prove
the new tree is still installable by the old updater (it requires the master file name below, so renaming the master before
every enrolled game has taken the new updater would strand them).
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
            "`GAME_ARTS_MASTER_STANDARD_v7.7.md` and the "
            "`.agents/skills/game-arts/SKILL.md` (Codex) or "
            "`.claude/skills/game-arts/SKILL.md` (Claude Code). "
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
        if dest.is_symlink() or (dest.exists() and not dest.is_file()):
            changes["conflicts"].append(key + " (symlink or non-file path)")
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
    # One-time adoption also retires redundant prior framework master copies,
    # always backing them up first. Routine updates never delete user files.
    if adopt:
        for obsolete in game.glob("GAME_ARTS_MASTER_STANDARD_v7.*.md"):
            if obsolete.name == MASTER or not obsolete.is_file() or obsolete.is_symlink():
                continue
            preserved = backup / obsolete.name
            preserved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(obsolete, preserved)
            obsolete.unlink()
            changes["updated"].append(obsolete.name + " (retired with backup)")
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
