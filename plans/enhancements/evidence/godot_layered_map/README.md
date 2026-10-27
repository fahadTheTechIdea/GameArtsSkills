# Godot layered-map check (evidence, not shipped)

Plan task P16.6. Builds a real layered map with the framework's own tools (three tilesets, a rock sheet, a 6 x 4 cell scene read into a map with three rocks) and loads
its layers in headless Godot, so the engine-facing claims of `plans/enhancements/MULTILAYER_TERRAIN_RESEARCH.md` are observed, not assumed. It is plan evidence, not
part of the framework, and one of the few places where engine files are allowed (the docs guard skips `plans/`).

```text
python plans/enhancements/evidence/godot_layered_map/run.py [--godot PATH] [--keep]
```

`run.py` builds everything in a scratch folder, copies the files into a scratch Godot project and runs `verify_layered_map.gd`, which only observes and prints one
`VERIFY_JSON` line. `run.py` compares every value with the framework's own and writes `output.json`. Last recorded run: Godot 4.7.2 stable, 2026-10-27, 15 checks, 0 failed.

What is checked: each overlay becomes one `TileMapLayer` on the dual grid (a layer offset by half a cell), holds one tile per position of the framework's overlay plan and reads
back the tile id the framework chose, with each display tile centred where four cells meet; the rocks as atlas tiles on a y-sorted layer land on the cell their pixel position
falls in, carry the pivot's distance as the tile's y-sort origin and the footprint as one collision polygon per tile; the rocks as sprites sit at their exact pixel positions under
a y-sorted node.

Found while building it: a tile holds collision data only when its source already belongs to a tile set that has a physics layer (the polygon is dropped silently otherwise), and a
tile can only sit on a cell, so a free pixel position is snapped by up to half a cell (2 px here).

What it does not show (also listed in `output.json`): nothing is rendered, so the draw order of y-sorted layers and sprites and how the pictures look are not observed; the meaning
of a tile's texture origin for placing a sprite by its pivot; navigation; performance with many objects; other engine versions; the owner has not opened these files in a game.
The harness can fail: with the atlas coordinates swapped, or the half-cell offset removed, it fails the overlay checks (both tried).
