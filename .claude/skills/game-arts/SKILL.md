---
name: game-arts
description: Use for any creation, transformation, review, mockup, sprite, sprite sheet, game UI, world/scene art, terrain, character, effect, animation, atlas or Godot game-art task.
---

# Game Arts orchestrator

1. Read `GAME_ARTS_MASTER_STANDARD_v7.4.md` at the repository root. Treat the master as authoritative; avoid filling gaps by guessing.
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
Before selecting profiles or generating art, locate and read `<target-game-root>/.gamearts/project.json`. Use its saved values as default project choices and validate against `schemas/gamearts-project.schema.json`. If not found and configuration is needed, invoke the **conversational** `game-arts-project-setup` skill inside the current Claude/Codex chat; ask simple questions and offer recommended defaults. Never require user-run commands. Save the confirmed choices directly to the game project's `.gamearts/project.json` using available file tools. Do not treat the shared skills repository as the user's game repository. Never silently change saved settings. Always preserve universal rules of the master specification.

## Custom user instructions (mandatory preflight)
On **every Game Arts task**, load active applicable rules from `<game-root>/.gamearts/instructions/*.md` after reading persistent settings. Project-wide rules always apply; scope-specific rules apply to matching scene/world/asset/UI/animation etc. Route saving, finding, updating, disabling and deleting such rules to `game-arts-custom-instructions`. They are explicitly user-approved and stored in the game repository, never in the shared framework. Distinguish one-off requests from requests for persistence. No silent conflicts or overrides of global master requirements.

## Mandatory v7.3 mockup and asset lifecycle

Read the v7.3 standard and invoke the `game-arts-lifecycle` skill for generation staging, mockup/asset approval, rejection, revocation, replacement, restoration and listing. Use separate `<game>/.gamearts/outputs/mockups/{generated,approved,revoked}` and `<game>/.gamearts/outputs/assets/{generated,approved,revoked}` stores plus linked manifests. Every final asset references its exact **approved mockup revision** and blueprint region IDs. Use unique descriptive game-related versioned filenames, keep companion PNG/JSON/metadata together, and never silently overwrite or delete a revoked version. **No user-facing CLI or manual folder management.** Never claim approval without explicit user approval and verified file transitions.

## Automatic, user-friendly Game Arts behavior (v7.4)

When the user opens a game project and asks for art normally, **apply Game Arts automatically** using the project-root instructions. Quietly load the relevant `.gamearts/project.json`, active scoped `.gamearts/instructions/*.md` and approved mockup/asset manifests as needed; invoke specialist skills only for the actual task. **Do not require "initialize", "load Game Arts", command-line setup, special phrases or manual skill selection.** If settings are absent, use known approved defaults for preliminary work and ask one simple question only if an essential decision is missing. Do not repeat saved choices or demand approval again for unchanged accepted mockups. Keep storage, naming, manifests, JSON and tool operations behind the scenes. Ask only for meaningful design/approval decisions; verify files before reporting success. The user workflow is simply **open project → ask for art → approve when needed**.
