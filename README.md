# Game Arts Skills

**Universal AI-assisted 2D game graphics production skills for Claude Code and OpenAI Codex, with Godot 4 integration.**

This repository is the canonical source for Game Arts skills, specifications, schemas and validation tools.

## Just ask for game art

Once installed in your game project, **open Claude Code or Codex and describe what you want**. Game Arts automatically reads your saved project settings and relevant approved references. You do **not** need to initialize skills or run commands. It asks only for necessary choices and approval of new mockups/art. See the [automatic user experience standard](GAME_ARTS_MASTER_STANDARD_v7.4.md).

## Capabilities

- **Mockup-first:** approve whole-world, scene, asset, character and UI mockups before final art production.
- **Detailed mockup analysis:** extract visible geometry, materials, textures, small details, states and animation candidates.
- **Art-style profiles:** pixel art, illustrated, painted, vector, rendered-to-2D and custom visual systems.
- **Reference-controlled art:** locked masters, consistent directions, key-pose animation, and sprite cleanup.
- **Moving parts:** independent and nested components, animated directional attachments and synchronized states.
- **Production outputs:** deterministic sprite sheets, **measured JSON atlas for every sprite sheet**, quality checks and generation provenance.
- **Strict source masking:** all Game Arts PNG unused areas must be exact opaque **#FF00FF**.
- **Godot integration:** world-scale, composed scene, render and animation validation.
- **Individual files only:** no ZIP-only asset delivery.

## Install

| Tool | Automatic project instructions | Specialist skills |
|---|---|---|
| Claude Code | [CLAUDE.md](CLAUDE.md) | [`.claude/skills/`](.claude/skills/) |
| Codex | [AGENTS.md](AGENTS.md) | [`.agents/skills/`](.agents/skills/) |

1. Clone or copy the matching agent instruction and skill directories into the game repository.
2. Follow [README_INSTALL.md](README_INSTALL.md).
3. Request ordinary tasks such as *"Create a mockup for this game level"* or *"Generate an animation sheet from the approved mockup."*
4. The orchestrator selects relevant skills without requiring a special prompt phrase.

These files provide reusable agent workflows and validators, not a standalone image renderer. Actual sprite generation requires supported image and artifact tools.

## Persistent game settings and setup wizard

Game Arts saves **per-game settings in the game repository**, at `.gamearts/project.json` (not in the shared skills repository). These settings survive new Claude and Codex sessions when the agents load the project's files.

**Run the setup wizard directly in Claude Code or Codex chat** by saying **“Set up Game Arts for my game”**. The agent asks a few simple questions, offers recommended defaults, and saves the answers to the game repository itself. No command-line steps or manual JSON edits are required. For later changes say **“Show my Game Arts settings”** or **“Change my Game Arts settings.”** Commit the generated settings file in the game repository for shared persistence. See [project settings documentation](docs/PROJECT_SETTINGS.md) and [JSON schema](schemas/gamearts-project.schema.json).

Both Claude and Codex have a [project setup skill](.agents/skills/game-arts-project-setup/SKILL.md) which runs the entire setup conversationally and saves your selections for you.

## Custom instructions — saved per game

You can add persistent Game Arts preferences directly in Claude Code or Codex by saying **“Always use soft morning lighting for this game”**, **“Add a custom UI art instruction”**, or **“Show my custom Game Arts instructions.”** No JSON editing or commands required.

Each approved rule is saved separately in the **game repository** at `.gamearts/instructions/*.md`. The orchestrator retrieves active rules automatically for relevant art tasks and checks them against the universal master requirements. See [custom instructions guide](docs/CUSTOM_INSTRUCTIONS.md).

## Mockup and asset lifecycle

Mockups and production art have **separate generated / approved / revoked** folders inside each game. Every production asset is linked to its **specific approved mockup revision** and approved blueprint details. Files use descriptive game-related versioned names; PNGs, companion atlases and metadata move together during approval or revocation.

You can simply say **“Approve this mockup”**, **“Reject this image”**, **“Show approved sprites”**, or **“Restore the previous version.”** The agent manages the folders and records automatically. See [asset lifecycle guide](docs/ASSET_LIFECYCLE.md).

## Skill catalog

| Skill | Purpose |
|---|---|
| [game-arts](.agents/skills/game-arts/SKILL.md) | Orchestrates profile selection and production gates |
| [game-arts-project-setup](.agents/skills/game-arts-project-setup/SKILL.md) | Configures persistent game-specific defaults |
| [game-arts-lifecycle](.agents/skills/game-arts-lifecycle/SKILL.md) | Manages generated, approved, revoked mockups and linked asset bundles |
| [game-arts-custom-instructions](.agents/skills/game-arts-custom-instructions/SKILL.md) | Saves, retrieves and manages user-defined per-game art rules |
| [mockup-analyzer](.agents/skills/mockup-analyzer/SKILL.md) | Decomposes approved world, scene, character, asset and UI mockups |
| [art-profile](.agents/skills/art-profile/SKILL.md) | Applies the approved game visual style |
| [animation-planner](.agents/skills/animation-planner/SKILL.md) | Plans moving parts, directional coverage and key poses |
| [sheet-atlas](.agents/skills/sheet-atlas/SKILL.md) | Assembles images and generates measured atlas metadata |
| [godot-validator](.agents/skills/godot-validator/SKILL.md) | Checks technical outputs and in-engine behavior |

## Reference and validation

- [Master standard v7.2](GAME_ARTS_MASTER_STANDARD_v7.4.md) — **canonical specification**.
- [Mockup Blueprint JSON schema](schemas/mockup-blueprint.schema.json)
- [Blueprint validator](scripts/validate_blueprint.py)
- [Sprite sheet/atlas validator](scripts/validate_sheet_atlas.py)

## Current game-world geometry

The approved world profile uses an **orthogonal square grid**, with 16 × 16-meter logical terrain cells, initially 256 × 256-pixel ground art, nominal 16 px/m, 1-meter default construction snapping and continuous world coordinates. Elevated oblique art for objects does not imply changing the world map into an isometric grid.

## Contributing and maintenance

Update the master specification first, then keep the specialist skills, schemas, validators and install guide consistent. Test behavior in the target Godot game, and never claim a sprite or atlas is game-ready without the applicable validation.
