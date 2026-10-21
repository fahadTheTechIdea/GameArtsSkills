---
name: sheet-atlas
description: Use when assembling or validating final sprite sheets, exact #FF00FF masking, pivots, frame bounds, atlas JSON or attachment metadata.
---

# Deterministic sprite sheet + atlas

Do NOT assume the image model's grid or embedded labels are accurate. Assemble approved individual frames into precisely measured cells using a deterministic script/tool. Choose cells from actual maximum directional/action extents, keep stable pivots and physical scale, avoid clipping and frame drift.

Exact source/export requirements: every delivered PNG uses alpha=255 throughout and exact #FF00FF in unused pixels, no PNG alpha transparency, no backgrounds with gradients or fringes. If masked compositing needs edge-coverage information, preserve it via authorized separate metadata or working intermediate.

For each sheet export a companion JSON with actual canvas width/height, real frame rectangles, directions, frame order/durations, original image dimensions, pivots, trim offsets, source reference and validation. For modular art: named mount on parent, parent-local world coordinates, direction-specific measured frame pixel anchors, component pivots, moving mount transforms keyed by action/state/direction/time, and draw/occlusion metadata. Atlas coordinate space convention must be explicit.

Run `python scripts/validate_sheet_atlas.py <image.png> <atlas.json>` for geometry/pink checks, then visually validate alignment and composition. Script success alone is not proof of artistic or Godot readiness.
## Executable builder — mandatory
The repository now includes **`scripts/build_sheet_atlas.py`**, which creates a real sprite-sheet PNG and companion measured JSON atlas from existing approved individual source frame PNGs, rather than merely describing an output.

When a production request requires a sprite sheet:
1. Gather the actual approved source frames from the target game, preserving pixel-art/style rules and exact opaque #FF00FF.
2. Make a builder job manifest with descriptive game-related name, source frame paths, direction/action, chosen columns, per-frame source pivots and verified named attachment points if applicable. Read `docs/ATLAS_GENERATION.md` for the job format. Do not invent anchor measurements.
3. Invoke `scripts/build_sheet_atlas.py` **internally** using your available command/file tools. Never ask normal users to run the script.
4. The builder arranges native-sized frames on canonical pivots, writes opaque #FF00FF output PNG, and writes real frame rectangles, source offsets, transformed frame anchors, timing and hashes into the matching `.atlas.json`.
5. Use `scripts/validate_sheet_atlas.py` and additional checks; evaluate full image visual fidelity, directional coverage, and nested animated mount transforms in the Godot preview when available.
6. Store both outputs as one candidate bundle inside the target game's `.gamearts/outputs/assets/generated/`. Obtain final approval before lifecycle promotion to approved.
7. If the agent cannot execute the builder or frames are unavailable, state that the atlas **was not generated** and explain the blocker. Do not fabricate coordinates or pretend a successful build.
8. Source-frame anchors are **supplied and transformed**, not automatically inferred from image content. Mark anchor or Godot validation unverified until actually checked.

For complete examples see `docs/ATLAS_GENERATION.md`. 
