---
name: godot-validator
description: Use to inspect and validate generated artwork in Godot, including imports, sorting, animations, scale, collision state and visual regression.
---

# Godot composition validation

When a Godot project and runtime/editor tools are available, validate actual imported graphics: physical footprint vs visual bounds, scale, camera, nearest/linear texture filtering by art profile, chroma key rendering, correct tile adjacency, animated frame playback, nested moving anchors, directions, collision/navigation and light-occlusion updates, Y-sort/z-index layering and interactive states. Compare against approved mockup and locked master; record tested scenes and results.

Never report a pass without running the check. Fail missing frame assets, incorrect anchors, clipping, changed static geometry, illegal alpha/pink masking or invalid atlas rectangles. If Godot is unavailable, mark `not_tested` and give exact reproducible next steps.
## Executable modular moving component implementation (v7.6)

When approved artwork includes separately moving or state-changing parts, do **not** stop at generic atlas metadata. Use `scripts/build_component_bundle.py` internally with the actual approved frame PNGs and **artist-verified parent anchors/pivots** to build individual directional sheets and measured JSON atlases, plus a `.bundle.json` containing the nested component hierarchy and sampled direction/time-dependent mount transforms. See `docs/COMPONENT_ANIMATION.md`. Do not hardcode component types or frame counts. Ensure all required directions and parent mounts exist, validate the generated bundle, and keep it in `assets/generated` pending final approval. The tool cannot infer artwork anchor geometry, create missing animation images, or certify Godot rendering, so never claim those capabilities without separate actual tests.

## Executable component validation

When modular assets are generated, run `scripts/validate_component_bundle.py <bundle-directory>` internally. Require its geometry/attachment structure checks to pass before marking technical file integrity verified. Also test actual rendered motion, color-key masking, collision, z-order and direction transitions in Godot if available. Do not claim Godot tested from JSON checks alone.
