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
