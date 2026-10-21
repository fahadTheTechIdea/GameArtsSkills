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

After installing the skills, configure the game **in its own repository**:

```bash
python /path/to/GameArtsSkills/scripts/setup_gamearts.py --project-dir /path/to/game
```

The wizard writes `<game>/.gamearts/project.json`. Commit that file so future Claude/Codex sessions read the exact saved settings. Use `--show` to inspect, `--validate` to check, and `--overwrite` only for intentional changes. Full details: [Project settings](docs/PROJECT_SETTINGS.md).
