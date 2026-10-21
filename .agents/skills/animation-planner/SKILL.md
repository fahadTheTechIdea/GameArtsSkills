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
