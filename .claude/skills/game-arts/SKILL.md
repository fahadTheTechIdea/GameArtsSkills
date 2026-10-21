---
name: game-arts
description: Use for any creation, transformation, review, mockup, sprite, sprite sheet, game UI, world/scene art, terrain, character, effect, animation, atlas or Godot game-art task.
---

# Game Arts orchestrator

1. Read `GAME_ARTS_MASTER_STANDARD_v7.2.md` at the repository root. Treat the master as authoritative; avoid filling gaps by guessing.
2. Classify the task: visual mockup, mockup analysis, production image, animation/components, sheet/atlas, Godot validation or a mixed project.
3. For **new** visual content produce a reviewable mockup and obtain **explicit approval** before final production. If an explicitly approved reference already exists, reuse its revision; do not re-approve needlessly.
4. Determine mockup scope: world, scene, asset, character, ui_screen, ui_flow or mixed. For complex or mixed work, delegate analysis to `mockup-analyzer` and recurse into nested blueprints.
5. Select active art profile and asset profile. Preserve latest **orthogonal square-grid** game geometry (16 m square logical ground cells, initial 256×256 px), not obsolete diamond tiles.
6. After approval, inventory every meaningful visible detail: surfaces, edges, textures, small props, structures, signals, lights, vegetation, typography/UI, motion candidates. Mark observed vs inferred. Build a complete blueprint.
7. Generate reference-conditioned locked masters; plan needed directional views and key poses. Independently movable/state-changing parts get dedicated reusable components or justified alternate motion resources. Anchors themselves can animate; synchronize parent/child states and all required directions.
8. Deliver PNGs with **exact opaque RGB #FF00FF / alpha 255** in unused regions. Never export transparent PNGs without explicit exception.
9. Compose sheets deterministically and compute a measured JSON atlas **for every sprite sheet**, including pivots, coordinate spaces, world anchors and animated attachment transforms as appropriate.
10. Validate the final composed output, and test in Godot when available. If validation/tools are unavailable, disclose unverified status. Deliver **individual files**, no ZIP.

## Route focused work
Read `.agents/skills/<name>/SKILL.md` (Codex) or `.claude/skills/<name>/SKILL.md` (Claude) for `mockup-analyzer`, `art-profile`, `animation-planner`, `sheet-atlas`, `godot-validator` as applicable. Those are focused modules, not automatically mandatory for every task.
## Persisted project configuration
Before selecting profiles or generating art, locate and read `<target-game-root>/.gamearts/project.json`. Use its saved values as default project choices and validate against `schemas/gamearts-project.schema.json`. If not found, invoke `game-arts-project-setup` or the `scripts/setup_gamearts.py` questionnaire before substantial art generation. Do not treat the shared skills repository as the user's game repository. Never silently change saved settings. Always preserve universal rules of the master specification.
