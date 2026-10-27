---
name: animation-planner
description: Plan animated and stateful art - parts that move, cycle or change state, moving attachment anchors, directions, key poses and component hierarchies. Use when an element moves, needs directions, has animated mounts, or needs frame or key-pose animation.
---

# Animated components and action coverage

Policy: master *Animation candidates and modular components*, *Asset profiles, view and direction classification*, *Sprite sheets, atlases and component bundles*, *Parent-artwork cleanup and separation gate*.

## Plan
Inspect every visible real-world moving or visually changing detail, major, small and ambient. Build an inventory: state IDs, dependencies, timing, constraints, implementation technique (frames, transforms, rig, shader, procedural, hybrid). No hardcoded object classes or frame counts.
- Lock the base master and directional masters first. Frame-based motion: plan key poses (start, extremes, anticipation, recovery, loop seam) and controlled intermediates, never independent whole-scene redraws.
- Split independently moving components and keep unchanged base pixels. The parent/child hierarchy supports animated attachment anchors, direction/action/state/time-dependent position, rotation and scale, nested independent motion, draw order and occlusion.
- If the parent has eight directions every visible moving child needs validated direction-correct art or a demonstrably equivalent direction-correct transform; never borrow mismatched frames. A fixed structure or fixed machine keeps its **one** base view; only its moving components animate.
- Preserve normalized playback phase on a direction change and switch parent, children, pivots, anchors and draw order together.

## Prompt strategy
Never ask an image model for a whole animation sheet. Build from the locked master and separate component layers; prompt one component or one key pose with the real locked image as conditioning: "Edit only [part] to [pose]; keep every unchanged pixel, camera, palette, scale and pivot; do not redraw the parent or invent another view." Hinge and mount positions are measured by you, not produced by a prompt. Derive in-betweens from approved poses by deterministic transforms where sufficient, and check unchanged regions and attachment continuity.

## Build
Use `scripts/build_component_bundle.py` with the approved frame PNGs and artist-verified pivots and anchors (`docs/COMPONENT_ANIMATION.md` has the job format): per-direction sheets and atlases plus `<asset>.bundle.json`. Track rules that matter when planning:
- `mount_tracks` follow the **parent's** action, `motion_tracks` the component's own; a track no action selects fails the build; keyframe times strictly increase in `[0, 1]`.
- Rotation interpolates linearly (a 0 to 360 degree key is a full turn); `rotation_interpolation: "shortest"` is an opt-in.
- Frames are shown by `duration_ms` weights; `draw_order` can differ per direction.
- The builder cannot find physical mount points, create art or certify alignment; engine behavior is the game project's to test.

## Static-parent isolation and review
Animated, detachable, removable, interactive or replaceable parts must be **absent** from the static parent frames, not just repeated in a component sheet; art tools receive the analyzer's explicit excluded-component list. Before approving a component system run the bundle validator with `--approval-gate` and `validate_parent_cleanup.py --strict-props` evidence for every parent, direction and frame. Never animate a door, wheel, boom or prop whose silhouette is still painted into the parent; if no clean plate is approved or layers cannot be aligned, report the blocker. Sources, masks and frames come from the current revision only, never a revoked predecessor.

**Timing of a segment.** For limited animation or weight, a keyframe may set `interpolation` (`linear`, `nearest` to hold, `cubic`) and `easing` (`ease_in`, `ease_out`, `ease_in_out`) for the segment that starts at it (`docs/COMPONENT_ANIMATION.md`; master *Sprite sheets, atlases and component bundles*). Use them only when the person asks for that feel; the default is linear. Name what a run of frames is (`tags`, with how it plays and repeats) when the game or another tool must find it.

**Check and show the motion.** `python scripts/check_animation.py --image <sheet.png> --atlas <sheet.atlas.json> --game-root <game>` reports, per animation, the loop-seam jump, pivot drift, clipping and repeated frames, with limits from the game's preset; it informs and does not block (master *Quality gates and validation grades*). `python scripts/render_preview.py --image <sheet.png> --atlas <sheet.atlas.json> --output-dir <folder> --game-root <game>` draws each animation as a still strip and a looping GIF so the person can see it play; previews are review aids, never art.

Segmentation and occlusion are not proven by valid transforms: for each parent, action and direction include the separated object, the actual pose, the clean background, the attachment alignment and any reconstructed surface in the visual review (`scripts/visual_review_cleanup.py`) and show it to the user before approving the assembled package. An animation preview is for visual QA only; it replaces neither the real sheet and atlas checks nor engine testing.
