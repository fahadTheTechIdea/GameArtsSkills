# Layered maps

A layered map reads a **whole scene** as layers: which terrain lies under every cell, the stack of terrain layers that draws it, and the static things (rocks, bushes, trees, buildings) that stand on it as sprites. It is engine-neutral data that your engine reads; Game Arts does not build an engine scene from it.

## The layers
- **Ground**: the lowest-priority terrain, everywhere (water, say).
- **One overlay per other terrain**, in priority order. An overlay covers every cell whose terrain has at least its priority, and it is drawn as a **dual grid**: a tile sits where four cells meet, chosen by which of those four the overlay covers. Each overlay needs only the 15 corner tiles of a two-terrain `dual_grid_16` tileset (a tileset whose pieces are made of the overlay terrain, with the terrain around it second), however many terrains the map has.
- **Objects** (and **overhead** objects, drawn above the actors), each placed by its atlas pivot, which is its ground contact and its sort point, with an optional footprint and collision.
- **Gameplay**: walkable or blocked, worked out from the terrains and the objects' footprints.

## Read a scene
```text
python scripts/gamearts_layered_map.py build --image <scene.png> --terrains <terrains.json> --cell 16x16 --name <name> --output-dir <folder> [--objects <objects.json>] [--min-region N]
python scripts/gamearts_layered_map.py validate <name>.layered_map.json
python scripts/gamearts_layered_map.py overlay <name>.layered_map.json --terrain <id>
python scripts/gamearts_layered_map.py gameplay <name>.layered_map.json
```
`terrains.json` lists each terrain: `id`, one-character `symbol`, its sample `colours` in the approved scene (`#RRGGBB`; a terrain has light and shaded tones, so give several), `priority`, `walkable`, and optionally its `tileset` file. Each cell gets the terrain whose nearest sample colour is nearest to the cell's median colour. Cells that are far from every sample are **listed**, never hidden.

A painted scene also draws things over the ground: trees, roofs, characters. Name them in an `occluders.json` (`id` and sample `colours` each, passed with `--occluders`). A cell they cover has no visible ground, so it takes the terrain of the nearest visible ground and is **listed as inferred** (`occluded_cells`), never as read. On the painted test scenes a quarter to over half of the cells were hidden this way, so check that list.

Colour cannot tell an object from ground of a similar colour (a cream wall from a cream crossing, a blue roof from a blue parking bay). When you have an **occlusion mask**, a picture the size of the scene that is white where an object lies (from the scene's analysis or a segmenter), pass it with `--occlusion-mask`: the cells it covers are hidden whatever their colour, together with those the colour occluders find. A large structure such as a building should also be an object with a blocking footprint, not ground inferred from its surroundings. Cleanup is **off** unless you give `--min-region`, and it reports what it changed: smoothing was measured to erase thin real features such as one-cell shores.

## Objects
Objects are **supplied**, from the approved scene's analysis or from masks an external segmenter produced. Detecting them by colour alone was measured to be unreliable (it missed objects close to their terrain's colour or invented hundreds of false ones), so Game Arts does not guess. To fill an area with repeated objects:
```text
python scripts/gamearts_placement.py scatter --map <name>.layered_map.json --on sand,grass --radius 24 --seed 7 --atlas rocks.atlas.json --frame S0 --footprint 8x8 --id-prefix rock --output rocks.json
```
This uses Poisson-disk sampling: a guaranteed minimum distance between objects (so footprints never overlap), the same positions for the same seed on every platform, only on the terrains you name, and clear of objects already placed. It writes a list you can pass to `build --objects`.

## From the scene to a map your tools can open
1. **Approve the scene** (the mockup gate) and list its terrains by sample colours, and the things drawn over the ground as occluders.
2. **Read it:** `gamearts_layered_map.py build ...`. Look at the unclassified and occluded cells it lists.
3. **Plan the art:** `gamearts_layered_map.py plan <map> --write-jobs <folder>` says, for each terrain, which tileset is missing, invalid or present, how many pictures it needs and what each one shows (in words), and writes a tileset job skeleton for each one still to make. The base ground needs one tile (or variants); every overlay needs the 16 corner tiles of a `dual_grid_16` set (one of them, with no overlay in any corner, is never drawn but the layout requires it, so make it blank).
4. **Make the pictures** with your image tool, through the normal mockup and approval gates, then build each tileset with `build_tileset.py` from its job and name it in `terrains.json`.
5. **Add the objects** (supplied, or `gamearts_placement.py scatter`), rebuild the map, and `validate` it. `overlay` shows any tile a set lacks.
6. **Export it:** `python scripts/export_exchange.py --layered-map <map> --format tiled` writes a Tiled map (`.tmj`) of the whole scene: the layers in order (each overlay offset by half a cell), the objects as tile objects placed by their pivot and sorted by y, a layer of blocking footprints, and the gameplay grid as a map property. It embeds the tilesets, so it needs only the pictures beside it. Tiled's format is best effort until the file has been opened in the tool.

## What is checked
The labels match the grid; the layers are the stack the terrains and objects make; every terrain's tileset exists, is the right layout, lists the right terrains in the right order and has the cell size; every position of every overlay has a tile in its tileset (a missing one is named); every object has its atlas frame, lies on the map and does not overlap another's footprint unless it says so.

## What is not checked
How good the art looks, and how any engine draws these layers (`engine_validation` stays `not_tested`). A scene that is a painting needs a terrain colour for each terrain, so check the unclassified cells before trusting a read.
