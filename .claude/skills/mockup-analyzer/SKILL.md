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
