# Game Arts — Everyday Commands

No special command syntax is required. **Say what you want in natural language inside Claude Code or Codex** while working in your game project. The agent selects the skills and handles files in the background.

## Start and personalize

| Say | Agent behavior |
|---|---|
| "Set up Game Arts for this game." | Ask a few friendly questions in chat; save confirmed project defaults. |
| "Use the recommended settings." | Use established game profile defaults; ask only for missing essential decisions. |
| "Show my game art settings." | Read and summarize saved project settings. |
| "Change my game's art style." | Change only the selected setting, confirm and save. |
| "Always make the UI icons simple." | Save a scoped custom instruction in the game project. |
| "Show my custom art instructions." | Summarize applicable saved custom rules. |

## Mockups (created by the agent or provided by you)

| Say | Agent behavior |
|---|---|
| "Create a mockup of my world." | Render an actual world-scale concept preview when image tools are available, save as a generated mockup and show for approval. |
| "Create a city scene mockup." | Generate a reviewable scene mockup using the game's saved style and references. |
| "Create a mockup of this character." | Preserve its reference identity and show visual design for approval. |
| "Design a UI screen mockup." | Generate a screen mockup; UI geometry is screen-space, not world terrain geometry. |
| "Here is a mockup I made. Use it." | Import a managed **copy** into `mockups/generated`, preserve the external original, show and ask approval unless already explicitly approved. |
| "Here is my already approved mockup." | Import a managed copy directly into `mockups/approved`, record the approval and source; no unnecessary recreation or repeat approval. |
| "Make the pavement wider and revise the mockup." | Produce a *new version* in generated; preserve old revision. |
| "Approve this mockup." | Promote the exact identified revision to approved, update manifest, then extract a detailed blueprint. |
| "Reject this mockup." | Move the managed version to revoked with the reason; preserve external original. |
| "Show my approved mockups." | Show current approved mockup revisions from the manifest. |

## Production artwork, animations, and approvals

| Say | Agent behavior |
|---|---|
| "Generate game art from the approved mockup." | Decompose all meaningful visible details; generate production candidates tied to that exact mockup. |
| "Create a sprite sheet for this object." | Find approved reference or show a mockup first; produce native-size art with needed directions and states. |
| "Animate the moving components." | Discover applicable components, use correct directional images/animated mounts, generate validated animation resources. |
| "Generate the atlas JSON." | Measure actual exported sprites and generate a matching atlas for each sheet. |
| "Approve this sprite." | Require exact revision identity and appropriate validation; promote the complete PNG + atlas + metadata bundle. |
| "Reject this sprite because its scale is wrong." | Revoke the whole managed bundle, record the reason and keep its mockup link. |
| "Show my approved artwork." | Find active approved assets using the asset manifest, not temporary directory guesses. |
| "Restore the earlier approved version." | Revalidate and obtain necessary reapproval, then safely restore its status. |
| "Check this asset in Godot." | Use available Godot tools to validate; explain clearly if tests could not be run. |

## Automatic decision rules

1. **Every game-art request:** load available per-game settings, active applicable custom instructions, current approved references and lifecycle manifests when relevant.
2. **New design with no approved visual:** create and show an *actual mockup* (not only a text description), save as generated, then ask for explicit approval.
3. **User-supplied mockup:** import a managed copy. Already explicitly approved → approved; otherwise → generated and request approval. Do not regenerate it unnecessarily.
4. **Approved mockup:** analyze detailed surfaces, geometry, textures, objects, UI elements, small details and possible real-world movement/state changes. Link every production asset to its exact approved revision and blueprint region.
5. **Production:** generate locked masters, directional/animated components and measured atlas metadata, then validate and request **separate final art approval**.
6. **Lifecycle:** generated / approved / revoked for both mockups and assets. Keep full dependent file bundles together, use meaningful game-related versioned names, and preserve revocation history.
7. **Never assume "approved" means an unrelated item.** Resolve the target from the currently shown revision; ask only if the target is genuinely ambiguous.
8. **Don't pretend to run tools.** If image/file/Godot tools are missing, report the limitation rather than claiming files, previews or tests were created.
9. **Never require technical commands** or manual file editing from normal users. The agent manages the technical steps.
10. **Maintain universal requirements:** opaque exact #FF00FF pixels for unused PNG areas, measured JSON atlas per sprite sheet, valid animated attachment hierarchies, honest verification and no ZIP files.

## Where files belong

Inside each **game repository**, not this shared skills repository:

```text
.gamearts/
  project.json
  instructions/
  outputs/
    mockups/{generated,approved,revoked}/
    assets/{generated,approved,revoked}/
    manifests/{mockups.json,assets.json}
```

For installation details, see [README_INSTALL.md](../README_INSTALL.md). The canonical production requirements are in [GAME_ARTS_MASTER_STANDARD_v7.7.md](../GAME_ARTS_MASTER_STANDARD_v7.7.md).

## Working sheet and atlas generator

When approved source frames exist and a sprite sheet is requested, invoke the `sheet-atlas` skill and have the agent run `scripts/build_sheet_atlas.py` internally, then `scripts/validate_sheet_atlas.py`. This creates **real** native-scale opaque pink PNG sheets and companion measured JSON atlases. Save the pair together in the game project's generated asset bundle and request approval. See `docs/ATLAS_GENERATION.md`. The builder transforms **provided** pivot and anchor data into cell coordinates; it does not infer physical mount points or certify visual/Godot readiness. Never claim atlas generation unless files were actually written and checked. Users do not need to run commands.

## Real moving component generation

For assets with moving parts, Claude/Codex calls `scripts/build_component_bundle.py` internally with approved frames and verified attachment coordinates. This generates separate component PNG sheets, their matching measured atlas JSON files and a nested sampled-transform bundle; it is not merely an instruction to generate metadata. The user does not run commands. See [Component Animation](docs/COMPONENT_ANIMATION.md). Actual Godot tests remain a separate step.

## Godot runtime component support (v7.7)

For approved nested moving-part bundles, use the reusable `godot/addons/gamearts/game_arts_component.gd`, `.tscn` and `chroma_key.gdshader` in the target game's `res://addons/gamearts/` folder where integration is requested. Internally invoke `scripts/generate_godot_scene.py` to produce a native `.tscn` referencing the built bundle, and verify all file paths when the candidate is later approved/moved. The runtime supports per-direction component atlas regions, animated parent mounts, normalized playback and nested Node2D inheritance; actual Godot execution, physics, navigation, light/occlusion, and visual regression remain unverified until performed. See `docs/GODOT_COMPONENT_RUNTIME.md`. Keep the user-facing workflow conversational.


## From an approved image to a real asset — nothing special to learn

For **any** game and any selected style, you can say: **“Generate the workshop/vehicle/prop from this approved mockup.”** The framework automatically finds the approved source and its actual image pixels, measures the object's region, creates an internal reference crop, resolves saved style/camera settings, and passes that real crop to the connected image tool when available. A generated master is reviewed against the source before components, sheets and measured atlases are attempted.

This is part of the existing lifecycle and skills; users never edit crop jobs, JSON, pixels or prompts manually. If the image provider cannot accept a reference image, the agent reports that production is blocked rather than returning unrelated art.


## Keep installed Claude/Codex skills current

Say **“Enable automatic Game Arts updates for both Claude and Codex in this game.”** The locally connected agent enrolls that workspace, checks both current skill trees and merges trusted session-start hooks. Once enrolled, each agent session checks for framework updates and synchronizes both agents; no recurring manual copying is needed. Changes made to GitHub are not pushed to PCs while offline. For an immediate refresh inside a currently open local session, say **“Update my installed Game Arts skills now.”** The agent must run the installed updater and verify results, never claim local success from a GitHub commit alone.


## Automatic static-parent cleanup before approval

When you ask **"Make this building/vehicle/scene into separate usable sprites,"** Game Arts now removes all independently moving, removable, interactive, replaceable or animated elements **from the base sprite** while exporting the pieces separately. For example, a workshop is created without the workbench, screws or spanners baked into its interior. This rule applies to every art style, not only pixel art. The agent automatically verifies actual removal before approval, and flags missing evidence or incomplete visual inventory rather than claiming completion. No extra command or manual setup is necessary.
