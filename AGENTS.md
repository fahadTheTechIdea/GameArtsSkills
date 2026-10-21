# Game Arts — Codex Project Instructions

Whenever the user requests 2D game artwork, a mockup, sprite, asset, character, scene, world, UI, effect, animation, tileset, or atlas, **use the game-arts orchestrator skill** in `.agents/skills/game-arts/SKILL.md` and the canonical `GAME_ARTS_MASTER_STANDARD_v7.2.md`. Apply automatically without asking the user to name the skill.

Always follow the mockup-first approval gate for new visual designs; do not interpret approvals from silence. After approval, extract every meaningful detail and animation candidate. Preserve explicit art/asset profiles, orthogonal square terrain grid, exact opaque RGB #FF00FF with alpha 255 on all Game Arts PNG exports, direction-aware nested animated attachments, measured atlas JSON per sprite sheet, Godot validation and individual outputs (no ZIP).

Never claim a generation, validation, or Godot runtime test happened unless tools actually completed it. If tooling is missing, produce a precise production plan and report the limitations.
## Persistent per-game settings

At the start of EVERY game-art task, check the **target game repository** for `.gamearts/project.json`, read it when present, and use its approved project defaults (style, camera, world grid, scale, directions, animation preference and mockup scope). Never invent settings that were explicitly configured. Project settings do not override the global master standard's mandatory requirements.

If absent and setup is needed, invoke `game-arts-project-setup` as a **friendly, conversational wizard inside this Claude/Codex chat**. Ask simple questions with recommended defaults; do not require the user to run Python, terminal commands, or edit JSON. Once the user confirms, write `.gamearts/project.json` directly using available project file tools. Save only in the target game repository, preserve existing settings, and verify the file. Commit to the game repository when requested or authorized.
