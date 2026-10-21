---
name: sheet-atlas
description: Use when assembling or validating final sprite sheets, exact #FF00FF masking, pivots, frame bounds, atlas JSON or attachment metadata.
---

# Deterministic sprite sheet + atlas

Do NOT assume the image model's grid or embedded labels are accurate. Assemble approved individual frames into precisely measured cells using a deterministic script/tool. Choose cells from actual maximum directional/action extents, keep stable pivots and physical scale, avoid clipping and frame drift.

Exact source/export requirements: every delivered PNG uses alpha=255 throughout and exact #FF00FF in unused pixels, no PNG alpha transparency, no backgrounds with gradients or fringes. If masked compositing needs edge-coverage information, preserve it via authorized separate metadata or working intermediate.

For each sheet export a companion JSON with actual canvas width/height, real frame rectangles, directions, frame order/durations, original image dimensions, pivots, trim offsets, source reference and validation. For modular art: named mount on parent, parent-local world coordinates, direction-specific measured frame pixel anchors, component pivots, moving mount transforms keyed by action/state/direction/time, and draw/occlusion metadata. Atlas coordinate space convention must be explicit.

Run `python scripts/validate_sheet_atlas.py <image.png> <atlas.json>` for geometry/pink checks, then visually validate alignment and composition. Script success alone is not proof of artistic or Godot readiness.