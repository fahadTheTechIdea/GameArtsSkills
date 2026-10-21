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