# Game Arts — Modular Moving Components

The [component bundle builder](../scripts/build_component_bundle.py) is an executable production helper for all modular 2D assets. It accepts approved source PNG frames, creates a **separate sprite-sheet PNG and measured atlas JSON for each component/direction**, validates that child mount names exist, calculates nested parent/child transforms and samples animated mounts over normalized time.

**Claude and Codex should invoke this automatically** after approved mockups and component artwork are available. Users do not need to run commands.

## Example job

The agent writes a `component_job.json` next to real approved source frame images, with this structure (illustrative paths/anchor numbers):

```json
{
  "name": "mygame_dynamic_structure_v001",
  "directions": ["S", "E"],
  "sample_times": [0, 0.5, 1],
  "source_mockups": [{"mockup_id":"scene-001","revision":"v003"}],
  "components": [
    {
      "id": "base",
      "parent": null,
      "views": {
        "S": {"frames":[{"file":"base_s.png","pivot":[16,24],"anchors":{"joint":[18,12]}}]},
        "E": {"frames":[{"file":"base_e.png","pivot":[16,24],"anchors":{"joint":[22,14]}}]}
      }
    },
    {
      "id": "part",
      "parent": "base",
      "mount": "joint",
      "parent_action": "open",
      "views": {
        "S": {"frames":[{"file":"part_s.png","pivot":[4,10]}]},
        "E": {"frames":[{"file":"part_e.png","pivot":[4,10]}]}
      },
      "mount_tracks": {
        "open": {
          "S": [{"time":0,"rotation_degrees":0},{"time":1,"rotation_degrees":70}],
          "E": [{"time":0,"rotation_degrees":0},{"time":1,"rotation_degrees":-70}]
        }
      }
    }
  ]
}
```

### Inputs
- Asset `name`: descriptive versioned slug; output location must not already exist.
- `directions`: **profile-dependent**, not hardcoded to eight. Every component must have all listed views.
- `components`: exactly one root; any number of descendants with `parent` and `mount` pointing to a named anchor in **every frame** of their parent directional atlas.
- `views[direction].frames`: approved individual source PNGs, pivots and measured named anchors (see [atlas builder](ATLAS_GENERATION.md)). Frame counts may differ by component and direction.
- `rest`: optional local component position/rotation/scale.
- `parent_action` and `mount_tracks`: optional animated mount transform tracks keyed by parent action and direction (or `*` wildcard).
- `action` and `motion_tracks`: optional child-local animation tracks keyed by action and direction.
- Keyframe times: monotonic normalized 0..1, position in **screen/local pixels** relative to named mounts; rotation in degrees; scale factors dimensionless. These are artist-verified values, **not automatically inferred**.
- `sample_times`: normalized positions at which to save test transform matrices.

### Outputs
The agent stores the complete candidate in `.gamearts/outputs/assets/generated/<descriptive-revision>/`:
- `<name>_<component>_<direction>.png`
- `<name>_<component>_<direction>.atlas.json`
- `<name>.bundle.json` with hierarchy, track definitions, per-direction references and sampled composed 2D transforms.

The builder uses **opaque exact #FF00FF** unused pixels. It doesn't resize art to match arbitrary category cell sizes and retains source frame hashes.

### Composition convention

`child_world = parent_world × parent_frame_mount_offset × animated_mount × child_rest × child_motion`

Each mount offset comes from the parent atlas frame's named anchor minus that frame's pivot. When a parent or child changes direction, the selected directional frames and mounts must update together; the engine stores per-direction data so a Godot runtime adapter can do so atomically.

### Required validation and known limitations

- The build validates hierarchy cycles, missing directional artwork, missing named parent anchors, bad frame formats and invalid animation tracks when evaluated.
- It **does not infer attachment anchor coordinates from artwork**, solve mechanical geometry, validate collisions/occlusion, test every continuous time, or create native Godot scenes. Such checks require a separate visual review and real Godot integration.
- The bundle is **not automatically approved or game-ready** after a successful build. User and technical approval gates still apply.
- Never use this tool to regenerate new reference art instead of obtaining approved mockups and frame images.

For developers/test runners, `python -m unittest discover -s tests -v` runs synthetic modular-component tests. The normal user never needs to run that command.

## Automated bundle validator

After building, the agent should invoke `scripts/validate_component_bundle.py <generated-bundle-folder>` internally and keep the bundle in generated until human approval and any required Godot tests. The validator checks PNGs, atlases, frame bounds, alpha, directional listings and sampled transforms, but does not infer physical geometry or verify unsampled motion.


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
