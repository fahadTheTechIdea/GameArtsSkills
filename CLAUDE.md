# Game Arts — Claude Code Project Instructions

Automatically apply the `game-arts` skill under `.claude/skills/game-arts/SKILL.md` for any request to create, edit, review, animate, export, or validate game artwork, mockups, sprites, scenes, world art, characters, UI, tilesets, effects, attachments, or atlases. Read `GAME_ARTS_MASTER_STANDARD_v7.2.md` as the definitive source.

New artwork follows mockup → explicit approval → detailed decomposition → production → validation. Preserve approved style and dynamic asset profiles, exact opaque #FF00FF pixels in unused PNG regions, orthogonal square terrain profile, measured per-sheet JSON atlases, animated component hierarchy, Godot validation and individual file delivery without ZIP archives.

Never claim image generation or validation occurred unless it was actually performed.
## Persistent per-game settings

At the start of EVERY game-art task, check the **target game repository** for `.gamearts/project.json`, read it when present, and use its approved project defaults (style, camera, world grid, scale, directions, animation preference and mockup scope). Never invent settings that were explicitly configured. Project settings do not override the global master standard's mandatory requirements.

If absent and project setup is needed, use the `game-arts-project-setup` skill and `python scripts/setup_gamearts.py --project-dir <game-root>` from the GameArtsSkills toolkit. Do not save a game's config inside the shared skills repository. If settings exist, never silently overwrite them; use `--overwrite` only on user-requested reconfiguration. Commit the resulting `.gamearts/project.json` to the **game repository** for cross-session persistence.
