# Installing Game Arts in a game project

This is a **folder tree**, not a ZIP. Copy it into the root of your game repository, keeping the hidden folders.

## What to copy
| Item | Why |
|---|---|
| `CLAUDE.md` and/or `AGENTS.md` | Project-root guidance the agent loads automatically (Claude Code reads `CLAUDE.md`, Codex reads `AGENTS.md`). If the game already has one, add the framework's section instead of replacing yours. |
| `.claude/skills/` and `.agents/skills/` | The focused skills (the two folders hold the same text). Copy the one your tool uses, or both. |
| `GAME_ARTS_MASTER_STANDARD.md` | The single authoritative standard. (Do not copy the small pointer file under the old versioned name; it exists only for updaters installed earlier.) |
| `scripts/`, `schemas/`, `presets/` | The helper scripts, the contracts they enforce, and the ready-made looks and engine profiles (validated data) the setup offers. Copy them together; a script without its schema refuses to run. |
| `docs/` | Job formats and the user guides. |

Game-specific files are created later, inside the **game** (never in this framework): `.gamearts/project.json`, `.gamearts/instructions/`, `.gamearts/storyboard/`, `.gamearts/outputs/` and `.gamearts/system/` (locks and backups; keep it out of version control).

## Requirements
- Python 3.11 or newer on the machine the agent runs on (run locally on 3.12 and 3.14; the CI matrix adds 3.11).
- **Pillow** and **`jsonschema`**: `python -m pip install Pillow jsonschema`. A missing `jsonschema` is a hard failure (a skipped contract check would be reported as a pass), so install both.
- An image-generation tool available to the agent, which you choose once per game (Codex's built-in image tool, its command-line fallback, a connector you name, or your own pictures). Without one the agent can still plan, import your mockups, build sheets from frames you provide and run every check, but it will say it cannot render art.
- Git is needed only for the optional updater.

The agent runs the scripts itself; you never type them. If something is missing (a package, an interpreter, a writable folder) it runs a read-only check, `scripts/gamearts_doctor.py`, and tells you the exact fix.

## Claude Code
`CLAUDE.md` is the project-root guidance; `.claude/skills/<name>/SKILL.md` are the discoverable skills. To share across all your repositories on one machine, copy the skill folders under `~/.claude/skills/`; for a team, commit the project files.

## Codex
`AGENTS.md` is the root guidance; `.agents/skills/<name>/SKILL.md` is the matching skill layout. Commit them. A skill is selected by its description; the root instruction sends art requests to `game-arts`.

## First use
Open the game in the agent and ask for art, or say **"Set up Game Arts for this game."** Settings are saved to `.gamearts/project.json` after you confirm them (`settings_status: "owner_confirmed"`); mockups cannot be registered before that. Commit the file so teammates and later sessions reuse it. More: [project settings](docs/PROJECT_SETTINGS.md), [commands](docs/COMMANDS.md), [workflow](docs/USER_WORKFLOW.md).

## Keeping both agents current (optional, opt-in)
[`scripts/sync_local_agents.py`](scripts/sync_local_agents.py) installs a session-start hook so each trusted Claude Code or Codex session checks the framework's `main` branch and updates both agents' skills, the master, scripts, schemas and docs in the game. Your settings, instructions, storyboard, outputs and unrelated files are never touched.

Ask a locally connected agent: **"Enable automatic Game Arts updates for Claude and Codex in this game."** Or, from a trusted checkout of this repository:
```text
python scripts/sync_local_agents.py bootstrap --source <GameArtsSkills checkout> --game-root <your game root> [--adopt-existing] [--hooks local|project|none] [--codex-user-hook] [--require-signed]
```

One install can serve several games: every script takes `--game-root`, so a framework installed in a parent folder works for a game in a nested folder (for example `--game-root stories/one`), and each game keeps its own `.gamearts/`.
- `--adopt-existing` only after you authorize backing up and replacing framework-path files already installed; without it a colliding or edited file is kept and reported as a conflict.
- Hook placement: `local` (default) writes Claude Code's personal `.claude/settings.local.json` (and adds it to `.git/info/exclude` so it is never committed); Codex has no project-local personal hook file, so its entry goes to `~/.codex/hooks.json` only with `--codex-user-hook`. `project` commits portable entries (no absolute paths; `--python-command` names the interpreter; needs a POSIX-style shell on every machine). `none` installs nothing.
- Both tools make you review and trust a new or changed hook (Codex: `/hooks`) before it runs. Do not assume the update is active until you have, and the first sync has completed.
- Each run keeps a file you edited, removes a file the framework dropped only if you never edited it (backed up first), advances its recorded revision only when a whole run finished, and refuses an incomplete checkout. `--require-signed` accepts only a commit with a valid signature (`git verify-commit`; needs the signer's key set up locally).
- State is `.gamearts/system/agent-sync-state.json`, backups are in `.gamearts/system/backups/`.
- A change on GitHub does not reach an offline computer; it applies at the next trusted session start, or when you say **"Update my installed Game Arts skills now."** If a check fails the agent reports that nothing was synchronized.
- The session that performs an update has already loaded the project instructions and skills it started with (observed in a real Claude Code session: the update ran at session start, yet the agent still answered from the previous `CLAUDE.md`). The new files apply from the next session.

**Security:** the updater downloads and runs framework scripts from a remote branch. Review the repository and the hooks before enabling it, and never enroll someone else's machine without their action.

## What this is not
Instructions plus validators and builders: not an image model, a sprite renderer or an engine importer. Nothing it produces is declared game-ready; engine import and runtime tests are the game project's, recorded as `engine_validation`.
