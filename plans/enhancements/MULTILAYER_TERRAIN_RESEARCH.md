# Multi-layer terrain tilesets from a scene: research and proposed design

Researched 2026-10-27. Status: **research and a proposal, nothing built.** Owner request: "Research how to create multi-layer tilesets for Godot, for a game, based on the existing pipeline. It should recreate the whole surface from a scene with different layers, including all types of terrain and static objects like rocks as sprites. Research it for the best algorithms."

How to read this: **Documented** means a source says it. **Measured** means I ran it here (the experiment in §5, synthetic data). **Inferred** is my reasoning and is labelled so. Nothing here has met a real approved mockup, a real image tool's terrain art, or a Godot project.

Constraints that shape the answer (all from the repository's own rules): no engine code in this repository, so engine-specific scene building belongs to the game project and this repository delivers engine-neutral data plus art; the framework's scripts depend on Pillow and `jsonschema` only; the framework **measures and validates, the image tool or agent produces**; the key-colour PNG stays the canonical delivery; one owner per fact.

## 1. What the pipeline already has

| Stage the task needs | Already in the framework | Gap |
| --- | --- | --- |
| Approved scene picture | Mockup gate, `mockup-analyzer` (measured source-pixel regions, asset class and view per region), reference crops, pixel-grid snapper | A mockup is a painting: it is not aligned to any tile grid, and nothing turns it into a label per cell |
| Ground tiles that fit together | `tileset` class, layouts `single`, `variants`, `wang_corner_16`, `wang_edge_16`, `blob_47`, `dual_grid_16` (two terrains each), builder, validator, shared-side checks | One tileset covers two terrains. Three or more terrains and their transitions are not planned or checked |
| Objects as sprites | `static_structure`, `prop`, atlases with pivots, trim, anchors, tags, nine-slice; `parallax_layer` for backdrops | No footprint, no ground contact point, no sort anchor, no placement record |
| Layers | `world.layers` exists only for parallax; no ordered stack of tile layers | No contract for "this scene is these layers" |
| Export | Tiled export (best effort), runtime export with real alpha, matte for soft edges, Godot profile with 4.7.2 observations | No map file at all: the framework delivers art, never a map |

## 2. Findings from the sources

### 2.1 Godot's own features (documented; Godot stable docs, read 2026-10-27)

- **Terrain sets** have three modes: Match Corners and Sides, Match Corners, Match Sides. Each tile carries peering bits. `set_cells_terrain_connect(cells, terrain_set, terrain, ignore_empty_terrains)` updates cells and "neighboring cells may also be updated"; it "requires the TileMapLayer's TileSet to have terrains set up with all required terrain combinations", otherwise results can be unexpected ([TileMapLayer reference](https://docs.godotengine.org/en/stable/classes/class_tilemaplayer.html), [TileSet reference](https://docs.godotengine.org/en/stable/classes/class_tileset.html)). A third-party plugin author reports the built-in system is slow and awkward at runtime ([Better Terrain](https://github.com/Portponky/better-terrain), [Terrain Autotiler](https://github.com/dandeliondino/terrain-autotiler); the second is no longer maintained as of 4/2024, so a reference, not a dependency).
- **One tile per cell per layer.** "Stacking tiles at one location requires separate layers"; layers can be reordered; removing a layer deletes its tiles ([Using TileMaps](https://docs.godotengine.org/en/stable/tutorials/2d/using_tilemaps.html)). `TileMap` is deprecated in favour of several `TileMapLayer` nodes.
- **Objects.** Scene tiles (scene collection) let any node tree be a tile, but "every scene is instanced individually for every placed tile"; the docs recommend them only when needed and say "for plain sprites, use atlases instead" ([Using TileSets](https://docs.godotengine.org/en/stable/tutorials/2d/using_tilesets.html)). Per-tile **Y Sort Origin** helps simulate height and works only when Y Sort Enabled is on; with y-sorting the rendering quadrant size does not apply (tiles are grouped by Y position). A forum report says sorting by origin needs the object's base at the origin and mixing sorted and unsorted layers causes trouble; blogs disagree on details, so this needs a test in a real project ([forum](https://forum.godotengine.org/t/best-practice-for-stacking-tilemaplayer-nodes-with-ysort-in-godot-4-4/120306)).
- **Collision, navigation, occlusion, custom data** are TileSet layers defined per tile. Custom data is shared by all placed instances; per-instance variation needs alternative tiles. Built-in navigation "has many practical limitations that result in inferior pathfinding performance"; the docs recommend baking a navigation mesh, and say 2D navigation meshes cannot be layered on top of each other.
- **Variation without extra art:** alternative tiles (flip, transpose, modulate, y-sort origin) and a per-tile probability for random painting; the docs also describe scattering as "a chance that no tile will be placed".
- **Atlas rules:** set the tile size before creating the atlas, fully transparent regions make no tiles, texture padding (a 1-pixel transparent edge) prevents bleeding when filtering is on.

### 2.2 Autotiling families and how they scale to many terrains

- **Single-grid bitmask** (4 or 8 neighbours; 16 or 47 tiles for two terrains) is what the pipeline's `blob_47` is. Boris the Brave: it "only handles transitions between two different terrains. If you add a third, you need hundreds of tiles" ([Beyond Basic Autotiling](https://www.boristhebrave.com/2021/09/12/beyond-basic-autotiling/), 2021). A Tiled forum thread shows corner-based terrain caps at 2^4 = 16 combinations and cannot encode a blob set.
- **Dual grid** (display tiles offset by half a cell, each placed where four data cells meet; 2D marching squares): 16 combinations, 15 if the empty case is dropped; only the corner art is needed. Sources: [Excalibur write-up](https://excaliburjs.com/blog/Dual%20Tilemap%20Autotiling%20Technique), [TileMapDual (Godot)](https://github.com/pablogila/TileMapDual), [a Godot forum implementation](https://forum.godotengine.org/t/i-made-a-16-tile-autotiler-dual-grid-because-why-not/141382). The pipeline already has `dual_grid_16`.
- **Layered or overlay tiles.** Per-terrain priority overlays: "assign a priority to each; a cell matches its neighbour if the neighbour has the same or higher priority; each terrain gets its own overlay drawn lowest to highest" (Red Blob Games' autotile material, as summarised by a search result; the article page itself I could not read, so treat this as secondary). Boris the Brave confirms the layered idea: a base tile plus border tiles stacked, "you still need less than half the full tileset of the blob pattern". Masked transitions (a reusable blend mask, stackable for multi-way blends) are the route for higher-resolution art (Factorio's dev blog is the cited example).
- **Wang tiles for textures** (Cohen, Shade, Hiller, Deussen 2003, [paper](https://graphics.uni-konstanz.de/publikationen/Cohen2003WangTilesImage/index.html)): a small set of edge-coloured tiles fills a plane non-periodically; repetition can still show; the later "corner tiles" variant gets more of the sample into the result. Useful for the **interior** of a large terrain so it does not visibly repeat.

### 2.3 From a picture to a terrain grid

- **Tile extraction by deduplication** (cut an image on a grid, drop identical tiles: Tile Extractor, TileMap2TileSet, Bisqwit's Image Tilemapper) works only on art that was **made** from tiles. A painted or generated mockup has no repeated identical cells, so this is the wrong tool for the framework's main input. (Inferred from how those tools describe themselves.)
- **Segment, then classify.** Open-vocabulary work uses class-agnostic masks followed by a vision-language model to name each mask ([OVSeg](https://ar5iv.labs.arxiv.org/html/2210.04150)), and reports that CLIP is the weak point because it handles masked crops poorly; training-free dense variants exist ([CLIP-DIY](https://openaccess.thecvf.com/content/WACV2024/papers/Wysoczanska_CLIP-DIY_CLIP_Dense_Inference_Yields_Open-Vocabulary_Semantic_Segmentation_For-Free_WACV_2024_paper.pdf)). SAM's automatic mask generator sweeps a grid of point prompts and returns a mask per object ([segment-anything](https://github.com/facebookresearch/segment-anything), [SAM 2 in Transformers](https://huggingface.co/docs/transformers/en/model_doc/sam2)). I found **no source that tests any of this on game mockups or pixel art**, and the one terrain-specific model found is trained on real off-road photos. Treat all of it as unverified for this input.
- **Label-map cleanup.** Morphological opening/closing and area opening are the standard ways to remove speckle in segmentation output; the sources warn that a too-large radius merges real regions. Majority-vote relabelling is described for uncertain pixels. (My experiment, §5, shows the cost of over-cleaning.)

### 2.4 Static objects as sprites

- Sprite-extraction tools use connected-pixel analysis, flood fill or background-colour removal, and a Phaser tool notes touching sprites merge into one ([Phaser extract-sprites](https://phaser.io/tools/extract-sprites)). Promptable segmenters are the proposed fix for merging; no tested result found.
- **Placement** of repeated objects (rocks, trees): Bridson's fast Poisson-disk sampling is O(n) and gives a guaranteed minimum distance ([paper](https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph07-poissondisk.pdf), [explainer](https://sighack.com/post/poisson-disk-sampling-bridsons-algorithm)); a variable-radius variant takes a density map so objects cluster or thin by terrain ([poissonDiskSampling](https://pypi.org/project/poissonDiskSampling)). A game-oriented write-up uses a simpler random-radius variant ([devmag](https://devmag.org.za/2009/05/03/poisson-disk-sampling/)).

### 2.5 Filling in, or inventing, a surface

- **Wave Function Collapse** (Gumin, [README](https://github.com/mxgmn/WaveFunctionCollapse)): repeat observation (collapse the lowest-entropy cell) and propagation. Two models: **simple tiled** (adjacency from the artist's rules) and **overlapping** (adjacency and weights learned from a sample image). The README itself says deciding whether a result exists is NP-hard, contradictions end a run without output, and "easy" tilesets "don't produce interesting global arrangements" without extra heuristics. A practitioner note found: high-level rules such as walkability or path connectivity need extra logic.
- **Terrain from noise:** an elevation field and a moisture field, thresholded or looked up in a Whittaker-style table; Voronoi regions with Lloyd relaxation give irregular borders; Gaussian smoothing softens the classification; hard region edges need blending ([Red Blob Games](https://redblobgames.com/maps/terrain-from-noise/), [SoCG 2026 paper](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SoCG.2026.101)). Relevant only where the scene must be **extended** beyond the approved picture.

## 3. Design proposal

The task is two problems that must not be mixed: **(A) read the approved scene** into layers, and **(B) build and check the art that draws those layers**. The framework already does (B) for one terrain pair; (A) is new.

### 3.1 Layers (engine-neutral, then mapped to Godot)

| Layer | Content | Data | Godot mapping (documented features) |
| --- | --- | --- | --- |
| L0 ground | The lowest-priority terrain everywhere (for example water or dirt) | full-coverage label | a `TileMapLayer` filled with `single`/`variants` tiles |
| L1..Ln terrain overlays | One layer per further terrain in priority order; each is a two-state (terrain or not) dual-grid layer | per-terrain boolean grid, 15 corner tiles per terrain | one `TileMapLayer` per terrain with a 16-tile set; draw order = priority. One tile per cell per layer is why they are separate layers |
| Detail | Cracks, flowers, shore foam, path edges: art with no neighbour rules | cell list with variants | a layer of atlas tiles with scatter probability |
| Objects | Rocks, bushes, trees, buildings as sprites | list of {sprite, pixel position, footprint, collision, class}; the position is where the atlas pivot lands | small and many **on the cell grid**: atlas tiles in a y-sorted layer (docs: atlases for plain sprites), accepting a snap of up to half a cell (observed, 3.5); at free pixel positions, or tall, animated or interactive: sprites or separate nodes, placed exactly. Per-tile y-sort origin at the object's base |
| Overhead | Canopy, bridges, roofs drawn above actors | like Objects, with a layer role | a layer above the actors |
| Gameplay data | Walkable, blocked, cost, terrain name | derived from labels and object footprints | TileSet collision, navigation (baked, per the docs), custom data layers |

The overlay scheme needs **(N-1) x 15 ground tiles for N terrains** (inferred), against N(N-1)/2 pairs x 15 for full pairwise sets and "hundreds" for single-layer blobs. §5 measured how many distinct combinations a 5-terrain scene actually uses.

### 3.2 Algorithms, with a decision for each

| Step | Adopt | Adapt | Avoid |
| --- | --- | --- | --- |
| Align the picture to a grid | the framework's pixel-grid snapper and the approved scale | detect the cell size from the mockup's stated tile size | guessing a grid from a painting |
| Terrain label per cell | **nearest palette colour in Lab on each cell's median**, against the colours of the approved terrain art (measured 99.5% on a clean synthetic scene, in Pillow and the standard library alone, 3.3) | a segmenter's masks where terrain colours overlap or textures are rich | a blind k-means with no named palette (works, but needs the naming step) |
| Cleanup | **area opening with a small minimum** on the label grid; report what changed | none | a 3x3 majority filter: measured to erase thin real features (§5) |
| Terrain art | overlay dual-grid, 15 tiles per terrain, checked by the existing shared-side validator | Wang-style variants for large interiors | one blob set per terrain pair |
| Object separation | the mockup analysis's measured regions as **prompts**, a segmenter for the exact mask (external tool, validated here) | colour-contrast detection only for high-contrast objects | blind detection (measured weak, §5) |
| Object placement (to extend or fill) | Bridson Poisson-disk, radius from the object's footprint, density from a terrain mask | variable radius per class | uniform random (measured overlap, §5) |
| Extending beyond the scene | noise-based labels for the base, then the same overlays | overlapping-model WFC only if a sample must be matched | WFC as the first choice: contradiction handling and global-structure limits are documented |

### 3.3 Dependencies, for a framework other people download

The owner's rule: use the libraries the work needs, but remember that other people install this. Two measurements decide it (both mine, 2026-10-27):

- **The core reader needs no new library.** A Pillow-and-standard-library version of the cell reader (per-cell median colour, nearest palette colour in Lab with the framework's own palette module, then a breadth-first area opening) labelled the synthetic scenes **99.45% correct, against 99.49% for the numpy version**, in **0.35 s for a 1024 x 768 scene** and **5.75 s for a 4096 x 3072 scene at 64 px cells**. That is a one-off analysis step, so the time is acceptable. The expensive things are image segmentation and machine learning, not the terrain reader.
- **What the optional libraries cost a downloader.** Wheels fetched for Python 3.12: numpy 2.5.4 is 12.6 MB on Windows and numpy 2.2.6 is 16.5 MB on Linux (licence BSD-3-Clause, plus the permissive licences it bundles); opencv-python-headless 5.0.0.93 is 43.8 MB on Windows and 56.6 MB on Linux (its metadata says Apache 2.0; older PyPI pages say its wheels ship FFmpeg under the LGPL-2.1, which I did not re-check for this release). A segmenter such as SAM adds a deep-learning runtime and model weights; mirrors of the official repository state Apache 2.0 for the model, the checkpoints are hundreds of megabytes to a few gigabytes (my memory, not verified here), and its dataset has a separate research licence.

**Tested with other libraries (the owner's follow-up: "test with different libraries now and decide if they don't make a difference later").** The same job through numpy 2.5.4, OpenCV 5.0.0, SciPy 1.18.1 and scikit-image 0.26.0 (Python 3.14.4, Windows), on five seeded scenes with 90 painted objects each, script and output kept in `plans/enhancements/evidence/terrain_backend_comparison.py` and `terrain_backend_comparison_output.json`:

| Job | Pillow (the framework's code) | numpy | OpenCV | scikit-image | Reading |
| --- | --- | --- | --- | --- | --- |
| Cell reader, accuracy | 98.42% | 98.41% | 98.42% | 98.41% | **no difference**: 99.98 to 99.99% of cells are identical (an even-count median takes the upper middle value in Pillow and the average in numpy) |
| Cell reader, 1024 x 768 | 0.19 s | 0.018 s | 0.019 s | 0.018 s | about 10x faster, but 0.19 s is already fast |
| Cell reader, 4096 x 3072 | 2.7 s | 0.27 s | 0.28 s | 0.27 s | about 10x faster; 2.7 s is acceptable for a one-off step |
| OpenCV's cheapest route (area **mean**, no median) | | | 97.6% accurate, 98.7% of cells identical, 0.015 s | | the only variant that is **worse**: objects pull a mean away from the terrain colour; about 180x faster |
| Area opening (small-region cleanup) | 96.89% | | OpenCV 96.92%, SciPy 96.93%, scikit-image 96.56% | | **no difference** in accuracy; 1 to 6 ms each; they differ cell by cell (98.5 to 99.8% identical) only in how ties between neighbouring labels are broken |
| Poisson-disk placement | pure Python, 136 points, minimum gap 24.11 px, 0.07 s | | SciPy `qmc.PoissonDisk`: 125 points, gap 24.03 px, 0.11 s | | **no difference**; SciPy is not faster |

Install cost for the scikit-image and SciPy route: about 257 MB on disk (with numpy, networkx, imageio and Pillow) against none for the Pillow path; the numpy wheel alone is 12.6 to 16.5 MB. **Reading: on this job the libraries do not change the answer, only the time, and the time saved is seconds on the largest picture.** The scene is synthetic and easy, so this says nothing about real painted mockups.

**Decision rule, to apply after P16.0 on real mockups:** adopt a library only if (a) it changes accuracy by 0.5 points or more on real scenes, or (b) real mockups are large enough that the Pillow reader takes more than about 10 s. Otherwise keep one implementation (the framework's) so results are identical everywhere. Until then nothing is added.

So the policy proposed, in tiers:

| Tier | What | Rule |
| --- | --- | --- |
| Core | Pillow and `jsonschema`, as today | Everything the framework must do, including the label reader, area opening, overlays, validators and Poisson-disk placement, runs here. The CI matrix keeps its oldest-Pillow leg |
| Optional speed-up | numpy | Used only when installed, with **identical results** (a test runs both paths and compares); never required. If it is absent nothing is skipped or reported as a pass: the Pillow path runs |
| External tools | A segmenter, an image generator | **Never bundled and never required.** They are tools the agent or the owner runs, like the image generator: the framework asks for masks as files and validates them (same size as the picture, one label or object per mask, no overlap beyond a stated tolerance), and says plainly when none was supplied. Their licence and weight size go in the install guide before any is recommended |
| Avoid | OpenCV | Large wheels and an extra licence question for no gain the core path needs |

Rules for anything a downloader installs: wheels only (no compiler), Python 3.11 and 3.14 as today, a minimum version stated and tested in a CI leg, no network use at run time, no model weights or large binaries in the repository, licences listed in `README_INSTALL.md`, and the doctor reports which optional pieces are present in plain words. A missing optional piece is never an error; a missing required one stays a hard failure, as the install guide already says for `jsonschema`.

### 3.4 Contract and tasks (proposed, none built)

A new `layered_map` description (a JSON contract, engine-neutral): the grid and cell size; the terrain list with priorities and tile sets; the label grid per terrain; the objects with footprint, ground anchor, sort anchor and collision; layer roles and order; everything referenced by hash. The framework would **validate** it (labels cover the grid, overlays and sets exist, every object sprite exists, footprints do not overlap unless declared, sort anchors sit inside the sprite) and export it with the existing Tiled path and the runtime export. A Godot importer that builds `TileSet` and `TileMapLayer` nodes belongs to the game project (the engine handoff note), written against the observed behaviour below.

| ID | Task | Check |
| --- | --- | --- |
| P16.0 | Spike on **real** approved mockups: terrain labelling accuracy and the object-separation route, with a real segmenter | accuracy and recall on at least three real scenes, recorded in the tracker; this decides everything below |
| P16.1 | Multi-terrain plan: priorities and the per-terrain 15-tile sets (extends the tileset class) | new test: complete set per terrain; an overlay whose neighbour rule fails is named |
| P16.2 | Label grid reader: cell classification from a mockup and the approved terrain art; area opening; a change report | new test on synthetic scenes with known labels; the report names every changed cell |
| P16.3 | Object records: footprint, ground anchor, sort anchor, collision in the atlas | schema and validator tests; a sort anchor outside its sprite is named |
| P16.4 | `layered_map` contract and validator | contract tests; revert-the-fix proofs |
| P16.5 | Placement: Poisson-disk with density masks, deterministic by seed | a test that the minimum distance holds and the result is reproducible |
| P16.6 | Godot observations with the installed 4.7.2 headless build, like the existing profile checks: a terrain-connect call on an overlay layer, y-sorted atlas objects, scene tiles under y-sort, baked navigation | recorded command, exit status and observed result per mapping; a mapping that cannot be shown is marked `needs_custom` |
| P16.7 | Skill and docs routing; the engine handoff note | the docs guard passes; no engine named in shipped text |
| P16.8 | Optional-dependency policy (3.3): the doctor lists optional pieces, a CI leg runs without them, a test compares the Pillow path with the numpy path, the licence list in the install guide | the matrix stays green without numpy; the two paths give identical labels on the synthetic scenes |

## 3.5 Observed in Godot 4.7.2 (P16.6)

`plans/enhancements/evidence/godot_layered_map/` builds a real layered map with the framework and loads its layers in the installed headless engine (15 checks, 0 failed; it fails when the atlas coordinates are swapped or the half-cell offset is removed). Observed: each overlay as one `TileMapLayer` offset by half a cell holds one tile per position of the framework's overlay plan and reads back the tile id the framework chose, each display tile centred where four cells meet; small objects as atlas tiles on a y-sorted layer land on the cell their position falls in, carry the pivot distance as the tile's y-sort origin and the footprint as a collision polygon. Two findings change the design: **a tile can only sit on a cell, so objects placed at free pixel positions (as Poisson-disk placement gives them) are snapped by up to half a cell as tiles, or must be sprites placed exactly**; and **a tile's collision polygon is silently dropped unless its source already belongs to a tile set that has a physics layer**. Not observed: draw order (nothing is rendered), how the art looks, a tile's texture origin for pivot placement, navigation, performance with many objects.

## 3.6 Tried on a real painted reference (the owner's test image, 2026-10-27)

The owner supplied three painted pixel-art scenes (beach, village, forest, one JPEG) "for testing". Evidence in `plans/enhancements/evidence/real_scene_spike/` (the image is not stored). No ground truth exists, so correctness was judged by looking at the label maps.

- **The first design failed.** Terrain colours from a median-cut palette of 6 colours, nearest colour of each cell's median: one colour described well only 37% of the village's cells at 32 px (81% of the beach's, 69% of the forest's); the label map was a colour mosaic, not terrain (grass split across shades, huts, trees and characters mixed in). The picture had no recoverable art-pixel grid (a re-encoded JPEG; a pixel-grid score of about 1.1 where a clean grid scores clearly higher), so a pixel snapper would have nothing to snap to.
- **Terrains as sample points, objects as occluders worked better.** With several sample colours per terrain and trees, roofs, rocks and characters as named occluder classes, filling the hidden cells from the nearest ground gave plausible ground maps by eye (the beach: sand, shallow water, foam and wet-sand patches; the village: grass in two tones, path, and the water edge), and cut the distinct four-corner combinations a scene needs from 244 to 109 (village), 119 to 58 (beach) and 230 to 57 (forest). It is not reliable where colours overlap (forest roots read as dirt path) or where objects dominate.
- **Objects are a large part of these scenes.** At 32 px cells the cells whose nearest class was an object were 29% (beach), 45% (forest) and 55% (village). "Recreating the whole surface" therefore means separating the objects **and** inferring the ground under them; the fill used here is a nearest-neighbour guess, not inpainting, and the ground under a big trunk or hut is unknowable from the picture.
- **Not in the design yet:** height. The village is a raised grass ledge over water with a cliff edge; a flat label grid has no elevation levels or cliff tiles. Objects larger than a cell (huts, big trees, rock masses) need real sprite extraction with masks; none was attempted here. The sample points were chosen by looking at the picture, so this is a best-effort reading by a person, not an automatic one.
- **What changed in the code because of it:** terrains take several sample `colours` (the schema field replaced the single `colour`), `build` takes `--occluders`, hidden cells are filled and recorded in `occluded_cells`.

## 3.7 Tried on the owner's club-arrival mockup (Cozy Soccer, 2026-10-27)

A far better test than the first reference: a clean PNG of a street-level scene (road, pavement, plaza, parking asphalt, the pitch, a club building, cars, trees, people), in the project's own camera. Evidence in `plans/enhancements/evidence/club_arrival_spike/` (the image stays in its repository). At 32 px cells (52 x 29).

- **The picture is not pixel art in the strict sense.** No block size shows a pixel grid (scores 1.00 to 1.03) and a sample has about 144,000 distinct colours: it is an AI render in a pixel-art style. A pixel snapper and a palette check have nothing to work with, so the ground tiles cannot be recovered from the mockup and must be made as art.
- **Colour alone reads the structure and then goes wrong at the overlaps.** With terrains defined by sample colours (asphalt, paving, grass, crossing, tactile strip, accessible bay) and 15 colour-defined occluder classes, the ground map shows the pitch, the road, the pavement strip, the parking lot and the plaza. But the building's cream wall read as crossing and its blue roof as the blue parking bay: 60 of the 240 cells of the facade were read as visible ground, and 25 cells read as the blue bay lay outside the real bay.
- **A near-tie margin does not fix it.** Treating a cell as uncertain when its nearest ground and occluder classes are within a margin removed the false ground only by hiding most of the picture (hidden share 48% at margin 0, 62% at 3, 80% at 6, 86% at 10), and the real accessible bay vanished at 3. The classes' colours overlap too much.
- **An occlusion mask fixes the object problem.** Given a mask (white where an object lies; here 37 rectangles drawn by hand, what a mockup analysis or a segmenter would supply), the facade read as visible ground fell from 60 to 0 cells, the blue-bay errors from 25 to 10 to 11, and the distinct four-corner combinations from 178 to 136 (mask alone) and 108 (mask plus colour occluders). `build --occlusion-mask` was added for this.
- **What is still wrong.** The ground under a large object is a guess from its surroundings (the fill put grass and paving under the building, which is really a building footprint: a large structure should become a blocking object, not inferred ground). A rare class spreads where hidden cells touch it (the narrow crossing label spread, about 130 false cells). Thin features (lane lines, bay lines, the kerb) are below a 32 px cell and vanish. About 57 to 65% of the picture's cells are hidden, so most of the read ground is inferred. No ground truth exists, the truth regions and the mask were drawn by eye, and the numbers describe a best-effort reading, not an automatic one.

## 4. What is not known

- **U-M1** Whether a segmenter and a classifier recover terrain and objects from real painted or generated game mockups (every cited result is on photographs or general images). P16.0 answers it. Check the licence of any model before it is recommended.
- **U-M2** Whether the overlay layers draw correctly in Godot with y-sorted objects and mixed layers (the documented facts conflict in forum reports). P16.6.
- **U-M3** Dual-grid and overlay behaviour on isometric and hexagonal grids (the pipeline's tileset note already says diamonds are unverified).
- **U-M4** Quality of overlay transitions with real art: sources describe the technique but not its look for painted styles; soft edges would use the matte.
- **U-M5** Whether a library may be added. **Decided by the owner on 2026-10-27: libraries may be used, but the framework is downloaded and used by other people, so the choice must suit them** (see 3.3).

## 5. Experiment (measured; synthetic data, seeded, reproducible)

A 64 x 48 cell scene with five terrains (water, sand, grass, forest floor, rock) from smoothed elevation and moisture fields; rendered at 16 px per cell with texture noise and boundaries warped by up to about 3 px so they do not follow the grid; 45 objects (rocks and bushes) painted over it. Five seeds. The script is not in the repository (it is a scratch file; the numbers are the evidence). It is deliberately easy: clean palette colours, no style, no lighting.

| Step | Result (mean of five seeds) | Reading |
| --- | --- | --- |
| Cell label by nearest palette colour (median Lab per cell) | **99.5%** correct | easy case; real art will be lower |
| Same with k-means (k = 5) named by nearest terrain colour | 99.5% | no gain over the named palette |
| Plus a 3x3 majority filter | **91.8%** | the filter **erased thin real features** (one-cell shores); do not use it |
| Raw plus area opening (regions under 2 cells absorbed) | 98.7% | still removes real one-cell features |
| Distinct four-corner combinations: truth / raw / majority + opening / opening only | 157 / **170** / 153 / 166 | label noise inflates tile demand by about 8%; heavy smoothing drops below the truth, which means real combinations were deleted |
| Distinct (terrain, 4-corner mask) overlay tiles needed | truth about 65, raw 66 | with overlays the demand is small and stable: a priority overlay set of 15 per non-base terrain (60 for five terrains) covers any such scene |
| Objects by **global palette distance** | rocks recalled 100%, **bushes 0%**, 0 false | objects close to their terrain's colour are invisible to a colour test |
| Objects by **local residual** (against a local median) | recall 74 to 82%, but about **270 to 300 false components per scene** | terrain boundaries and texture look like objects; precision is unusable without a segmenter or boundary exclusion |
| Objects touching (overlap allowed) | about one merged component per scene | merging is real but smaller than detection failure |
| Placement: uniform random vs Bridson (radius 24 px, 400 x 300 px) | minimum gap **5.4 px** vs **24.1 px** (guaranteed); 120 vs 136 points; 0.09 s | Poisson-disk is the right default for non-overlapping repeated objects |

Pillow-only version of the same reader (3.3): 99.45% raw and 98.63% after area opening, 0.35 s for a 1024 x 768 scene, 5.75 s for 4096 x 3072 at 64 px cells; the numpy version gave 99.49% and 98.67%.

What this supports: classify cells against the approved palette, clean conservatively and report it, use overlays so tile demand is bounded, place with Poisson-disk, and **do not rely on colour tests for objects**. What it does not support: any claim about real mockups, a segmenter's accuracy, Godot rendering, or performance in an engine.

## 6. Recommended next step

Do P16.0 first: it needs the owner's approved mockups and a chosen segmenter (an external tool, per 3.3), and every later task depends on what it finds. Until then the sensible, low-risk work is P16.1 (multi-terrain overlays on the existing tileset class), P16.3 and P16.5, which do not depend on the segmenter. No engine code goes in this repository; P16.6 produces observations, and the importer is the game project's.

## Sources (checked 2026-10-27)

Godot stable documentation: [Using TileSets](https://docs.godotengine.org/en/stable/tutorials/2d/using_tilesets.html), [Using TileMaps](https://docs.godotengine.org/en/stable/tutorials/2d/using_tilemaps.html), [TileMapLayer](https://docs.godotengine.org/en/stable/classes/class_tilemaplayer.html), [TileSet](https://docs.godotengine.org/en/stable/classes/class_tileset.html). Autotiling: [Beyond Basic Autotiling](https://www.boristhebrave.com/2021/09/12/beyond-basic-autotiling/), [Excalibur dual tilemap](https://excaliburjs.com/blog/Dual%20Tilemap%20Autotiling%20Technique), [TileMapDual](https://github.com/pablogila/TileMapDual), [Wang tiles, Cohen et al. 2003](https://graphics.uni-konstanz.de/publikationen/Cohen2003WangTilesImage/index.html). Generation: [WaveFunctionCollapse](https://github.com/mxgmn/WaveFunctionCollapse), [Bridson 2007](https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph07-poissondisk.pdf), [terrain from noise](https://redblobgames.com/maps/terrain-from-noise/). Segmentation: [segment-anything](https://github.com/facebookresearch/segment-anything), [OVSeg](https://ar5iv.labs.arxiv.org/html/2210.04150). Not read in full, so used only as pointers: the search summaries for the Red Blob Games autotile article (the fetched page was an index), the Godot forum threads, and the SoCG 2026 paper.
