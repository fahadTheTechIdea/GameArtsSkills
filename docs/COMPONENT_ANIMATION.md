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
