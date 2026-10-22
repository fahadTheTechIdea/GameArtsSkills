# Game Arts Skills

[![Godot Runtime Smoke Test](https://github.com/fahadTheTechIdea/GameArtsSkills/actions/workflows/godot-runtime-tests.yml/badge.svg)](https://github.com/fahadTheTechIdea/GameArtsSkills/actions/workflows/godot-runtime-tests.yml)


**Universal AI-assisted 2D game graphics production skills for Claude Code and OpenAI Codex, with Godot 4 integration.**

This repository is the canonical source for Game Arts skills, specifications, schemas and validation tools.

## Quick commands — just talk to Claude or Codex

No special commands or technical setup are required. Open the game project and ask normally:

| What you say | What Game Arts does |
|---|---|
| **“Set up my game art.”** | Runs a short in-chat settings wizard and saves choices in the game. |
| **“Create a city scene mockup.”** | Generates a real visual preview and asks for approval. |
| **“Here is a mockup I created.”** | Imports a copy into generated mockups and offers approval. |
| **“This mockup is already approved.”** | Imports the approved version without generating a replacement. |
| **“Revise the mockup.”** | Creates a new candidate version, preserving earlier artwork. |
| **“Approve this mockup.”** | Locks the reference, saves it in approved, and analyzes all visible details. |
| **“Generate sprites from the approved mockup.”** | Produces traceable assets, animation sheets and measured atlases. |
| **“Approve this sprite.”** | Promotes the validated PNG and companion metadata as a complete bundle. |
| **“Show approved art.”** | Finds the current approved images in the game project. |
| **“Change my settings / add an art instruction.”** | Updates saved settings or scoped custom instructions conversationally. |

See **[all natural-language commands](docs/COMMANDS.md)** for animation, atlas, rejected/revoked versions, restoration and Godot testing.

## Just ask for game art

Once installed in your game project, **open Claude Code or Codex and describe what you want**. Game Arts automatically reads your saved project settings and relevant approved references. You do **not** need to initialize skills or run commands. It asks only for necessary choices and approval of new mockups/art. See the [automatic user experience standard](GAME_ARTS_MASTER_STANDARD_v7.7.md).

## Use your own mockup

**Bring your own mockup:** Upload or point the agent to artwork you created elsewhere. Game Arts imports a managed copy into the mockup lifecycle, preserves your original, and uses the approved version as its production reference—no unnecessary recreation. If you say it's already approved, it enters the project's `mockups/approved/` with provenance; otherwise it goes into `mockups/generated/` for review. Final sprites and atlases are still generated and approved separately. Original external files are never moved or modified without permission.

## The complete workflow — automatic, not just setup

Ask for an art asset in natural language. Game Arts reuses saved project choices and your relevant custom rules, **creates and displays a visual mockup** when no approved one exists, asks for approval, analyzes the mockup's geometry/textures/small details/animations, generates the production sprite and atlas, validates it, and asks for final approval. There are **two distinct approvals**: the visual mockup and final production asset. No CLI or manual folder management.

- **Set up my game art** → friendly in-chat wizard when you actually want to configure settings.
- **Create a city-scene mockup** → image preview, revision and approval flow.
- **Generate an asset** → find the approved reference or create a mockup first.
- **Approve this** → move exact revision to approved and continue the next stage.
- **Show approved artwork** → read lifecycle records, not loose files.

Read the [complete everyday workflow](docs/USER_WORKFLOW.md).

## Real sprite-sheet and atlas builder

Game Arts now includes an executable [sprite-sheet + measured atlas generator](scripts/build_sheet_atlas.py) using actual frame PNGs. Claude Code and Codex should invoke it automatically behind the scenes when creating multi-frame artwork. The generator produces a paired **opaque pink PNG** and **JSON atlas**; [tests](tests/test_build_sheet_atlas.py) and [CI](.github/workflows/atlas-tests.yml) check basic assembly invariants. Read the [atlas generation guide](docs/ATLAS_GENERATION.md) for details and limitations.

The generator accurately calculates frame rectangles and transformed **supplied** anchors. It does **not** automatically infer mechanical attachment points from images or create native Godot scenes. Those remain separate validation/integration steps.

## Moving-part generation — now implemented

The [modular component bundle builder](scripts/build_component_bundle.py) accepts actual approved frames and verified anchor coordinates, builds **separate PNG sprite sheets plus measured atlas JSON files for every required component direction**, and outputs a nested, time-dependent attachment-transform bundle. Its [tests](tests/test_component_bundle.py) cover direction checks, missing mounts, nested transforms and error handling. Read the [component animation guide](docs/COMPONENT_ANIMATION.md).

**Limitations:** It does not generate missing artwork, visually infer true pivots/mount locations, or export/test a Godot scene automatically. Those stages require separate image and engine tooling.

## Godot component playback — initial integration

The repository now includes a [reusable native Godot 4 component scene](godot/addons/gamearts/game_arts_component.tscn), [direction-aware runtime script](godot/addons/gamearts/game_arts_component.gd), [runtime pink-mask shader](godot/addons/gamearts/chroma_key.gdshader), and [scene generator](scripts/generate_godot_scene.py). They load the generated component bundle and display individually moving nested components, updating all applicable directions together at one normalized animation phase.

The [integration guide](docs/GODOT_COMPONENT_RUNTIME.md) describes setup and limitations. **Godot headless/editor execution is not yet verified.** The component builder still requires artist-verified anchors and approved source frames; native collision, occlusion and light updates are not automatic.

## Godot runtime smoke test (CI)

The repository now includes a synthetic modular-art generator and a **real Godot 4 headless smoke test** that imports a generated scene, verifies directional artwork and nested mounts, checks parent/child motion, and ensures the chroma-key ShaderMaterial is loaded. This runs in [GitHub Actions](https://github.com/fahadTheTechIdea/GameArtsSkills/actions/workflows/godot-runtime-tests.yml) when relevant files change. Test source: [Godot runner](tests/godot/test_runtime.gd) and [fixture generator](tests/create_godot_fixture.py).

**Do not infer successful engine testing from committed files alone.** Check the Actions result. Headless structural tests do not certify actual composited pixels, collision/navigation, lighting or artist-approved alignment. Those still require visual/engine tests.

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
| [game-arts-mockup-creator](.agents/skills/game-arts-mockup-creator/SKILL.md) | Produces actual visual mockups and handles review before final art |
| [mockup-analyzer](.agents/skills/mockup-analyzer/SKILL.md) | Decomposes approved world, scene, character, asset and UI mockups |
| [art-profile](.agents/skills/art-profile/SKILL.md) | Applies the approved game visual style |
| [animation-planner](.agents/skills/animation-planner/SKILL.md) | Plans moving parts, directional coverage and key poses |
| [sheet-atlas](.agents/skills/sheet-atlas/SKILL.md) | Assembles images and generates measured atlas metadata |
| [godot-validator](.agents/skills/godot-validator/SKILL.md) | Checks technical outputs and in-engine behavior |

## Reference and validation

- [Master standard v7.6](GAME_ARTS_MASTER_STANDARD_v7.7.md) — **canonical specification**.
- [Mockup Blueprint JSON schema](schemas/mockup-blueprint.schema.json)
- [Blueprint validator](scripts/validate_blueprint.py)
- [Sprite sheet/atlas validator](scripts/validate_sheet_atlas.py)

## Current game-world geometry

The approved world profile uses an **orthogonal square grid**, with 16 × 16-meter logical terrain cells, initially 256 × 256-pixel ground art, nominal 16 px/m, 1-meter default construction snapping and continuous world coordinates. Elevated oblique art for objects does not imply changing the world map into an isometric grid.

## Contributing and maintenance

Update the master specification first, then keep the specialist skills, schemas, validators and install guide consistent. Test behavior in the target Godot game, and never claim a sprite or atlas is game-ready without the applicable validation.

The separate [bundle validator](scripts/validate_component_bundle.py) checks that every referenced component PNG/atlas exists, direction sets and frame rectangles are valid, all source PNGs are opaque and sampled composed transforms are finite. It does **not** replace in-Godot visual/physics verification.

## Asset direction policy and living documentation

Static structures and fixed machinery have **one approved world view by default**, with separately animated moving parts; freely moving objects use **eight directions when directional gameplay requires it**. UI portraits are their own single-view presentation assets. Restricted placement rotations are explicit exceptions, not forced eight-view sheets. All angles must preserve the approved asset identity and art style.

**Maintenance:** revise the existing canonical master standard and associated files in place; do not add another numbered master document for each change.


**Single canonical master:** Only [GAME_ARTS_MASTER_STANDARD_v7.7.md](GAME_ARTS_MASTER_STANDARD_v7.7.md) is maintained; older numbered copies have been retired. Future revisions update this existing file in place, rather than adding another master document. Distinct technical guides and Claude/Codex skills remain separate because they serve different purposes.


## Reference-controlled image prompts — mandatory

Game Arts now uses actual approved mockups and **task-specific prompt packets**, not generic requests for an attractive picture. The [single canonical master standard](GAME_ARTS_MASTER_STANDARD_v7.7.md) contains prompt templates for static structures, fixed machinery, mobile directional masters, moving parts, key poses, UI portraits, terrain, effects and corrective edits.

**Generation is staged:** approved crop → one locked master → master review → isolated moving components → approved key poses → deterministic animation and actual measured atlas generation. **No image-generated contact sheets, text/diagram labels or fake JSON in production PNGs.** Static structures receive one approved world view by default; mobile objects use the required directional set. Oilfield Days' world view is elevated 3/4 top-down oblique, not isometric.

The actual approved image must be passed to the image tool if reference-image conditioning is supported. A textual mention of the mockup alone is not proof that it was used. Artistic review and script validation are separate gates. A failure must be reported, not silently approved.


## Selected project style controls every image prompt

Game Arts builds the **actual image-tool prompt** from the current game's `.gamearts/project.json` before every image request: selected `art_style.id` and style reference, `world.object_camera`, project scale, chosen asset view policy, animation method and export requirements. Applicable per-game custom instructions and exact approved mockup/locked-master references also apply. The agent must pass actual source images when supported and cannot substitute a generic “pixel-art/isometric” prompt for a different selected style.

**Priority:** universal output requirements → explicit approved user changes/locked asset identity → relevant custom and asset-specific rules → saved game settings → carefully labeled defaults. Conflicts are surfaced; the agent never silently changes a previously approved camera or style. The system supports pixel art, painted, illustrated, vector, rendered-to-2D and custom styles. See the [existing project settings guide](docs/PROJECT_SETTINGS.md) and [canonical master](GAME_ARTS_MASTER_STANDARD_v7.7.md).
