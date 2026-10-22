---
name: mockup-analyzer
description: Use to analyze approved or candidate whole-world, scene, character, asset, UI screen/flow or mixed mockups and create an exhaustive evidence-grounded production blueprint.
---

# Scope-aware mockup analysis

Treat approved mockups as detailed production sources, not moodboards. For an unapproved mockup label output provisional and do not initiate final production.

1. Identify world, scene, asset, character, ui_screen, ui_flow or mixed scope. Maintain separate coordinate systems (world meters, sprite pixels, UI screen pixels).
2. Record source reference/region for each visible meaningful feature; document materials, silhouettes, repeated patterns, geometry, texture, color, depth, z-order and spatial relationships.
3. Decompose recursively: world → regions → scenes → assets → components; UI flow → screens → UI components and states.
4. Inventory **every real-world motion/state candidate**, including small and ambient details. Provide probable action/state and preferred frame/transform/shader/procedural implementation; do not assume every candidate needs redundant sprite frames.
5. Mark evidence `observed`, `user_specified`, `inferred` or `unknown`. Don't invent hidden geometry; request nested details in the blueprint when needed.
6. Link extracted regions to stable output asset IDs; check every significant region is accounted for or deliberately excluded.
7. Produce a JSON blueprint following `schemas/mockup-blueprint.schema.json` and run `python scripts/validate_blueprint.py <blueprint.json>` if permitted.

Keep approved mockup ID, revision and visual constraints on all downstream assets. Never silently alter approved composition.
## When to launch
Only after mockup approval for definitive asset breakdown. The separate `game-arts-mockup-creator` handles **actual visual mockup generation**, revision, preview, and approval. A provisional analysis may support a pending mockup but is not production authorization.


## Image-prompt grounding output
After analyzing the approved mockup, supply a concise **reference-conditioned prompt packet** per individual asset: actual source image/region, approved revision, observable identity features, unobserved/unknown details, style/camera, asset class and exact view policy, materials and proportions, components and motion candidates, locked elements, allowed changes, output constraints, and validation checks. **Observations must not be silently promoted to inferred hidden geometry.**

For a static structure, define its ONE exact approved camera and prevent redraws of walls/roof during component animation. For mobile assets, list all eight required directions where gameplay requires and describe identical model geometry across directions. Never treat UI icons as interchangeable with world views.


## Provide measured region selection for actual conditioned generation
For every item authorized by an approved scene mockup, identify a source-image bounding rectangle in actual **source pixel coordinates**, and maintain the exact source image, approved revision and style/camera constraints. Record a measured region ID, [x,y,width,height], reasonable context padding, observed identity lock, material/camera notes and unknown hidden features. Feed this into the executable reference crop gate; never invent pixel bounds, refer to arbitrary neighboring objects, or treat tiny UI previews as authoritative world-camera art when a world crop exists.


## Reusable crop-stage handoff

When a user requests production from an approved mockup, return the existing blueprint's exact measured **source-pixel** crop (x,y,width,height), minimal context padding, observed visual identity lock, asset class/profile, approved mockup ID/revision and source image path/hash. The orchestrator uses these as inputs to the existing `scripts/prepare_reference_crop.py`, saving its crop/packet in the current asset candidate's `reference/` subfolder. Do not manually crop an altered color-key version, invent bounding boxes, or create a new lifecycle. UI/terrain/world assets use their individually selected camera and style settings.


## Universal ownership inventory — every independent object

In each approved mockup, classify major AND tiny details as permanent/inseparable parent artwork versus **movable, removable, interactive, replaceable or animated components**. Furniture, workbenches, individual tools, screws, cabinets and props can be separate even if they have no moving animation; similarly for vehicle doors/wheels and industrial machinery. Do not exclude small elements due to perceived insignificance.

Before master generation, produce the complete `separation_inventory` and `parent_cleanup` blueprint evidence fields: each component's ID, classification, observed source position, intended independent sprite, owned removal-mask region, and the background/inner surface revealed when removed. The **static master prompt excludes each such component**. The producer then verifies none remains baked into the parent. Treat undisclosed hidden backgrounds as unknown pending separate reference/review. Do not mark decomposition complete solely because a separate object sprite was produced.


## Workshop-derived exhaustive separation & inferred-pixel inventory (all styles)
Before generating the parent, inventory small objects **separately** even when they overlap: workbenches, toolboxes, cabinets, spanners, nuts, bolts, doors, wheels, lights, and any independent detail appropriate to this asset (list derived from real image, not hardcoded). For each candidate describe its visible extent, exact silhouette/ownership mask, removal region, parent layer, occluded surfaces, source-observed versus inferred pixels, game-dependent interactivity and intended output. Do not treat an object’s rectangular bounding box as its silhouette. No source-derived image may be called fully observed if part is behind another object. Pass this inventory and clean-plate requirements before any static-master prompt.


## Independent second-pass object/occlusion audit

Pixel-based masks cannot tell whether the producer forgot a screw, cabinet, wheel, small tool or separable structure part. Re-inspect the ORIGINAL approved image/crop independently of the candidate components, record a complete expected component ID inventory, and compare it to the actual detached component manifests. Inspect where each removed object hid underlying wall/floor/tabletop/mechanism pixels; classify reconstructed regions as `inferred`, `partially_observed` or `unknown`, with source-aligned binary region masks and reasons. Even an empty uncertainty list requires an explicit completed occlusion audit. Pass this evidence as internal `review_spec` to the existing visual review helper; do not mark inferred pixels source-verified.

Present the original/source + each isolated sprite side by side with the reconstructed clean plate for actual human review. A silhouette mask automatically extracted from the very same contaminated sprite is not independent evidence.
