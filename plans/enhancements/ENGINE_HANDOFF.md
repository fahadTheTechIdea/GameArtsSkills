# Engine runtime hand-off (for whoever owns the game-engine integration)

Written 2026-10-23 as plan task P5.2, before the engine files were removed from this repository (owner decision D-2:
this repository is engine-agnostic art tooling imported into game projects; it contains no engine imports or runtime).

What was removed from this repository: the Godot addon (`godot/addons/gamearts/`: a component node, its scene and a
chroma-key shader), the scene generator script, the smoke-test fixture generator and runner, the engine CI workflow, the
engine runtime document and the `godot-validator` skill. They remain in the repository's version history.

What this repository now provides to an engine integration (the contract is in the master standard, section
"Engine-neutral integration contract"): sprite sheets with exact opaque `#FF00FF` outside the frames, one measured atlas
per sheet, and a component bundle whose `sampled_poses` hold the composed 2D transform of every component for every
direction and sampled time. The bundle's `engine_validation` field is `not_tested` until the game project records its own
result.

## Findings against the removed runtime (observed in review, not fixed)

These are inputs for the integration's next owner. None was fixed here; the code is gone.

1. The component node processed every frame whether or not anything moved. Use events or a timer and stay idle when
   nothing animates.
2. Pose application returned silently on missing data, so a broken bundle rendered as a static pose instead of failing.
3. Track interpolation was hand written. An engine's own animation resources are the native mechanism and should replace it.
4. The shader and lighting path forced modulate/lighting assumptions and nearest filtering regardless of the art style
   (painted and rendered styles want smooth filtering).
5. The runtime loaded bundles from a dot-prefixed project folder (`res://.gamearts/...`). Engines may skip or exclude such
   folders at import or export; load imported resources from a normal project path instead. Documentation names
   `.gdignore` for hiding folders; dot-prefix behavior is community-reported only and was not tested for export.
6. The generated scene kept a stale `bundle_path` after an asset moved from `generated` to `approved`.
7. The scene generator injected the bundle's `directions` string into the scene file without escaping.
8. Per-frame durations and per-direction draw order were not honoured by the runtime. Both are now in the bundle contract
   (`duration_ms` per frame in the atlas; `draw_order` per component and direction in the bundle).
9. There was no numeric parity test between the Python-sampled poses and the runtime transforms. `sampled_poses` is the
   oracle to compare against.
10. CI pinned one engine version (4.4.1). The fixture failed on a newer engine too, so the cause was the fixture data:
    its `mount_tracks` were keyed by the child's own action while the builder and runtime select them by the parent's
    action. The builder now rejects a track no action selects, so this fixture shape cannot recur.

Composition convention of `sampled_poses` (as built by `scripts/build_component_bundle.py`): a child's world matrix is
`parent_world x mount_offset x mount_animation x rest x own_motion`, where `mount_offset` is the child's named mount
anchor on the parent's current frame minus that frame's pivot, `mount_animation` comes from the child's `mount_tracks`
for the parent's action, and rotation keyframes interpolate linearly unless the job sets `rotation_interpolation` to
`shortest`.

Destination for a replacement runtime: recommended as a separate integration package that engine game projects install;
creating it is the owner's decision.

Update 2026-10-24: the engine is now planned as a per-project setting with engine profiles (data, not code) holding the
mapping from the framework's neutral outputs to each engine's own concepts, Godot first; see
[STYLE_AND_USABILITY_PLAN.md](STYLE_AND_USABILITY_PLAN.md) (D-16 to D-19, P10.6 to P10.9). The ten findings above remain
the inputs for whoever writes the importer; the profile is where the mapping facts live, so they are not repeated here.
