# Godot 4 — Game Arts Modular Component Runtime

This addon **loads generated moving-part component bundles** into a native Godot 4 `Node2D` scene. It uses directional sprite-sheet regions and composes nested parent/child animated mounts.

## Files

- `godot/addons/gamearts/game_arts_component.gd`: component hierarchy and playback.
- `godot/addons/gamearts/chroma_key.gdshader`: runtime masking of source images that remain opaque `#FF00FF`.
- `godot/addons/gamearts/game_arts_component.tscn`: editable reusable native base scene.
- `scripts/generate_godot_scene.py`: produces a native `.tscn` instance pointing to a specific existing `.bundle.json`.

## What Codex/Claude should do automatically

1. Confirm the user-approved master artwork and moving-part images are present.
2. Generate all matching component/direction PNG sheets, atlas JSONs and a `.bundle.json` with `build_component_bundle.py`.
3. Run `validate_component_bundle.py`.
4. Copy the three addon resources into the **target Godot game's** `res://addons/gamearts/` location, only if requested or required for integration and with normal project write permission. Preserve unrelated project files.
5. Place the generated asset bundle inside that game project's `res://` tree. Create the `.tscn` through `generate_godot_scene.py`, setting its `bundle_path` to the actual asset bundle path.
6. If Godot is available, test the generated scene across all required directions, at multiple times (including nested simultaneous motion), and verify masking and occlusion. Report tests only if they actually ran.
7. Save the complete generated candidate under `.gamearts/outputs/assets/generated/` and follow approval/revocation lifecycle rules. Recheck resource references after moving an approved bundle, especially the `bundle_path` in its scene file.

## API

`load_bundle("res://.gamearts/outputs/assets/generated/<asset>/<asset>.bundle.json")` loads components.
`set_facing("E")` switches all components' directional imagery and mounts in one pose update.
`set_progress(0.5)` applies the same normalized playback phase to all relevant tracks.
`playing = true` advances the normalized phase using `cycle_seconds`. `repeat_cycle` controls looping.

The runtime rebuilds its parts from the bundle/atlases and applies source-frame pivots, parent named mounts, parent-action animated mount curves, and independent component local curves.

### Important limitations

- This is **initial Godot runtime support**, not a production-ready rig importer. Actual Godot parsing, interactive physics and visuals must be tested on the target engine and game assets.
- Coordinates in the builder bundle are **screen/local pixels** for visuals. `parent_local_m` world geometry is not yet automatically projected into runtime sprite anchors.
- It uses normalized-time frame selection, not the per-frame `duration_ms` values in the atlas yet.
- `rest × own` motion supports position, rotation and scale as an affine decomposition, but complex shearing/3D perspective-correct movements may require a different representation.
- Direction changes preserve normalized time. No automatic engine-driven collision/navigation/light occluder updates have been implemented.
- Files remain exact opaque `#FF00FF`; pink is removed only during shader rendering. The shader needs runtime visual testing.
- Full automated screenshot comparison and actual Godot scene smoke tests are still needed.

**Everyday user experience:** ask “Animate this object” or “Check the moving parts in Godot.” Agent tools handle the underlying build steps. Do not ask users to run scripts.
