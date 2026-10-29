#!/usr/bin/env python3
"""Opt-in Game Arts local updater for Claude Code + Codex (Python standard library plus the framework's own helpers).

Bootstrap once, from a trusted local copy of GameArtsSkills:
  python scripts/sync_local_agents.py bootstrap --source PATH_TO_GAME_ARTS --game-root PATH_TO_GAME
After you trust the SessionStart hook in each tool, it checks the framework `main` branch at the start of a local session.
A failed or offline fetch never claims an update. Personal settings, instructions and artwork are never touched; a framework
file you edited is preserved and reported; a file removed upstream is removed from your game only if you never edited it.

Hook placement (researched 2026-10-23; Claude Code hooks reference, OpenAI Codex hooks documentation):
  local   (default) Claude -> .claude/settings.local.json, a personal file (added to .git/info/exclude so it is never committed;
          Claude Code itself ignores it only when it saves a setting there). Codex has no
          project-local personal hook file, so its entry goes to ~/.codex/hooks.json only with --codex-user-hook.
  project portable entries committed to .claude/settings.json and .codex/hooks.json: no absolute path, interpreter named by
          --python-command. Needs a POSIX-style shell on every machine that opens the game.
  none    install nothing.
Both tools make you review a new or changed hook before it runs (Codex stores trust against the hook's hash, `/hooks`).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402

REPO = "https://github.com/fahadTheTechIdea/GameArtsSkills.git"
BRANCH = "main"
MASTER = "GAME_ARTS_MASTER_STANDARD.md"
MASTER_GLOB = "GAME_ARTS_MASTER_STANDARD*.md"
STATE = Path(".gamearts/system/agent-sync-state.json")
BEGIN = "<!-- GAMEARTS-SYNC-START -->"
END = "<!-- GAMEARTS-SYNC-END -->"
PREFIXES = (".agents/skills/", ".claude/skills/", "scripts/", "schemas/", "docs/", "presets/")
EXTS = (".md", ".py", ".json", ".yaml", ".yml")
REQUIRED = (".claude/skills/game-arts/SKILL.md", ".agents/skills/game-arts/SKILL.md", "scripts/sync_local_agents.py")
OWNED_HOOK = "sync_local_agents.py"
HOOK_MATCHER = "startup|resume"


def master_name(root):
    """The master standard in `root`. A file under another name (the bridge that updaters installed before the rename look
    for) is ignored while the real master is present; otherwise there must be exactly one, whatever it is called."""
    found = sorted(p.name for p in Path(root).glob(MASTER_GLOB) if p.is_file())
    if MASTER in found:
        return MASTER
    if len(found) != 1:
        raise ValueError(f"Expected exactly one {MASTER_GLOB} in {root}, found {len(found)}")
    return found[0]


def load_state(root):
    file = root / STATE
    if not file.is_file():
        return {"repository": REPO, "files": {}, "pending": {}, "revision": None}
    state = json.loads(file.read_text(encoding="utf-8"))
    if state.get("repository") != REPO or not isinstance(state.get("files"), dict):
        raise ValueError("Existing sync state is invalid or from another repository")
    state.setdefault("pending", {})
    return state


def save_state(root, state):
    common.atomic_write_json(root / STATE, state)


def candidates(source):
    """Every framework file to install: the master plus the synced folders. An incomplete checkout is refused outright,
    because anything missing from it would otherwise look like a file removed upstream."""
    source = Path(source)
    for rel in REQUIRED:
        if not (source / rel).is_file():
            raise ValueError(f"Incomplete framework checkout: {rel} is missing; nothing was changed or removed")
    result = [Path(master_name(source))]
    for dirname in PREFIXES:
        directory = source / dirname
        if directory.is_dir():
            result += [p.relative_to(source) for p in directory.rglob("*") if p.is_file() and p.suffix in EXTS]
    for rel in result:
        p = source / rel
        if not p.is_file() or p.is_symlink():
            raise ValueError("Missing or unsafe framework file: " + str(rel))
    return sorted(set(result))


def lock(root):
    return common.file_lock(Path(root) / ".gamearts/system/agent-sync.lock", name="Game Arts sync")


def revision(source):
    try:
        r = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5)
        return r.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "trusted-local-source"  # a copied folder has no git history; the state records that honestly


def managed_block(rev, master):
    return ("\n" + BEGIN + "\n"
            f"Game Arts managed setup: for game-art work, apply the current `{master}` and the "
            "`.agents/skills/game-arts/SKILL.md` (Codex) or `.claude/skills/game-arts/SKILL.md` (Claude Code). "
            "Use this game's saved settings, applicable instructions, approved mockups and generated/approved/revoked "
            "lifecycle. Both local agent skill trees are synced at session start when configured.\n"
            "Revision: " + rev + "\n" + END + "\n")


def merge_instructions(game, name, rev, master):
    path = game / name
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = managed_block(rev, master)
    if BEGIN in existing or END in existing:
        if existing.count(BEGIN) != 1 or existing.count(END) != 1:
            raise ValueError("Ambiguous Game Arts managed block in " + name)
        a, b = existing.index(BEGIN), existing.index(END) + len(END)
        result = existing[:a] + block.strip("\n") + existing[b:]
    else:
        result = existing.rstrip("\n") + block
    if existing != result:
        common.atomic_write_bytes(path, result.encode("utf-8"))


def preserve(game, backup, rel):
    kept = backup / rel
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(game / rel, kept)


def prune_empty_parents(game, path):
    parent = path.parent
    while parent != game and common.inside(parent, game) and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def recover_pending(game, state):
    """A run that died between writing a file and recording it left `pending` entries: trust a file that holds exactly
    the content that was about to be written, so the next run does not report it as a local edit."""
    for key, expected in list(state["pending"].items()):
        target = game / key
        if target.is_file() and common.sha256_file(target) == expected:
            state["files"][key] = expected
        del state["pending"][key]


def sync(source, game, *, adopt=False, rev=None, source_verification="not_requested"):
    source, game = source.resolve(), common.game_root(game)
    if source == game:
        raise ValueError("Source must be a separate complete GameArtsSkills checkout")
    if not game.is_dir():
        raise ValueError("Game project does not exist: " + str(game))
    wanted = candidates(source)
    master = master_name(source)
    state = load_state(game)
    recover_pending(game, state)
    tracked = state["files"]
    changes = {"new": [], "updated": [], "removed": [], "kept_after_upstream_removal": [], "conflicts": [], "unchanged": []}
    backup = game / ".gamearts/system/backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    current_rev = rev or revision(source)
    completed = False
    try:
        for rel in wanted:
            key = rel.as_posix()
            dest = game / rel
            raw = (source / rel).read_bytes()
            hash_new = common.sha256_bytes(raw)
            if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                changes["conflicts"].append(key + " (symlink or non-file path)")
                continue
            if dest.exists():
                hash_current = common.sha256_file(dest)
                if hash_current == hash_new:
                    tracked[key] = hash_new
                    changes["unchanged"].append(key)
                    continue
                if tracked.get(key) != hash_current:
                    if not adopt:
                        changes["conflicts"].append(key + " (local change or unowned file)")
                        continue
                    preserve(game, backup, rel)
                changes["updated"].append(key)
            else:
                changes["new"].append(key)
            state["pending"][key] = hash_new  # written ahead, so a crash after the write is recognised next run
            save_state(game, state)
            common.atomic_write_bytes(dest, raw)
            tracked[key] = hash_new
            del state["pending"][key]
            save_state(game, state)
        # A file the framework no longer ships is removed only while it still equals what this updater installed.
        for key in sorted(set(tracked) - {rel.as_posix() for rel in wanted}):
            dest = game / key
            if not dest.exists():
                del tracked[key]
            elif dest.is_file() and not dest.is_symlink() and common.sha256_file(dest) == tracked[key]:
                preserve(game, backup, Path(key))
                dest.unlink()
                prune_empty_parents(game, dest)
                del tracked[key]
                changes["removed"].append(key)
            else:
                del tracked[key]  # edited by the user: it is theirs now; reported once, never deleted
                changes["kept_after_upstream_removal"].append(key)
        # One-time adoption also retires redundant prior master copies, always backing them up first.
        if adopt:
            for obsolete in game.glob(MASTER_GLOB):
                if obsolete.name == master or not obsolete.is_file() or obsolete.is_symlink():
                    continue
                preserve(game, backup, Path(obsolete.name))
                obsolete.unlink()
                tracked.pop(obsolete.name, None)
                changes["updated"].append(obsolete.name + " (retired with backup)")
        for name in ("AGENTS.md", "CLAUDE.md"):
            try:
                merge_instructions(game, name, current_rev, master)
            except (ValueError, OSError) as exc:
                changes["conflicts"].append(name + ": " + str(exc))
        completed = True
    finally:  # whatever completed is recorded; the revision only advances when the whole run did
        state.update({"repository": REPO, "branch": BRANCH, "conflicts": changes["conflicts"]})
        if completed:
            state.update({"revision": current_rev, "source_verification": source_verification,
                          "last_sync_utc": datetime.now(timezone.utc).isoformat()})
        save_state(game, state)
    return changes


# ---------------------------------------------------------------------------------------------------- hooks
def quote(part):
    if any(ch in part for ch in '"$`'):
        raise ValueError(f"Cannot put this path in a hook command (it contains a quote, $ or backtick): {part}")
    return f'"{part}"'


def local_command(game, require_signed):
    """Machine-specific command (absolute interpreter and paths); only ever written to a personal, uncommitted file."""
    interpreter = quote(Path(sys.executable).as_posix())
    script = quote((game / "scripts" / OWNED_HOOK).resolve().as_posix())
    root = quote(game.resolve().as_posix())
    return f"{interpreter} {script} update --game-root {root} --quiet" + (" --require-signed" if require_signed else "")


def project_commands(python_command, require_signed):
    """Portable commands for committed files: nothing machine-specific, paths resolved by each tool's own mechanism."""
    tail = " --quiet" + (" --require-signed" if require_signed else "")
    claude = f'{python_command} "$CLAUDE_PROJECT_DIR/scripts/{OWNED_HOOK}" update --game-root "$CLAUDE_PROJECT_DIR"{tail}'
    codex = (f'{python_command} "$(git rev-parse --show-toplevel)/scripts/{OWNED_HOOK}" update '
             f'--game-root "$(git rev-parse --show-toplevel)"{tail}')
    return claude, codex


def edit_hook_file(path, command):
    """Set (or, for None, remove) this updater's SessionStart entry in a hooks/settings file, keeping every other entry.
    Returns True when the file changed."""
    if not path.is_file() and command is None:
        return False
    obj = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(obj, dict):
        raise ValueError(f"Invalid JSON settings at {path.name}")
    hooks = obj.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"Existing hooks config must be an object: {path.name}")
    sessions = hooks.get("SessionStart", [])
    if not isinstance(sessions, list):
        raise ValueError(f"Existing SessionStart hook config invalid: {path.name}")
    owned = any(OWNED_HOOK in str(h.get("command", "")) for g in sessions if isinstance(g, dict)
                for h in g.get("hooks", []) if isinstance(h, dict))
    if command is None and not owned:
        return False  # nothing of ours to remove: leave the user's file exactly as it is
    before = json.dumps(obj, sort_keys=True)
    obj["hooks"] = hooks
    remaining = []
    for group in sessions:  # drop only this updater's handler, retain third-party hooks
        if not isinstance(group, dict):
            remaining.append(group)
            continue
        copy = dict(group)
        copy["hooks"] = [h for h in group.get("hooks", []) if not (isinstance(h, dict) and OWNED_HOOK in str(h.get("command", "")))]
        if copy["hooks"]:
            remaining.append(copy)
    if command is not None:
        remaining.append({"matcher": HOOK_MATCHER, "hooks": [{"type": "command", "command": command, "timeout": 45,
                                                              "statusMessage": "Game Arts local update check"}]})
    hooks["SessionStart"] = remaining
    if not remaining:
        del hooks["SessionStart"]
    if not hooks:
        del obj["hooks"]
    if json.dumps(obj, sort_keys=True) == before:
        return False
    common.atomic_write_json(path, obj)
    return True


def keep_out_of_git(game, relative):
    """A personal hook file must not be committed. Claude Code ignores `.claude/settings.local.json` only when IT saves a
    setting there, so a file written by this updater is added to the repository's local `.git/info/exclude` (uncommitted,
    never the project's `.gitignore`). Returns a note when that is not possible, else None."""
    git_dir = game / ".git"
    if not git_dir.is_dir():
        return f"{relative} is personal to this machine: keep it out of version control (this folder has no .git directory to exclude it automatically)."
    exclude = git_dir / "info" / "exclude"
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if relative not in existing.splitlines():
        common.atomic_write_bytes(exclude, (existing.rstrip("\n") + ("\n" if existing else "") + relative + "\n").encode("utf-8"))
    return None


def install_hooks(game, scope="local", *, python_command="python3", require_signed=False, codex_user_hook=False, home=None):
    """Place the session-start hook where `scope` says; remove this updater's entries from every other game-level file."""
    if scope not in ("local", "project", "none"):
        raise ValueError("hooks scope must be local, project or none")
    game = common.game_root(game)
    home = Path(home) if home else Path.home()
    claude_local, claude_project = game / ".claude/settings.local.json", game / ".claude/settings.json"
    codex_project, codex_user = game / ".codex/hooks.json", home / ".codex/hooks.json"
    wanted = {claude_local: None, claude_project: None, codex_project: None, codex_user: None}
    notes = []
    if scope == "local":
        command = local_command(game, require_signed)
        wanted[claude_local] = command
        if codex_user_hook:
            wanted[codex_user] = command
        else:
            notes.append("Codex: no hook installed. Codex has no project-local personal hook file; rerun with "
                         "--codex-user-hook to add it to ~/.codex/hooks.json, or use --hooks project.")
    elif scope == "project":
        claude, codex = project_commands(python_command, require_signed)
        wanted[claude_project], wanted[codex_project] = claude, codex
    changed = []
    for path, command in wanted.items():
        if path == codex_user and not codex_user_hook:
            continue  # a user-level file outside the game is touched only when explicitly asked for
        if edit_hook_file(path, command):
            changed.append(path)
    if wanted[claude_local] is not None:
        note = keep_out_of_git(game, ".claude/settings.local.json")
        if note:
            notes.append(note)
    return {"scope": scope, "changed": [str(p) for p in changed], "notes": notes,
            "review": "Claude Code and Codex ask you to review and trust a new or changed hook before it runs."}


# ---------------------------------------------------------------------------------------------------- update
def fetch_main(scratch):
    """Clone the framework's `main` branch into `scratch`; returns (checkout path, commit id). The only network step."""
    checkout = Path(scratch) / "GameArtsSkills"
    subprocess.run(["git", "clone", "--depth", "1", "--single-branch", "--branch", BRANCH, REPO, str(checkout)],
                   check=True, timeout=35, capture_output=True, text=True)
    return checkout, revision(checkout)


def verify_signature(checkout):
    """Require a valid signature on the fetched commit (`git verify-commit`); needs the signer's key configured locally."""
    try:
        subprocess.run(["git", "-C", str(checkout), "verify-commit", "HEAD"], check=True, timeout=20, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError("The fetched framework commit has no valid signature; nothing was changed. "
                         + (exc.stderr or "").strip()) from exc
    return "signature_verified"


def update(game, fetcher=fetch_main, require_signed=False):
    if not (game / STATE).is_file():
        raise ValueError("One-time trusted Game Arts bootstrap is required")
    with lock(game):
        with tempfile.TemporaryDirectory(prefix="gamearts-fetch-") as scratch:
            checkout, rev = fetcher(scratch)
            if not re.fullmatch("[0-9a-f]{40,64}", rev):
                raise ValueError("Fetched repository revision is unverified")
            verification = verify_signature(checkout) if require_signed else "not_requested"
            state = load_state(game)
            if state.get("revision") == rev and not state.get("conflicts") and not state.get("pending"):
                return {"revision": rev, "up_to_date": True, "conflicts": [], "source_verification": verification}
            result = sync(checkout, game, rev=rev, source_verification=verification)
            result["revision"] = rev
            result["source_verification"] = verification
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="mode", required=True)
    first = subs.add_parser("bootstrap")
    first.add_argument("--source", type=Path, required=True)
    first.add_argument("--game-root", type=Path, required=True)
    first.add_argument("--adopt-existing", action="store_true", help="Back up and update framework-path files already installed")
    first.add_argument("--hooks", choices=("local", "project", "none"), default="local")
    first.add_argument("--codex-user-hook", action="store_true", help="Also add the hook to ~/.codex/hooks.json (local scope)")
    first.add_argument("--python-command", default="python3", help="Interpreter name written to committed (project) hooks")
    first.add_argument("--require-signed", action="store_true", help="Update only to commits with a valid signature")
    upd = subs.add_parser("update")
    upd.add_argument("--game-root", type=Path, required=True)
    upd.add_argument("--quiet", action="store_true")
    upd.add_argument("--require-signed", action="store_true")
    args = parser.parse_args()
    try:
        game = common.game_root(args.game_root.expanduser())
        if not game.is_dir():
            raise ValueError("Game project does not exist: " + str(game))
        if args.mode == "bootstrap":
            with lock(game):
                result = sync(args.source.expanduser(), game, adopt=args.adopt_existing)
            result["hooks"] = install_hooks(game, args.hooks, python_command=args.python_command,
                                            require_signed=args.require_signed, codex_user_hook=args.codex_user_hook)
            # locks, manifest backups and scratch drafts live in .gamearts/system/ and never belong in the game's history
            result["system_folder"] = keep_out_of_git(game, ".gamearts/system/") or "excluded from git through .git/info/exclude"
        else:
            result = update(game, require_signed=args.require_signed)
        if not getattr(args, "quiet", False):
            print(json.dumps(result, indent=2))
        else:
            print("Game Arts sync " + ("up to date" if result.get("up_to_date")
                  else "updated to " + str(result["revision"]) + ", conflicts=" + str(len(result.get("conflicts", [])))))
        if result.get("conflicts"):
            print("Local modified/unowned framework files were preserved; check sync-state conflicts.", file=sys.stderr)
        return 0 if not result.get("conflicts") else 2
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as err:  # json.JSONDecodeError is a ValueError
        print("Game Arts local sync unavailable: " + str(err), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
