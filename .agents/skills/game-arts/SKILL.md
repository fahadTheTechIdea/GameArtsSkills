---
name: game-arts
description: Use for any creation, transformation, review, mockup, sprite, sprite sheet, game UI, world/scene art, terrain, character, effect, animation, atlas or Godot game-art task.
---

# Game Arts orchestrator

1. Read `GAME_ARTS_MASTER_STANDARD_v7.7.md` at the repository root. Treat the master as authoritative; avoid filling gaps by guessing.
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

Read the current master standard and invoke the `game-arts-lifecycle` skill for generation staging, mockup/asset approval, rejection, revocation, replacement, restoration and listing. Use separate `<game>/.gamearts/outputs/mockups/{generated,approved,revoked}` and `<game>/.gamearts/outputs/assets/{generated,approved,revoked}` stores plus linked manifests. Every final asset references its exact **approved mockup revision** and blueprint region IDs. Use unique descriptive game-related versioned filenames, keep companion PNG/JSON/metadata together, and never silently overwrite or delete a revoked version. **No user-facing CLI or manual folder management.** Never claim approval without explicit user approval and verified file transitions.

## Automatic, user-friendly Game Arts behavior (v7.4)

When the user opens a game project and asks for art normally, **apply Game Arts automatically** using the project-root instructions. Quietly load the relevant `.gamearts/project.json`, active scoped `.gamearts/instructions/*.md` and approved mockup/asset manifests as needed; invoke specialist skills only for the actual task. **Do not require "initialize", "load Game Arts", command-line setup, special phrases or manual skill selection.** If settings are absent, use known approved defaults for preliminary work and ask one simple question only if an essential decision is missing. Do not repeat saved choices or demand approval again for unchanged accepted mockups. Keep storage, naming, manifests, JSON and tool operations behind the scenes. Ask only for meaningful design/approval decisions; verify files before reporting success. The user workflow is simply **open project → ask for art → approve when needed**.

## Connected Game Arts workflow (v7.5 — mandatory)

The user can simply ask for artwork. **Do not collapse the complete experience into “auto-load Game Arts.”** At the start of each relevant task, quietly read applicable saved project configuration, active custom instructions, and approved mockup/asset references. If the user expressly asks to configure or modify preferences, route to the short in-chat `game-arts-project-setup` wizard; never ask for command-line steps. Missing optional settings must not block an initial mockup.

For a **new visual design** without an applicable approved reference, invoke `game-arts-mockup-creator` to render and show an actual mockup using available image tools, save it in `mockups/generated`, and request explicit visual approval or revision. Do not claim a rendered preview if only text was produced. On approval, invoke `game-arts-lifecycle` to promote the exact revision, then `mockup-analyzer` to extract every relevant detail, geometry, texture, object, UI element, movement and animation candidate into a linked blueprint. Generate reference-conditioned masters, component and animation art, deterministic sprite sheets with measured JSON atlases, and validate the assembled result. Save candidate output in `assets/generated` and **request separate final asset approval** before promoting the complete bundle to `assets/approved`. Rejected/replaced revisions go to their respective `revoked` locations. Reuse already approved references without repeating approval.

For user-defined lasting preferences, route to `game-arts-custom-instructions`; do not confuse one-off requests with lasting rules. Keep all underlying files and specialized skills invisible unless asked. For a complete decision table see `docs/USER_WORKFLOW.md`. Ask meaningful design/approval questions only, with sensible defaults. No setup ritual or special activation phrase.


## User-supplied / externally generated mockups
A user may supply an existing mockup created outside Game Arts. **Do not regenerate it.** Import a managed **copy** into the target game's mockup lifecycle, preserving the original external source. If the user explicitly confirms this exact revision is already approved, register it directly under `.gamearts/outputs/mockups/approved/`; otherwise register it under `mockups/generated/` and show it for approval. Store source provenance, descriptive versioned filename, ID, hash when available and manifest record. Never claim the import was saved if the agent lacks source access or filesystem permissions. After approval, analyze all its visual details and use that locked reference for production. Any exported Game Arts PNG derivative must comply with exact opaque #FF00FF; preserve nonconforming original external files separately and do not silently alter source pixels.

## Everyday user commands (natural language)

Recognize the complete user-friendly command catalog in `docs/COMMANDS.md`, including: **set up / show / change game settings; add / show custom instructions; create world/scene/character/UI mockups; import an outside mockup; import an already approved mockup; revise / approve / reject mockups; generate production sprites, component animations, and measured atlases; approve / reject / restore assets; show generated/approved/revoked artwork; validate in Godot.** Do not require slash commands or special trigger keywords. Infer intent and invoke the correct skill(s), respecting exact revision identity. An already-approved imported mockup is not regenerated. Ask for approval only when a real new mockup or final asset needs it. Do not claim actions completed without successful tool execution.

## Working sheet and atlas generator

When approved source frames exist and a sprite sheet is requested, invoke the `sheet-atlas` skill and have the agent run `scripts/build_sheet_atlas.py` internally, then `scripts/validate_sheet_atlas.py`. This creates **real** native-scale opaque pink PNG sheets and companion measured JSON atlases. Save the pair together in the game project's generated asset bundle and request approval. See `docs/ATLAS_GENERATION.md`. The builder transforms **provided** pivot and anchor data into cell coordinates; it does not infer physical mount points or certify visual/Godot readiness. Never claim atlas generation unless files were actually written and checked. Users do not need to run commands.

## Executable modular moving component implementation (v7.6)

When approved artwork includes separately moving or state-changing parts, do **not** stop at generic atlas metadata. Use `scripts/build_component_bundle.py` internally with the actual approved frame PNGs and **artist-verified parent anchors/pivots** to build individual directional sheets and measured JSON atlases, plus a `.bundle.json` containing the nested component hierarchy and sampled direction/time-dependent mount transforms. See `docs/COMPONENT_ANIMATION.md`. Do not hardcode component types or frame counts. Ensure all required directions and parent mounts exist, validate the generated bundle, and keep it in `assets/generated` pending final approval. The tool cannot infer artwork anchor geometry, create missing animation images, or certify Godot rendering, so never claim those capabilities without separate actual tests.

## Godot runtime component support (v7.7)

For approved nested moving-part bundles, use the reusable `godot/addons/gamearts/game_arts_component.gd`, `.tscn` and `chroma_key.gdshader` in the target game's `res://addons/gamearts/` folder where integration is requested. Internally invoke `scripts/generate_godot_scene.py` to produce a native `.tscn` referencing the built bundle, and verify all file paths when the candidate is later approved/moved. The runtime supports per-direction component atlas regions, animated parent mounts, normalized playback and nested Node2D inheritance; actual Godot execution, physics, navigation, light/occlusion, and visual regression remain unverified until performed. See `docs/GODOT_COMPONENT_RUNTIME.md`. Keep the user-facing workflow conversational.


## Permanent asset view and direction classification

**Before generating artwork, classify the asset by gameplay behavior and use the game-approved art style and projection consistently.** Never generate additional angles solely because the framework can support them.

| Asset class | Default views | Moving components |
|---|---|---|
| Static structure or fixed building | **One** locked, approved world-facing view | Separate frame-based or transform-animated parts as applicable; the static master does not rotate |
| Fixed machinery or permanently installed industrial equipment | **One** locked, approved world-facing view | Animate arms, linkages, valves, flame, doors, etc. independently as appropriate |
| Mobile object, vehicle or free-facing actor | **Eight** coherent directions (S, SW, W, NW, N, NE, E, SE) when gameplay supports directional movement or facing | Correct direction-specific components and applicable actions; preserve model identity and physical scale across views |
| UI icon, portrait or presentation graphic | **One** UI-optimized view unless UI behavior requires otherwise | UI-specific states/effects; don't reuse world camera assumptions |

A fixed asset may explicitly require a **limited rotation set** for placement or an interactive turning assembly; then use only its actual approved orientation set (e.g., 2 or 4) without forcing eight. Conversely, a mobile asset whose gameplay supports free directional travel uses the full eight-direction package and synchronized moving attachments. A fixed installation's independently rotating arm or turret is not grounds for rotating its entire base or rebuilding all eight static views.

For every asset, record `asset_class`, `view_policy`, `directions`, `approved_view_reference`, `rotation_requirements`, and independently animated `components` in its production blueprint/manifest. A valid single-view bundle must include exactly that one declared direction for all relevant components; validators must derive coverage from the declared profile, **not demand eight directions from a structure**. Only generate directions verified necessary for gameplay.

**Appearance lock:** Across any genuinely required directions, keep structure/model identity, geometry, materials, wall/door/window layout, proportions, scale, palette, component attachment logic and pixel density consistent. A different angle is not permission to redesign the object. Do not include labels, grids, diagrams, or example JSON inside actual production sprite PNG sheets. Measured metadata lives in separate JSON files.

**Oilfield Days defaults:** workshop, cabins, warehouses, fuel farm, separators, pumpjacks and flare stacks use a single approved top-down-oblique world angle (with independent door/linkage/flame animation); freely moving trucks, forklifts and mobile construction equipment use eight direction masters and applicable action sheets; fleet thumbnails, build-menu icons and dispatch portraits are separate UI presentation resources.

**Repository maintenance rule:** Update the current existing canonical master standard **in place** and update existing README, skills, instructions, validator contracts and documentation as needed. **Do not create another version-numbered master document or duplicate guidance file for routine changes.** Preserve previous sections and amend the current file rather than producing a parallel version.


## Required generation prompting preflight
**Do not send generic image requests or ask the generator to draw complete annotated sprite sheets.** Read the master section **Mandatory reference-controlled image prompting** before every actual image tool call and route to art-profile/mockup-analyzer/animation-planner as needed. Create a prompt packet anchored to a real approved crop/image, its locked style/projection, model identity, precise one-step output, allowed-change mask and view policy. Pass the actual reference image to the image-generation/editing tool when supported; never merely say "based on the mockup" while generating without its pixels. Classify outputs as mockup, master, component/key pose, or measured production artifact.

**Serial gates:** master first → compare against approved crop → approve master → isolate components → controlled key poses → deterministic composition → measured JSON atlas. In image prompts prohibit isometric drift for approved oblique styles, multiple angle views for static structures, changing unchanged parent pixels, embedded atlas text, arbitrary frame diagrams and invented unseen details. An image-generated contact sheet is **not** a validated sprite sheet.

For a failed image, do not retry the same vague prompt. Explain the objective mismatch, restore/keep approved master, constrain the tool with the real source crop, and retry only with a more precise allowed-change instruction. If actual source-conditioned image access is unavailable, disclose before generation rather than falsely claiming production fidelity.


## Selected game settings drive prompt generation (mandatory)
Before **every** image-generation/edit call, read `<game-root>/.gamearts/project.json`, applicable active custom instructions, approved mockup crop/locked master and asset-specific profile. Resolve the exact selected `art_style.id`, `art_style.reference`, style appearance settings (palette/outline/shading/texture/pixel density if present), `world.object_camera`, scale, asset-specific directions, `animation.preferred_method` and `export.*`. **Insert these actual resolved values into the tool prompt, not merely into commentary.** Use the hierarchy and conflict-resolution guidance under "Mandatory saved-settings resolution for EVERY image prompt" in the one canonical master.

Never hardcode Oilfield Days, pixel-art style, oblique projection, an isometric ban, or a direction count in generic prompts. Oilfield Days is a project-specific example, only applicable when that project/style is selected. If settings are missing, use verified approved references, then plainly marked defaults; ask the friendly wizard only for an essential missing choice. Never secretly replace a saved style. Check the actual prompt matches resolved values before sending it, and review the resulting image against the exact project-specific constraints afterward.


## Mandatory executable reference crop gate (before IMAGE TOOL CALL)
For a production image derived from a managed approved mockup, require a **real crop** using scripts/prepare_reference_crop.py; do not merely cite the mockup in the text prompt. Agent determines the actual source-pixel asset region, reads the registered approved mockup (ID, revision, path, hash) in mockups.json and selected .gamearts/project.json settings, and prepares the candidate reference packet/prompt. **Attach the resulting PNG crop as a real image input** to the image-generation/editing tool when it supports image conditioning. If image tool cannot accept source images, report a production blocker rather than generating generic concept art as a game-ready asset.

After calling the tool, record actual invocation/crop/candidate hash evidence and validate via the script's verify action. The receipt is only agent-reported, not independently provider-attested. Compare output against exact source crop **visually** (view angle, silhouette, identity, colors, roof, door and detail positions); a technically valid receipt never means production approved. Only then ask approval for the locked static master. For animation use separated component artwork and deterministic builders later. No text labels/grids/fake JSON or independent redraws. See executable crop gate section in canonical master. Run technical operations internally without user CLI.


## Built-in cross-project reference-crop stage (mandatory for reference-locked production)

This stage is **part of the existing asset workflow** and runs automatically for any game whose approved mockup is being turned into production artwork. Do not add new image-type folder trees or make the user prepare JSON/coordinates/commands.

1. Read the installed Game Arts scripts (the package must contain `scripts/prepare_reference_crop.py` and Pillow). If only skill text was copied and the helper is missing, restore/sync the framework package using permitted filesystem operations; if unavailable, disclose blocked preparation, not pretend the stage ran.
2. Reuse the current `mockup-analyzer`: inspect the selected approved mockup and **measure** the target asset's source-pixel bounding rectangle. Reuse the current `game-arts-lifecycle` to read/verify the exact approved mockup ID, revision, managed path, and SHA256 in `mockups.json`. Do not fabricate an approval or source hash.
3. Resolve `.gamearts/project.json`, active applicable instructions and asset-specific profile. Compose the internal crop job for `prepare_reference_crop.py`. Run it **internally** into `<game>/.gamearts/outputs/assets/generated/<asset-revision>/reference/`. The generated source crop is ordinary reference content with its original colors, not an opaque pink sprite.
4. Use the generated **actual PNG reference image** as image input to the selected image/edit tool when it supports conditioning, plus the resolved prompt packet. A string filename in the prompt is not image attachment. For UI use the UI profile view, for ground tiles the ground view/grid, for structures the fixed approved object view, for mobile assets the correct approved directional policy.
5. Only after a real tool call, record truthful source/candidate/tool receipt facts and invoke the helper's verification. Receipt is **agent-reported**, not proof of provider-side conditioning. Review the resulting artwork against the cropped reference. Reject perspective/identity drift; do not approve or start component/atlas production until the master passes review.
6. Continue the **existing** stages: locked master → components/key poses → actual PNG sheets/atlas JSON → separate production approval. Keep all dependencies linked to the same candidate.

Net-new conceptual mockups go through mockup creation and approval first; this approved-source gate must not block initial concept previews.


## Mandatory universal clean static-parent generation and verification

After mockup approval and exhaustive decomposition, **before producing a static/master image**, classify every visible independently movable, removable, interactive, replaceable and animated element. Include small furniture, workshop tools, screws, spanners, wheels, doors, swappable equipment, and other independent props when present. This applies to **all selected art media**, never just pixel art.

In the **actual image/editing tool prompt**, explicitly enumerate all blueprint-derived detached objects and instruct that **none may appear in the clean parent image**, even when each object also has a separate PNG. Produce/review the empty/clean background plate behind each object, without holes or arbitrary repainting. A static parent must consist solely of approved permanent/nonseparable art. Child assets are generated separately and must not be duplicated in the parent.

Before **final production approval**, run `scripts/validate_parent_cleanup.py` for each relevant standalone static parent, or `scripts/validate_component_bundle.py --approval-gate` for every composite rig. The existing bundle builder accepts `detached_inventory` and `parent_cleanup_evidence`; candidates without proof remain `pending`. Validate every parent/frame/direction and real atlas source-frame hash; include independently packaged props in the inventory. Also visually review inventory completeness, clean plate and approved camera/style. **Technical pixel checking cannot find objects absent from the declared inventory**, so never claim automatic artistic certification.

If the gate fails, reject/revise the static master; generating an extra sprite sheet is NOT remediation when the same objects remain painted inside it. Follow the canonical master section "Permanent universal parent-artwork cleanup and separation gate".


## Mandatory revoked/rejected asset exclusion (automatically enforced)

**Before EVERY reference lookup, generated-candidate continuation, image tool call or production operation**, use the existing lifecycle manifest and the executable `scripts/gamearts_asset_lifecycle.py` to select **only eligible records**. Production source mockups and source assets must be `approved`; the current in-progress revision must be `generated` and not `visual_review: rejected`. **Do not read/compose/regenerate from `revoked` candidates**, even if their files remain for history. A rejected/superseded candidate is not active merely because its former PNG path is still accessible.

**When the user explicitly rejects an image, asset, or revision**, route the precise ID/revision to `game-arts-lifecycle` and internally run the helper's `revoke` operation, with the recorded rejection reason. This validates bundle completeness, physically moves the entire managed version from generated/approved to `assets/revoked` (or `mockups/revoked`), backs up the manifest, updates its status/reason/path, and checks the transition. Never leave a clearly rejected candidate in `generated` with only a `visual_review: needs_revision` note, then silently reuse it. **Use exact revision identity** and do not mutate unrelated approved mockups or the next generated revision.

A different generated revision awaiting approval is **not automatically rejected** because an earlier revision was rejected. It stays in `generated`, never silently becomes `approved`. Do not continue toward final assets if a required master/clean plate has been rejected or remains unapproved.

The agent performs lifecycle actions using tools and verifies files; no user CLI or manual JSON required. If filesystem access is missing or errors occur, report the rejection intent and unsuccessful transition; do not claim that a revocation was persisted.


## Workshop-proven preflight and acceptance gates (ALL art profiles)
Before generating a single production parent image, load selected style/camera, exact approved mockup crop and manifest, then build a complete source-grounded inventory of **all independently movable, removable, interactive, replaceable or animated parts**. Require the clean parent image exclude every inventoried element. Crop-to-bounding-box does not isolate a sprite. Use independently reviewed per-object silhouette masks (source pixels) and check exports with \`scripts/validate_parent_cleanup.py --strict-props\` for newly produced standalone parents; for rigs use \`scripts/validate_component_bundle.py --approval-gate\`. A failing or unverified mask cannot produce an approved artwork claim.

When the source hides a tabletop, back wall, cabinet side, or similar surface, mark the reconstructed pixels as **inferred** and obtain clean-plate visual approval; include accepted caveats in final metadata. Reject unconditioned camera/style drift. Do not use revoked predecessor artwork in current generation or QA; a new candidate must be self-contained and tied only to actual approved source ID/revision/hash.

After user approval, **audit** the actual approved asset with \`scripts/gamearts_asset_lifecycle.py audit\` and reconcile any contradictory status in blueprint/QA/manifest. A manifest marked approved while blueprint says generated, production not granted, or visual review pending is a blocking inconsistency. Do not falsely promote Godot/runtime/scale to tested. The user need only decide real artistic matters, not repeat approvals already granted.


## Mandatory human-verifiable extraction review — new production

After cleanup and strict per-sprite masks, **do not equate pixel passes with semantic correctness**. The existing mockup analyzer must independently audit the original approved crop for all separate object IDs and any hidden/inferred surfaces; a list copied from generated sprites is not an independent inventory. With selected game style and the current non-revoked candidate, run `scripts/visual_review_cleanup.py prepare` internally against that candidate's cleanup manifest and analyzer-produced review spec. Render/display the before/after/plate/mask/uncertainty board and the original-versus-isolated-props board. Invite **one coherent explicit visual review** of actual silhouettes, inventory and highlighted inferred reconstruction, and do not invent user acceptance.

When and only when the user approves the exact displayed asset revision, record the actual user message reference (when available), complete accepted part/uncertainty IDs and packet hash in the decision. Verify with `scripts/visual_review_cleanup.py verify`. Bind each newly approved composite asset to `visual_review_protocol: "review_packet_v1"` and `visual_reviews` paths in its existing asset manifest. Run the lifecycle `audit` after promotion; it blocks reuse if reviewed source art, preview boards, masks, or decision evidence changed. No user CLI; do not claim the metadata independently attests a user action. Rejected or changed artwork needs new review. Existing user-approved legacy assets remain approved, with their original limitations.


## Finalize exact artwork acceptance through executable approval transition

For a **newly generated** asset that the user has explicitly approved, do not just move its folder and write optimistic JSON. Use `scripts/gamearts_asset_lifecycle.py approve` **internally**, supplying the exact generated asset ID and a truthful reference to the actual user approval message. For composite artwork, the helper requires the current source/blueprint's visual-review protocol and a valid packet/decision binding to the exact user-reviewed sprites, clean plate and uncertainty list. The helper reconciles blueprint/QA visual states, copies full bundle into approved, records final-art hashes, checks original source provenance and immediately runs the existing lifecycle `audit`. It attempts rollback if the audit fails. A local user-approved artwork is not automatically engine-tested; preserve `Godot: not_tested` and uncalibrated scale. Never fabricate a user decision or run the approval step before the user actually approves. Old approved artwork remains accepted unless explicitly revoked.
