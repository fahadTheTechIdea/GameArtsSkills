---
name: mockup-analyzer
description: Analyze an approved or candidate world, scene, asset, character, UI screen, UI flow or mixed mockup into an evidence-grounded production blueprint - scope, inventory of every visible detail and separable object, animation candidates, reference-crop regions and the independent review inventory.
---

# Mockup analyzer

Policy: master *Mockup scope classification and decomposition*, *Blueprint and evidence contract*, *Animation candidates and modular components*, *Parent-artwork cleanup and separation gate*, *Human-verifiable silhouette and reconstructed-background review*. Treat an approved mockup as a detailed production source, not a moodboard. Analysis of an unapproved mockup is provisional and starts no production. Launch after approval; creating the mockup is `game-arts-mockup-creator`.

## Procedure
1. Identify the scope (world, scene, asset, character, ui_screen, ui_flow, mixed) and keep separate coordinate systems (world meters, sprite pixels, UI screen pixels).
2. Record a source region for every meaningful feature: materials, silhouettes, repeated patterns, geometry, texture, colour, depth, z-order, relationships. Decompose recursively (world -> regions -> scenes -> assets -> components; UI flow -> screens -> components and states) with nested blueprints that reference their parents.
3. Inventory every real-world motion or state candidate, small and ambient too, with the probable states and a recommended implementation; not every candidate needs redundant frames.
4. Mark evidence `observed`, `user_specified`, `inferred` or `unknown`. Never invent hidden geometry or promote an observation to an inference; return `needs_mockup_detail` when resolution cannot support extraction.
5. Link each region to stable output asset IDs; account for or deliberately exclude every significant region (coverage audit).
6. Write the blueprint to `schemas/mockup-blueprint.schema.json` (`schema_version` "1.0") and run `python scripts/validate_blueprint.py <blueprint.json>`; a missing validator package is a failure, not a pass.
7. Keep the approved mockup ID, revision and visual constraints on every downstream asset; never silently alter the approved composition.

## Ownership inventory (before any master is generated)
Classify every major and tiny element as permanent static parent versus movable, removable, interactive, replaceable or animated. Furniture, workbenches, tools, screws, cabinets and props can be separate with no animation at all; so can doors and wheels. Derive the list from the real image, never from habit. Produce `separation_inventory` and `parent_cleanup` blueprint fields: each component's ID and class, observed position, intended sprite, owned removal-mask region and the surface revealed when it is removed. The static-master prompt excludes every one of them. Treat undisclosed hidden background as unknown pending a reference or review.

## Per-asset prompt grounding
For each asset give the reference-conditioned packet inputs: source image and region, approved revision, observed identity features, unknown details, style and camera, asset class and its view policy (one view for static structures and fixed machinery; the selected direction set for mobile assets; UI is separate from world views), materials, proportions, components and motion, locked elements, allowed changes, output constraints and checks.

## Reference-crop handoff
Return the measured **source-pixel** region `[x, y, width, height]` with a region ID, minimal padding, the identity lock, asset class and profile, and the approved mockup ID, revision, path and hash. These feed `scripts/prepare_reference_crop.py`; never invent bounds, crop a colour-keyed copy, or use a tiny UI preview as world-camera art. UI, terrain and world assets use their own selected camera.

## Independent second pass (required for composite assets)
Pixel masks cannot tell that a screw, cabinet, wheel or small tool was forgotten. Re-inspect the ORIGINAL approved crop independently of the candidate's components, write the complete expected component ID list, and compare it with the actual detached manifests. For each removed object inspect which wall, floor, tabletop or mechanism it hid; classify reconstructed areas `inferred`, `partially_observed` or `unknown` with a source-aligned binary mask and a reason. Even an empty uncertainty list needs a completed occlusion audit. Hand this over as the review spec (`schemas/gamearts-review-spec.schema.json`) to `scripts/visual_review_cleanup.py`. A silhouette taken from the contaminated sprite itself is not independent evidence; a human reviews the original beside each isolated sprite and the reconstructed plate.
