---
name: game-arts-mockup-creator
description: Create, revise, present and stage visually reviewable mockups of whole game worlds, levels/scenes, individual art assets, characters, UI screens and UI flows. Automatically use as first visual production step for new Game Arts designs, with project style and approved references; request explicit approval before final artwork.
---

# Game Arts Mockup Creator

## Automatically triggered when
- The user requests a new scene, environment, sprite, world, character, interface, effect or visual asset and there is not yet an approved mockup/reference for that design.
- The user asks to create, revise, compare, or approve a mockup.
- An existing approved mockup needs a materially changed artistic direction.

## Procedure
1. Discover the target game project. Load its existing `.gamearts/project.json` settings, relevant custom instructions and already-approved references. If no settings exist, use the current approved game-profile defaults for the mockup; ask only genuinely essential missing decisions. Setup is optional, conversational and never a prerequisite to viewing an initial concept.
2. Determine scope from the request: world, scene, individual asset, character, UI screen/flow or mixed. Use the appropriate art-style and asset profiles. Do not impose pixel-art-only techniques on nonpixel styles.
3. Inspect user-supplied reference images. Respect observed design details; never silently replace them with generic objects. For a broad mockup, preserve intended visual hierarchy and provide nested detail mockups where the source cannot reveal fine geometry.
4. **Generate actual reviewable mockup artwork** using a supported image-generation/design tool when connected. Don't merely give a text prompt and claim the image was created. If the agent lacks a capable image-generation tool, say so and offer the concept brief instead without claiming completion.
5. Follow exact opaque `#FF00FF` unused-pixel rules for every exported Game Arts PNG. A fully painted scene mockup can have no unused pixels. Apply the approved art/camera/world presentation rules.
6. Export each actual mockup to the game repository's `.gamearts/outputs/mockups/generated/`, giving it a descriptive `<game>_<scope>_<content>_mockup_vNNN.png` filename. Associate immutable `mockup_id`/revision, candidate metadata, reference provenance, and generated status with `.gamearts/outputs/manifests/mockups.json`; verify saves. No approval is implied by generation.
7. Show the actual preview in the conversation when the platform supports it. Ask plainly: **"Do you approve this mockup, or what should change?"** Do not send a huge questionnaire.
8. When the user asks for revisions, create a new generated revision and show the updated preview; preserve earlier iterations. On explicit approval, invoke `game-arts-lifecycle` to move the exact approved revision and metadata to `mockups/approved/` and update manifests. Rejected/superseded candidates go to `mockups/revoked/`.
9. After approval, invoke `mockup-analyzer` to inspect **all relevant visible geometry, textures, surfaces, small details, components, UI elements and real-world animation candidates**. Produce a nested blueprint where appropriate. Link every planned production asset to the approved mockup ID/revision and relevant blueprint elements.
10. Only then route to the correct production/animation/sheet/atlas/Godot skill. Production assets have a **separate approval** after technical validation.

## Essential user experience
- "Create a city mockup" → generate preview, show, ask approval.
- "Generate a sprite from this image" → show an asset mockup first unless the image is already explicitly approved.
- "Make the street wider" → create revised mockup, show it, ask approval.
- "Approved" → promote *the currently presented identifiable revision*, then decompose automatically.
- "Use my existing approved UI mockup" → reuse it; never make users reapprove the same design.
- Don't require the user to say "activate Game Arts", run a command, read schema files, select a skill or manually move assets.
- If saving fails or tools are unavailable, report honestly and don't mark the lifecycle complete.


## User-supplied / externally generated mockups
A user may supply an existing mockup created outside Game Arts. **Do not regenerate it.** Import a managed **copy** into the target game's mockup lifecycle, preserving the original external source. If the user explicitly confirms this exact revision is already approved, register it directly under `.gamearts/outputs/mockups/approved/`; otherwise register it under `mockups/generated/` and show it for approval. Store source provenance, descriptive versioned filename, ID, hash when available and manifest record. Never claim the import was saved if the agent lacks source access or filesystem permissions. After approval, analyze all its visual details and use that locked reference for production. Any exported Game Arts PNG derivative must comply with exact opaque #FF00FF; preserve nonconforming original external files separately and do not silently alter source pixels.

## Everyday user commands (natural language)

Recognize the complete user-friendly command catalog in `docs/COMMANDS.md`, including: **set up / show / change game settings; add / show custom instructions; create world/scene/character/UI mockups; import an outside mockup; import an already approved mockup; revise / approve / reject mockups; generate production sprites, component animations, and measured atlases; approve / reject / restore assets; show generated/approved/revoked artwork; validate in Godot.** Do not require slash commands or special trigger keywords. Infer intent and invoke the correct skill(s), respecting exact revision identity. An already-approved imported mockup is not regenerated. Ask for approval only when a real new mockup or final asset needs it. Do not claim actions completed without successful tool execution.


## Mandatory actual image prompts — use canonical master prompt packet

Before any image generation or source-conditioned edit, read the **Mandatory reference-controlled image prompting** section of \`GAME_ARTS_MASTER_STANDARD_v7.7.md\`. Compose a precise actual tool prompt from the target approved/draft reference, project style, camera, asset class, identity invariants, allowed change and solid opaque pink export. **Pass the actual source image/crop as image conditioning if supported**; do not pretend written descriptions replace actual image attachments.

For a mockup request, generate a visual *mockup*, not production components. For production based on approved mockups: do not replace the mockup with an unrelated generic visual. If only a large mockup screenshot exists, select/inspect its target region first. If the exact crop can't be made or passed to the tool, explicitly flag diminished reference fidelity rather than asserting the reference was used.

**User-approved mockup import remains authoritative**: do not regenerate it. If already approved, carry the original into approved workflow with provenance.

### Prompt to send for a structure master
"Use the ATTACHED approved mockup crop depicting [specific structure] as the authoritative appearance. Generate ONE fixed-view master only. Match the project's approved camera [projection with explicit NOT-isometric for Oilfield Days], same building silhouette, roof, walls, doors, cladding, colors and pixel-detail scale. No other viewing angle; no door-animation frames, multi-part charts, labels, grids, or example JSON. Exact solid opaque #FF00FF elsewhere."

**Gate:** compare resulting silhouette, approved camera, positions/materials and overall identity before presenting for master approval. Do not proceed to separately animated components until this gate passes. A visually attractive different building fails.


## Selected game settings drive prompt generation (mandatory)
Before **every** image-generation/edit call, read `<game-root>/.gamearts/project.json`, applicable active custom instructions, approved mockup crop/locked master and asset-specific profile. Resolve the exact selected `art_style.id`, `art_style.reference`, style appearance settings (palette/outline/shading/texture/pixel density if present), `world.object_camera`, scale, asset-specific directions, `animation.preferred_method` and `export.*`. **Insert these actual resolved values into the tool prompt, not merely into commentary.** Use the hierarchy and conflict-resolution guidance under "Mandatory saved-settings resolution for EVERY image prompt" in the one canonical master.

Never hardcode Oilfield Days, pixel-art style, oblique projection, an isometric ban, or a direction count in generic prompts. Oilfield Days is a project-specific example, only applicable when that project/style is selected. If settings are missing, use verified approved references, then plainly marked defaults; ask the friendly wizard only for an essential missing choice. Never secretly replace a saved style. Check the actual prompt matches resolved values before sending it, and review the resulting image against the exact project-specific constraints afterward.


## Actual crop before editing approved reference imagery
When a user has supplied/approved a mockup and requests production art, first select the **actual asset region** in its managed approved image and run scripts/prepare_reference_crop.py through available filesystem tools. The script creates a real cropped PNG, source and settings hashes, and a selected-style prompt. Pass that crop as an actual image input if the image tool supports it. **Do not turn a text description of the mockup into a new uncontrolled image generation.** If input conditioning is unsupported, disclose that production cannot yet be reference-locked. A reported tool attachment and matching hashes still require visual similarity review; no automatic approval.
