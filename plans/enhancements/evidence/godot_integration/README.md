# Godot integration check (evidence, not shipped)

Loads real framework output in headless Godot and compares what the engine did with what the framework said it would. Where
`godot_profile_verification` observes the engine alone, this folder runs the framework's own tools first: it is the end-to-end observation
behind plan A14.5. It is plan evidence, not part of the framework, not shipped to games, and one of the only places in the repository where
engine files are allowed (the docs guard skips `plans/`).

Run (Windows example; needs Pillow and `jsonschema`, and a Godot 4.7 console build):

```text
python plans/enhancements/evidence/godot_integration/run.py [--godot PATH] [--keep]
```

`run.py` builds, in a scratch folder and with the framework's scripts, a 16-tile corner tileset and a 47-tile blob tileset (`build_tileset`), a
sheet with three tags and per-frame times (`build_sheet_atlas`), an interface kit with four button states and a panel with nine-slice margins, and
animation tracks with easing, stepped and cubic keys. It derives the engine-ready copies with `export_runtime`, copies them into a scratch
Godot project and runs `verify_integration.gd`. The script only observes and prints one `VERIFY_JSON` line; `run.py` compares every value with the
framework's own, writes `output.json` (the observations, the framework's expected values and each check's outcome) and exits 1 if any check
failed. Last recorded run: Godot 4.7.2 stable (.NET build), 2026-10-24, 45 checks, 0 failed.

What is checked, and against what:

- **Runtime PNG.** Loads as RGBA at the delivered size; every key-colour pixel is fully transparent and every other pixel fully opaque (counts
  taken from the keyed sheet).
- **Tags to `SpriteFrames`.** One animation per tag with the frame count, loop flag, frame order (forward, reverse), per-frame relative durations
  and region size from the atlas, and the centre pixel of each region equal to that frame's colour in the engine-ready sheet. Ping-pong has no
  engine setting; the check records that the game plays it forward then back itself.
- **Interface kit.** `NinePatchRect` margins and texture are the frame's `nine_slice` and untrimmed size; each `Button` style box for
  normal, hover, pressed and disabled takes its state's frame and margins.
- **Curves.** Linear, ease in, ease out, ease in-out and stepped keys give the same values in the engine and in the framework to 0.001. **Cubic does
  not match** and the check asserts the difference, because the engine profile marks cubic `needs_custom`.
- **Tilesets.** Every neutral neighbour label is accepted as a terrain peering bit and reads back equal; the tileset and atlas agree on the tile
  count; painting a 3 x 3 block of one terrain with `set_cells_terrain_connect` makes the engine choose, for every cell of the block, the tile
  whose labels describe that cell's surroundings (the expected labels come from the block geometry alone, not from the tile data).

What it does not show: nothing is rendered, so filtering, halos and how the pictures look are not observed; other engines are not run; one
engine version and one machine; the owner has not opened these files in a game. The harness can fail: with the transparency step removed it
fails on every sheet that has key-colour pixels, and with the corner geometry inverted it fails the corner tileset (both tried, see tracker V-23).
