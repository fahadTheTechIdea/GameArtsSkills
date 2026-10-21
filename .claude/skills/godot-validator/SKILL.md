---
name: godot-validator
description: Use to inspect and validate generated artwork in Godot, including imports, sorting, animations, scale, collision state and visual regression.
---

# Godot composition validation

When a Godot project and runtime/editor tools are available, validate actual imported graphics: physical footprint vs visual bounds, scale, camera, nearest/linear texture filtering by art profile, chroma key rendering, correct tile adjacency, animated frame playback, nested moving anchors, directions, collision/navigation and light-occlusion updates, Y-sort/z-index layering and interactive states. Compare against approved mockup and locked master; record tested scenes and results.

Never report a pass without running the check. Fail missing frame assets, incorrect anchors, clipping, changed static geometry, illegal alpha/pink masking or invalid atlas rectangles. If Godot is unavailable, mark `not_tested` and give exact reproducible next steps.