# Game Arts automatic agent installation — v7.2

This is a **folder tree**, not a ZIP. Copy its files into the root of your game repository, preserving hidden directories.

## Claude Code
`CLAUDE.md` is project-root persistent guidance; `.claude/skills/<skill>/SKILL.md` provides discoverable focused skills. To apply across all your repositories on one machine, copy a skill directory under `~/.claude/skills/` and put the core policy in your user-level instructions as appropriate. For a shared team, commit the project files.

## Codex
`AGENTS.md` is root guidance; `.agents/skills/<skill>/SKILL.md` is the corresponding skill layout. Commit them in your repo. The agent selects a skill by its frontmatter description; reliable auto-activation comes from the root instruction invoking `game-arts` for relevant requests.

## Usage
Simply say, "Create a mockup of my game scene", "Generate a sprite for this asset", "Animate this component", or "Export atlas JSON". For new visual artwork, expect a mockup and approval stage; for an explicitly approved reference the workflow can continue directly.

## Sources
- `GAME_ARTS_MASTER_STANDARD_v7.7.md` — authoritative policy.
- `schemas/mockup-blueprint.schema.json` — one shared blueprint schema.
- `scripts/validate_blueprint.py` — basic structure and optional JSON schema checks.
- `scripts/validate_sheet_atlas.py` — dimensional checks and opaque-alpha gate (requires Pillow).

## Important
These are instructions plus small validators, not an AI image model, sprite renderer or Godot importer. Art generation, atlas assembly and Godot validation require those external tools to be available and actually run. None of the generated assets is automatically declared game-ready. All delivered Game Arts PNGs follow exact opaque #FF00FF and every sprite sheet needs a measured atlas JSON. No ZIP deliverables.
## Persistent per-game settings (new)

After installing the skills, open your game in **Claude Code or Codex** and say **“Set up Game Arts for this project.”** The agent asks a short series of easy questions, offers recommended defaults, and saves `<game>/.gamearts/project.json` through its project file tools. **Users do not run any Python command or edit JSON.** To review or update, say **“Show my Game Arts settings”** or **“Change my Game Arts settings.”** Commit the saved file so later sessions and teammates reuse your choices. Full details: [Project settings](docs/PROJECT_SETTINGS.md).

## Custom instructions in each game

To keep project-specific Game Arts rules, simply tell Claude or Codex **“Add a Game Arts instruction: ...”**. The agent uses `game-arts-custom-instructions` to save a dedicated Markdown file under the actual game's `.gamearts/instructions/` directory. It will automatically read applicable active rules on future art tasks. Say **“Show my custom art instructions”** to review or change them. See [custom instruction guide](docs/CUSTOM_INSTRUCTIONS.md). No commands required.

## Mockup and asset approval storage

Game Arts uses `.gamearts/outputs/mockups/{generated,approved,revoked}` and `.gamearts/outputs/assets/{generated,approved,revoked}` inside the **game project**. Every asset references its exact approved mockup revision. Tell the agent **“Approve this mockup”**, **“Approve this sprite”**, or **“Reject this artwork”**; no manual file moving. The `game-arts-lifecycle` skill manages complete PNG+atlas bundles, descriptive names and manifests. See [lifecycle guide](docs/ASSET_LIFECYCLE.md).

## Every session: no special commands

When Claude Code or Codex is opened in an installed game project, project-root instructions provide Game Arts awareness. Just ask for an artwork task; saved settings, active custom instructions and approved mockup/asset manifests are read quietly when relevant. The full standard and specialized skills are loaded on demand, not all at startup. The user never has to say “initialize Game Arts” or run a setup command unless explicitly choosing an advanced workflow. Tool/project access is required for persistence.

## Automatic mockup and production flow

Ask the agent normally for a world, scene, character, asset or UI design. If no approved visual reference exists, the agent should use `game-arts-mockup-creator` to create and display a real mockup using its available image tools, save a candidate, then request your approval. After approval it analyzes small details and creates final production art, sprite sheets and measured atlas JSON. Final assets have their own approval. The conversational setup wizard is used **only when you ask to configure the project or an essential setting is missing**, not as a mandatory ceremony before every mockup. Details: [User workflow](docs/USER_WORKFLOW.md).

## Bring your own mockup

**Bring your own mockup:** Upload or point the agent to artwork you created elsewhere. Game Arts imports a managed copy into the mockup lifecycle, preserves your original, and uses the approved version as its production reference—no unnecessary recreation.

When the user supplies an existing external mockup, **import a copy rather than generating a replacement**. Respect explicit prior approval; if not approved, ask for approval of that actual revision. Keep source provenance and a traceable managed reference. Do not claim an import succeeded unless file access and write operations were completed. Follow the v7.5 external mockup intake rules and require detailed decomposition before final art production.

## User-friendly commands

Once installed, there is no manual activation. Ask normally: **“Create a mockup”**, **“Use this outside mockup”**, **“This is already approved”**, **“Revise it”**, **“Approve this mockup”**, **“Generate sprites”**, **“Approve this sprite”**, **“Show approved art”**, **“Set up my game art”**, or **“Change my settings.”** The agent routes the complete wizard, mockup creation/import, decomposition, production, animation, atlas, validation and lifecycle stages automatically. See [full commands](docs/COMMANDS.md).

## Real moving component generation

For assets with moving parts, Claude/Codex calls `scripts/build_component_bundle.py` internally with approved frames and verified attachment coordinates. This generates separate component PNG sheets, their matching measured atlas JSON files and a nested sampled-transform bundle; it is not merely an instruction to generate metadata. The user does not run commands. See [Component Animation](docs/COMPONENT_ANIMATION.md). Actual Godot tests remain a separate step.

## Godot component scene integration

For a Godot project, the agent should install the reusable `godot/addons/gamearts/` files under the game's `res://addons/gamearts/` folder and use `scripts/generate_godot_scene.py` internally to create a native `.tscn` referencing the actual approved component bundle. No user-run commands. In-engine scene loading must be verified separately; do not claim it from Python JSON tests. See [Godot component runtime](docs/GODOT_COMPONENT_RUNTIME.md).
