---
name: animation-planner
description: Use when a game-art element moves, cycles, changes state, has moving anchors, needs directions, or requires frame/key-pose animation.
---

# Animated component and action coverage

Inspect *all* visible real-life moving or visually changing details: major, small and ambient. Build an inventory with state IDs, movement dependencies, timing, constraints and visual implementation technique. Do not hardcode object classes or frame counts.

- Lock base/master reference and directional master art first.
- When frame-based, plan key poses (start, extremes, anticipation, recovery, loop seam as needed) and controlled intermediates rather than independent whole-scene redraws.
- Split independently moving components; preserve unchanged base pixels.
- Parent/child hierarchy supports animated attachment anchors, direction/action/state/time-dependent position/rotation/scale, nested independent motion, rendering order and occlusion.
- If parent requires eight directions, EVERY visible moving child needs validated correct rendering in those eight directions or a demonstrably equivalent direction-correct procedural/transform method. Do not borrow mismatched frames.
- Preserve normalized playback phase on direction changes; update base, children, pivots, anchors and z-order atomically.
- Generate per-action/per-direction frame sheets according to the approved profile, each with an individually measured atlas JSON.
## Executable modular moving component implementation (v7.6)

When approved artwork includes separately moving or state-changing parts, do **not** stop at generic atlas metadata. Use `scripts/build_component_bundle.py` internally with the actual approved frame PNGs and **artist-verified parent anchors/pivots** to build individual directional sheets and measured JSON atlases, plus a `.bundle.json` containing the nested component hierarchy and sampled direction/time-dependent mount transforms. See `docs/COMPONENT_ANIMATION.md`. Do not hardcode component types or frame counts. Ensure all required directions and parent mounts exist, validate the generated bundle, and keep it in `assets/generated` pending final approval. The tool cannot infer artwork anchor geometry, create missing animation images, or certify Godot rendering, so never claim those capabilities without separate actual tests.


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


## Animation prompt strategy (must be used)
Never request a whole multi-frame animation sheet from an image model as the authoritative final output. Build from a **locked master** and separate component layers. For each independently moving part, prompt a single component or one key pose using the real locked image(s) as conditioning: "Edit only [part] to [pose], preserve all unchanged static pixels, camera, palette, scale and pivot; do not redraw the parent or invent another view." Parent mount and hinge positions must be measured/verified; a natural-language prompt cannot produce trustworthy coordinates.

For static buildings and fixed machinery, generate animation only for moving components while the base remains a **single approved view**. For mobile objects, maintain coherent eight-direction base and corresponding moving-component coverage. Select actions dynamically; no global fixed animation count. Derive interpolated frames from approved poses using deterministic image transforms where sufficient. Validate unchanged regions and attachment pose continuity.


## Static-parent content isolation — all art styles

When planning animated, transformable, detachable, removable, interactive or replaceable parts, REQUIRE their actual art be **absent from static parent frames**, not merely repeated in an exported component sheet. Keep a clean shell/housing/floor/mount and separate each independent object. This applies to pixel, painted, vector, illustrated and rendered source media alike. Art tools need an explicit **excluded-components list** from the mockup analyzer in their actual prompts, and all source/parent layers must use compatible native scale and pivots.

Before approving a component system, check each parent/direction/frame with `validate_parent_cleanup.py` and the bundle validator's `--approval-gate`; verify declared removal masks, approved clean background and atlas source parent hash. Do not animate a door/wheel/boom/prop while its original silhouette remains baked into the parent. If a clean plate is not approved or layers cannot be pixel-aligned, report blocking evidence rather than fake a pass.


## Frame and parent-source integrity after the workshop test
Produce animation frames from locked master/component art; validate every frame is distinguishable where motion is expected and attachments remain fixed or keyframed in the declared coordinate space. An independently animated door cannot remain painted in the parent shell; similarly independent tools cannot be duplicated in the floor. The source master, exclusion masks and all approved frame/atlas files must come from the **current** revision, with no implicit imports from a revoked predecessor. The animation preview is for visual QA, not a substitute for real sheet/atlas tests or engine testing. A clean background inferred behind a moving part must be marked and reviewed before final art approval.


## Visually review composite moving components before locking them

Even with valid frame dimensions and static-pixel masks, independently moving doors/arms/wheels can be incomplete or incorrectly segmented. For each relevant parent/action/direction, include the separated source object, actual independent pose, clean background, attachment alignment and any reconstructed surfaces in the visual review evidence. Use the existing `scripts/visual_review_cleanup.py` on cleanup manifests (group panels when appropriate), then present the review to the user before approving the assembled component package. Do not equate a successful component transform matrix with correct foreground segmentation or occlusion.
