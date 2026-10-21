# Persistent Game Arts project settings

This repository is the **shared skill implementation**, while **each game repository owns its configuration** at:

```
<game-repository>/.gamearts/project.json
```

## Wizard

From the GameArtsSkills repository:

```bash
python scripts/setup_gamearts.py --project-dir /path/to/my-godot-game
```

The wizard asks for the game's art style, camera, terrain footprint and image size, nominal pixels per meter, placement snap, default directions, animation preference, and usual mockup scope.

Useful commands:

```bash
python scripts/setup_gamearts.py --project-dir /path/to/my-godot-game --show
python scripts/setup_gamearts.py --project-dir /path/to/my-godot-game --validate
python scripts/setup_gamearts.py --project-dir /path/to/my-godot-game --overwrite
```

The resulting JSON is **not** written into the shared GameArtsSkills repo. Commit it to **the actual game repository**, and future sessions can reuse the same settings.

## Priority and persistence

1. The Game Arts master standard supplies universal production requirements.
2. `.gamearts/project.json` supplies the game's persistent defaults.
3. An approved art/mockup profile and asset-specific configuration further specify each output within those requirements.
4. Explicit user-requested and approved changes should update the file and be committed; don't silently drift settings across sessions.

Universal invariants are intentionally not wizard-selectable: exact opaque #FF00FF for unused PNG regions; explicit mockup approval and detailed decomposition; measured JSON atlas for every sprite sheet; direction-aware animated attachment support where applicable; honest validation status; individual file delivery, no ZIP.

## Claude / Codex

`CLAUDE.md` and `AGENTS.md` require the agent to read `.gamearts/project.json` at the start of relevant tasks. If missing, the agent should offer or run the wizard before starting substantial game-art production. If the game uses skills installed elsewhere, make sure their instruction entry point is visible to the agent in that game project.

## Limitations

The wizard is a **CLI questionnaire**, not a visual desktop interface. It configures the production agent; it does not perform image generation or Godot validation. Its saved configuration is an input for the other Game Arts skills.
