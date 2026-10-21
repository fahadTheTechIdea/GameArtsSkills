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