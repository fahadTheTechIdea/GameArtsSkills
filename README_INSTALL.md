# Game Arts automatic agent installation

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

## Included reference-image workflow (all games, all users)

**Install the framework as a complete package**, not just its Claude/Codex skill Markdown. In addition to the project-root `AGENTS.md` or `CLAUDE.md`, both skills directories, existing master standard and schemas, the agent needs the `scripts/` folder, especially **`scripts/prepare_reference_crop.py`** and the sprite/atlas builders. The reference helper uses Python 3 and **Pillow**; the agent should check dependencies and, with appropriate permissions, install them internally in its normal Python environment if missing. Do not make ordinary users run commands or manually write JSON.

**Automatic path:** An approved mockup is already stored under the active **game** project’s `.gamearts/outputs/mockups/approved/` with an approved `mockups.json` entry. On “Generate this asset from the mockup,” the existing `mockup-analyzer` measures the object's actual bounding rectangle and passes it to the crop helper. The helper creates a source-faithful PNG crop and reference packet under the **same asset candidate** folder: `.gamearts/outputs/assets/generated/<asset-revision>/reference/`. The agent attaches that exact crop to a compatible image/edit tool and uses the game's chosen visual style, camera and instructions. The agent may then generate **one master candidate**, compare it with the reference and request master approval; component/sheet/atlas generation follows separately.

The reference packet and crop are **supporting candidate files**, not a new top-level lifecycle, not an asset type, and not a reason to reorganize approved mockups. `prepare_reference_crop.py verify` can check recorded input/file hashes and opaque candidate pixels, **not provider-side proof of image conditioning or artistic similarity**. A source-conditioned tool invocation is required for reference-locked production. If the tool lacks actual image input, stop that stage and report the blocker instead of generating a generic structure. The agent must not claim local integration when only GitHub source files were updated.

This works with all selected art media. World structures use a single approved view by default, mobile directional assets use the game's required directions, and UI icons use their own selected UI presentation viewpoint. The crop is left in original mockup colors; the new production PNG must use exact opaque #FF00FF. [Existing user workflow](docs/USER_WORKFLOW.md) describes the integrated steps.

## Framework maintenance

Keep **one current master standard** (`GAME_ARTS_MASTER_STANDARD_v7.7.md`), the existing dedicated skills and workflows, and the existing generated/approved/revoked lifecycle. Update them in place instead of introducing multiple parallel standards or separate image-type pipelines.


## Automatic local updates for BOTH Claude Code and Codex

Game Arts now ships with [`scripts/sync_local_agents.py`](scripts/sync_local_agents.py), an opt-in **project-local updater**. One trusted setup installs safe `SessionStart` hooks for both local agents. Whenever either Claude Code or Codex opens/resumes the game project, the hook checks the canonical GameArtsSkills `main` branch and synchronizes both local skill directories and all framework-managed support files.

**For ordinary users:** In your locally connected Claude Code or Codex session, say **“Enable automatic Game Arts updates for both Claude and Codex in this game.”** The agent should locate this framework's trusted checkout and run the updater's one-time bootstrap on the current game workspace, preserving your game data and all unrelated client settings. Approve the respective client hook trust review. If you have multiple game repositories, ask the agent to enroll each intended project once.

**For advanced installers (optional):** From an existing trusted GameArtsSkills checkout:
```text
python scripts/sync_local_agents.py bootstrap --source <GameArtsSkills checkout> --game-root <your game root> --adopt-existing
```
Use `--adopt-existing` **only after authorizing the backup-and-update** of existing framework-path files. Without this flag the updater preserves colliding unowned files and reports them. The updater tracks managed hashes in `.gamearts/system/agent-sync-state.json` and stores backups inside `.gamearts/system/backups/`. It **never syncs or overwrites** `.gamearts/project.json`, `.gamearts/instructions/`, `.gamearts/outputs/`, unrelated custom skills, or unmarked user content in AGENTS.md/CLAUDE.md.

An installed bootstrap merges one project-local `SessionStart` entry into `.claude/settings.json` and `.codex/hooks.json`, retaining existing settings. Codex may ask you to review/trust the hook in `/hooks`; Claude Code applies its own hook safety controls. This is a one-time trust step, not something required for each art asset.

**Update timing:** Since GitHub cannot directly modify an offline PC, local installations refresh on the next trusted agent session startup/resume, not instantly at the remote commit timestamp. Internet access, Git and local filesystem permissions are required. If a check fails, the agent must report that it did **not** synchronize. This updater is for project-local installations; arbitrary unknown global installations elsewhere on the machine are not silently altered. Both Claude and Codex for each enrolled game are updated from the same verified source revision.

**Security:** Auto-update is opt-in because trusted local hooks can download and run framework code. Review the repository and hooks before enabling.


## Parent-artwork cleanup verification is required for ALL styles

Install the existing `scripts/validate_parent_cleanup.py` with the rest of Game Arts. The current `mockup-analyzer` identifies *all* independently movable/removable/interactive/replaceable/animated objects. The agent must remove those objects **from the clean static parent** as well as export them individually—creating a reviewed clean background where the objects used to be. Keeping the workbench/screw/wheel/door painted in the parent and also exporting an isolated sprite is a rejection.

The helper compares original composite PNG, final static-parent PNG, independently reviewed clean plate, component ownership masks, and exported component sprites. For nested/multi-view component bundles, use the current builder with packaged cleanup evidence and the existing validator's `--approval-gate` before promoting to approved. For a stand-alone structure with detached props but no animation bundle, run `validate_parent_cleanup.py` directly. These scripts are run internally by Claude/Codex, not by the user.

All styles (pixel, painted, vector, illustrated, rendered-to-2D, custom) share this ownership rule. Exact raster comparison requires **pixel-aligned exported layers**, but does not dictate the style's visible edge quality. If aligned source art, masks, or reviewed clean plates are unavailable, the gate stays pending and approval is blocked. Do not fabricate compliance evidence.
