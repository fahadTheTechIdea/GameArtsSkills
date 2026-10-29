# Modular moving components

[`scripts/build_component_bundle.py`](../scripts/build_component_bundle.py) builds (with `--game-root <game>` it also says whether the bundle faces the game's directions), for every component and direction, a sprite sheet and measured atlas, plus one `<asset>.bundle.json` with the hierarchy, tracks, draw order and sampled composed transforms. The agent runs it internally. The rules are in the master standard: *Animation candidates and modular components*, *Sprite sheets, atlases and component bundles*, *Parent-artwork cleanup and separation gate*.

## Job
Contract: [`schemas/gamearts-component-job.schema.json`](../schemas/gamearts-component-job.schema.json). Illustrative paths and numbers:

```json
{
  "name": "mygame_dynamic_structure_v001",
  "directions": ["S", "E"],
  "sample_times": [0, 0.5, 1],
  "source_mockups": [{"mockup_id": "scene-001", "revision": "v003"}],
  "components": [
    {"id": "base", "parent": null,
     "views": {"S": {"frames": [{"file": "base_s.png", "pivot": [16, 24], "anchors": {"joint": [18, 12]}}]},
               "E": {"frames": [{"file": "base_e.png", "pivot": [16, 24], "anchors": {"joint": [22, 14]}}]}}},
    {"id": "part", "parent": "base", "mount": "joint", "parent_action": "open", "draw_order": {"*": 1},
     "views": {"S": {"frames": [{"file": "part_s.png", "pivot": [4, 10]}]},
               "E": {"frames": [{"file": "part_e.png", "pivot": [4, 10]}]}},
     "mount_tracks": {"open": {"S": [{"time": 0, "rotation_degrees": 0}, {"time": 1, "rotation_degrees": 70}],
                               "E": [{"time": 0, "rotation_degrees": 0}, {"time": 1, "rotation_degrees": -70}]}}}
  ]
}
```
- `directions` depend on the asset profile (one for a fixed structure, the approved set for a mobile one); every component needs a view for each.
- Exactly one root. Every child names a `mount` that exists as a named anchor on **every frame** of its parent's atlas in every direction. Frame counts may differ per component and direction (frames are shown by `duration_ms` weights).
- `mount_tracks` animate the child's attachment on the parent and are keyed by the **parent's** action (`parent_action`, else the parent's `action`); `motion_tracks` animate the child itself and are keyed by its own `action`. Both are keyed by direction (`"*"` for all). A track that no action selects, a direction the bundle does not have, or keyframe times that do not strictly increase within `[0, 1]` fail the build.
- Keyframes: `time`, `position` (local pixels), `rotation_degrees`, `scale`. Rotation interpolates linearly, so 0 to 360 is a full turn; set `"rotation_interpolation": "shortest"` for the shortest arc. All values are artist-verified, never inferred.
- Timing of a segment: a keyframe may say how the segment that starts at it is crossed. `interpolation` is `linear` (default), `nearest` (hold this key's value until the next key, for stepped limited animation) or `cubic` (a smooth curve through this key and the next whose slope comes from the neighbouring keys; evenly spaced straight keys stay straight). `easing` reshapes the time inside the segment: `linear`, `ease_in` (u squared), `ease_out` (one minus the square of one minus u) or `ease_in_out` (twice u squared below one half, mirrored above). A stepped segment cannot also ease, and a last keyframe has no segment after it, so neither field is accepted there. `sampled_poses` follow both, so they remain the numeric reference to check a game against. A job without these fields builds exactly as before.
- `rest`: optional local transform. `draw_order`: integer per direction (`"*"` for all); default is the parent-first order. `sample_times`: normalized times saved as test transforms.
- Source frames are relative to the job's folder. The output folder must not exist.

## Outputs (one candidate under `.gamearts/outputs/assets/generated/<revision>/`)
`<name>_<component>_<direction>.png` and `.atlas.json` per component and direction, and `<name>.bundle.json` ([`schemas/gamearts-bundle.schema.json`](../schemas/gamearts-bundle.schema.json)): `component_order`, components with parents, mounts, tracks, `draw_order` and atlas names, `sampled_poses`, `rotation_interpolation`, `visual_review_protocol` (`"review_packet"` for multi-part bundles) and a `validation` block (`parent_cleanup: "pending"` until proof is supplied, `engine_validation: "not_tested"`). Everything is built in a staging folder and published only if it all validated.

## Composition convention
`child_world = parent_world x mount_offset x mount_animation x rest x own_motion`, with `mount_offset` = the child's named anchor on the parent's *current* frame minus that frame's pivot. On a direction change the directional frames, pivots, anchors and transforms switch together. `sampled_poses` hold each component's composed 2D matrix for every direction and time; a game project's engine integration compares against them (master *Engine-neutral integration contract*).

## Validate
```text
python scripts/validate_component_bundle.py <bundle-folder>
python scripts/validate_component_bundle.py <bundle-folder> --approval-gate
```
The first checks the bundle and atlas contracts, every sheet's key-colour policy, mounts on every parent frame, track reachability and the sampled poses. `--approval-gate` additionally demands the cleanup proof below. A built bundle is **not** approved or game-ready; it never finds physical mount points or certifies visual alignment or engine behavior.

## Cleanup proof (required for approval)
Every independently movable, removable, interactive, replaceable or animated element must be absent from the static parent frames, with proof for **every parent, direction and frame**. The job carries:
```json
{
  "detached_inventory": {"workshop_body": ["workbench", "spanner", "screw"]},
  "parent_cleanup_evidence": [
    {"parent_component": "workshop_body", "direction": "fixed", "frame_index": 0, "manifest": "proof/workshop_body_fixed_0/cleanup.json"}
  ]
}
```
Each cleanup manifest ([`schemas/gamearts-cleanup.schema.json`](../schemas/gamearts-cleanup.schema.json)) lists the original composite, the cleaned parent, a separately reviewed clean plate and each detached component:
```json
{
  "schema_version": "1.0", "method": "pixel_exact",
  "source_composite": "parent_before_cleanup.png", "static_parent": "static_parent_clean.png",
  "clean_plate": "approved_background_without_props.png", "clean_plate_review": "approved",
  "clean_plate_reference_id": "review-reference-id", "art_style_id": "selected_project_style",
  "detached_components": [
    {"id": "workbench", "kind": "removable", "sprite": "workbench.png", "removal_mask": "workbench.mask.png",
     "sprite_silhouette_mask": "workbench.silhouette.png", "silhouette_review": "approved",
     "silhouette_reference_id": "workbench-review", "source_offset": [112, 64]}
  ]
}
```
All full-size images share one pixel geometry; masks are binary 0/255. `scripts/validate_parent_cleanup.py <cleanup.json>` proves the parent differs from the source inside each removal mask, matches the plate there, and equals the source elsewhere. With `--strict-props` (required for new production; the bundle gate always uses it) each sprite also needs its independently reviewed `sprite_silhouette_mask` and a `source_offset`; the sprite's ink must then equal the source pixels at that offset (within `source_tolerance`, default 0), lie inside its removal mask and match its silhouette. The builder packages the evidence in the candidate and records the result; every inventory ID must appear in the proof. The check validates *declared* objects: an omitted object needs the visual inventory audit.

## Visual acceptance
Valid matrices and exact masks do not prove a part was extracted completely or that the hidden surface behind it is credible. `scripts/visual_review_cleanup.py` builds the review boards and the hash-bound decision (master *Human-verifiable silhouette and reconstructed-background review*); the lifecycle blocks approved reuse if that evidence is missing or no longer matches the files.
