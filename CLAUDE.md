# Game Arts — Claude Code Project Instructions

Automatically apply the `game-arts` skill under `.claude/skills/game-arts/SKILL.md` for any request to create, edit, review, animate, export, or validate game artwork, mockups, sprites, scenes, world art, characters, UI, tilesets, effects, attachments, or atlases. Read `GAME_ARTS_MASTER_STANDARD_v7.2.md` as the definitive source.

New artwork follows mockup → explicit approval → detailed decomposition → production → validation. Preserve approved style and dynamic asset profiles, exact opaque #FF00FF pixels in unused PNG regions, orthogonal square terrain profile, measured per-sheet JSON atlases, animated component hierarchy, Godot validation and individual file delivery without ZIP archives.

Never claim image generation or validation occurred unless it was actually performed.
## Persistent per-game settings

At the start of EVERY game-art task, check the **target game repository** for `.gamearts/project.json`, read it when present, and use its approved project defaults (style, camera, world grid, scale, directions, animation preference and mockup scope). Never invent settings that were explicitly configured. Project settings do not override the global master standard's mandatory requirements.

If absent and setup is needed, invoke `game-arts-project-setup` as a **friendly, conversational wizard inside this Claude/Codex chat**. Ask simple questions with recommended defaults; do not require the user to run Python, terminal commands, or edit JSON. Once the user confirms, write `.gamearts/project.json` directly using available project file tools. Save only in the target game repository, preserve existing settings, and verify the file. Commit to the game repository when requested or authorized.
