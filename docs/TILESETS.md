# Tilesets

A tileset is a sheet of equal square (or rectangular) tiles that a game's map fills itself from. Game Arts builds one from approved tile pictures and checks that it is complete and that the tiles can sit side by side. The layout rules are in the master standard (*Sprite sheets, atlases and component bundles*); this page is the job format and what is checked.

Tiles are checked as rectangles. A diamond (isometric) tile is stored in its rectangle with the key colour in the corners; the neighbour rules above are not yet verified against diamond edges, so ask for a small test sheet first.

## Layouts
Every tile carries the terrain found at each of the eight places around it, named clockwise from the top: `top`, `top_right`, `right`, `bottom_right`, `bottom`, `bottom_left`, `left`, `top_left`. A layout says which places it uses and which tiles it needs. With two terrains, `terrains[0]` is what the tiles are made of and `terrains[1]` is what lies around them.

| Layout | Terrains | Tiles | Places labelled |
|---|---|---|---|
| `single` | 1 | 1 | none (all the same terrain) |
| `variants` | 1 | 1 or more, interchangeable | none |
| `wang_corner_16` | 2 | 16, every combination of four corners | the four corners |
| `wang_edge_16` | 2 | 16, every combination of four edges | the four sides |
| `blob_47` | 2 | 47, every distinct arrangement of the eight neighbours | all eight; a corner counts only when both sides touching it are the first terrain |
| `dual_grid_16` | 2 | the same 16 corner tiles, drawn on a grid offset by half a tile | the four corners |

## Job
```json
{
  "name": "ground_v001",
  "tile_size": [16, 16],
  "layout": "wang_corner_16",
  "terrains": ["grass", "water"],
  "columns": 4,
  "tiles": [
    {"file": "t00.png", "neighbours": {"top_left": "water", "top_right": "water", "bottom_right": "water", "bottom_left": "water"}},
    {"file": "t01.png", "neighbours": {"top_left": "grass", "top_right": "water", "bottom_right": "water", "bottom_left": "water"}}
  ]
}
```
`columns` defaults to 8. `full_bleed` defaults to true: ground tiles fill their whole square with no key colour. A tileset of objects on a clear background says `"full_bleed": false` and keeps the key colour around the art. `single` and `variants` tiles need no `neighbours`.

## Animated tiles
Water, lava and torches are tiles that show several pictures in turn. Add the extra pictures to `tiles` (after the real tiles, without terrain or neighbours) and name the animation in the job:
```json
"animations": [{"tile": 3, "frames": [{"tile": 3, "duration_ms": 200}, {"tile": 16, "duration_ms": 200}, {"tile": 17, "duration_ms": 200}]}]
```
A frame other than the tile itself exists only as a frame: it takes the labels of the tile it animates, so an animation never changes what terrain a tile is, and the seam check holds it to the same edges. A tile has one animation, a frame belongs to one animation, an unknown id is refused by name, and a frame that brings its own labels is refused. The Tiled export lists each animation (frame tile and milliseconds) and gives the frames no wang id of their own. Durations are the art's intent; how an engine plays them is the game project's.

## Run
```text
python scripts/build_tileset.py <job.json> --output-dir <candidate-folder> [--game-root <game>]
python scripts/validate_tileset.py <name>.tileset.json
```
With `--game-root` the builder also says whether the tiles are the game's ground tile (`world.ground_tile_px`) and its scale; a mismatch is advice, never a refusal. The builder refuses an incomplete set (the missing tile is described in words: "missing tile: corners top_left=grass top_right=water ..."), a repeated tile, a label on a place the layout does not use, a blob corner that cannot exist, a picture that is not the tile size, and an existing output. It writes `<name>.png` and `<name>.atlas.json` through the one sheet builder and `<name>.tileset.json` with the layout and labels. Tile number *n* is frame *n* of the atlas, and the sheet is a regular grid with no spacing, so any tile editor reads it.

## What is checked
Labels (complete, consistent, canonical), tile size and grid position, the sheet's pixel contract, no key-coloured pixel in a ground tile, and **shared sides**: two tiles that claim the same side must have matching pixels along it. Matching is judged on the outermost row or column of each tile against the other, allowing the difference the tile's own texture already has between its outermost and next row plus a tolerance (16 on a 0 to 255 scale by default). A registered bundle with a tileset has all of this run by the technical artwork gate, so a broken tileset cannot be approved. It proves the tiles can be placed without a visible break; it does not say whether they look good.

## For other tools and engines
`python scripts/export_exchange.py --tileset <name>.tileset.json --format tiled` writes a Tiled tileset (`<name>.tsj`) with a wang set for the corner, edge and blob layouts. Compatibility is best effort until a real export has been opened in Tiled. Which engine setting a layout corresponds to is in the engine profile (`presets/engines/`).
