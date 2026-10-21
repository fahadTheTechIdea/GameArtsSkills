# Game Arts automatic agent installation — v7.2

This is a **folder tree**, not a ZIP. Copy its files into the root of your game repository, preserving hidden directories.

## Claude Code
`CLAUDE.md` is project-root persistent guidance; `.claude/skills/<skill>/SKILL.md` provides discoverable focused skills. To apply across all your repositories on one machine, copy a skill directory under `~/.claude/skills/` and put the core policy in your user-level instructions as appropriate. For a shared team, commit the project files.

## Codex
`AGENTS.md` is root guidance; `.agents/skills/<skill>/SKILL.md` is the corresponding skill layout. Commit them in your repo. The agent selects a skill by its frontmatter description; reliable auto-activation comes from the root instruction invoking `game-arts` for relevant requests.

## Usage
Simply say, "Create a mockup of my game scene", "Generate a sprite for this asset", "Animate this component", or "Export atlas JSON". For new visual artwork, expect a mockup and approval stage; for an explicitly approved reference the workflow can continue directly.

## Sources
- `GAME_ARTS_MASTER_STANDARD_v7.2.md` — authoritative policy.
- `schemas/mockup-blueprint.schema.json` — one shared blueprint schema.
- `scripts/validate_blueprint.py` — basic structure and optional JSON schema checks.
- `scripts/validate_sheet_atlas.py` — dimensional checks and opaque-alpha gate (requires Pillow).

## Important
These are instructions plus small validators, not an AI image model, sprite renderer or Godot importer. Art generation, atlas assembly and Godot validation require those external tools to be available and actually run. None of the generated assets is automatically declared game-ready. All delivered Game Arts PNGs follow exact opaque #FF00FF and every sprite sheet needs a measured atlas JSON. No ZIP deliverables.
## Persistent per-game settings (new)

After installing the skills, open your game in **Claude Code or Codex** and say **“Set up Game Arts for this project.”** The agent asks a short series of easy questions, offers recommended defaults, and saves `<game>/.gamearts/project.json` through its project file tools. **Users do not run any Python command or edit JSON.** To review or update, say **“Show my Game Arts settings”** or **“Change my Game Arts settings.”** Commit the saved file so later sessions and teammates reuse your choices. Full details: [Project settings](docs/PROJECT_SETTINGS.md).

## Custom instructions in each game

To keep project-specific Game Arts rules, simply tell Claude or Codex **“Add a Game Arts instruction: ...”**. The agent uses `game-arts-custom-instructions` to save a dedicated Markdown file under the actual game's `.gamearts/instructions/` directory. It will automatically read applicable active rules on future art tasks. Say **“Show my custom art instructions”** to review or change them. See [custom instruction guide](docs/CUSTOM_INSTRUCTIONS.md). No commands required.
