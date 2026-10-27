# Godot profile verification (evidence, not shipped)

Reproduces the observations behind `presets/engines/godot.json`. This folder is plan evidence: it is not part of the framework, it is not
shipped to games, and it is the only place in the repository where engine files are allowed (the docs guard skips `plans/`).

Run (Windows example; any Godot 4.7 console build works):

```text
Godot_v4.7.2-stable_mono_win64_console.exe --headless --path plans/enhancements/evidence/godot_profile_verification --script res://verify.gd
```

It prints one `VERIFY_JSON` line. `output.json` is that line from the recorded run: Godot 4.7.2 stable (.NET build), 2026-10-24 (tracker V-18 for the
grid, frame and project-setting probes; V-22 for the animation, UI, blend and tile probes).

What the script builds and reads back:

- **Frames and grids (V-18):** an `AtlasTexture` region, `SpriteFrames` durations and speed, a `Sprite2D` offset, `TileSet` hexagon and isometric grids read
  back through `TileMapLayer.map_to_local`, `Parallax2D`, and the project-setting options the engine itself lists.
- **Animation (V-22):** the `Animation` interpolation enum and the value read back at five times for the same three keys under nearest, linear and cubic
  interpolation; the value read back at three times of a 0 to 100 segment for six key transition values; `SpriteFrames` loop and speed; the playback methods
  and any ping-pong property of `AnimatedSprite2D`; the animation loop modes.
- **Interface and drawing (V-22):** the `CanvasItemMaterial` blend mode enum and its listed options; `NinePatchRect` margins read back after setting them; the
  style boxes of the default `Button` theme.
- **Tiles (V-22):** the `TileSet` terrain modes and, for each, which of the eight peering bits a tile exposes.

What it proves is only what it prints. It does not render anything, so filtering and edge halos are documented, not observed. The tests in
`tests/test_presets.py` (`GodotProfileTests`) tie every claim in the profile to a value in `output.json`, and check the framework's own easing, linear and cubic code
against the engine's numbers, so a change on either side that breaks the agreement fails a test.
