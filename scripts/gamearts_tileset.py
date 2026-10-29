#!/usr/bin/env python3
"""Single owner of what a tileset layout is, which tiles it requires and what each tile's neighbour labels mean.

A tile carries neutral labels for the eight places around its centre, named clockwise from the top (the order Tiled's wang ids use):
top, top_right, right, bottom_right, bottom, bottom_left, left, top_left. Each label is the name of the terrain found there. Engines and editors name
these positions their own way (Tiled's wang ids, an engine's peering bits); mapping to them is an export, never part of the tile.

Layouts (two terrains unless noted; terrains[0] is the terrain the pieces are made of, terrains[1] is what lies around it):
  single          one tile (one terrain)
  variants        one or more interchangeable tiles of one terrain (one terrain)
  wang_corner_16  the 16 tiles of every combination of four corner terrains; sides are not used
  wang_edge_16    the 16 tiles of every combination of four edge terrains; corners are not used
  blob_47         the 47 tiles of every distinct arrangement of the eight neighbours, where a corner counts only when both sides touching it do
  dual_grid_16    the same 16 corner tiles as wang_corner_16, drawn on a grid offset by half a tile (a dual-grid renderer places them)
The builder, the validator and the Tiled export all ask this module, so a tileset is judged and exported the same way everywhere.
"""
import itertools

LAYOUTS = ("single", "variants", "wang_corner_16", "wang_edge_16", "blob_47", "dual_grid_16")
SIDES = ("top", "top_right", "right", "bottom_right", "bottom", "bottom_left", "left", "top_left")
CORNERS = ("top_right", "bottom_right", "bottom_left", "top_left")
EDGES = ("top", "right", "bottom", "left")
TERRAIN_COUNT = {"single": 1, "variants": 1, "wang_corner_16": 2, "wang_edge_16": 2, "blob_47": 2, "dual_grid_16": 2}
USED = {"single": SIDES, "variants": SIDES, "wang_corner_16": CORNERS, "dual_grid_16": CORNERS, "wang_edge_16": EDGES, "blob_47": SIDES}
# the two sides that touch each corner, used to decide when a blob corner counts
CORNER_SIDES = {"top_right": ("top", "right"), "bottom_right": ("bottom", "right"), "bottom_left": ("bottom", "left"), "top_left": ("top", "left")}
# the labels along each side of a tile, read left to right or top to bottom, so that one tile's right side lines up with another tile's left side
SIDE_LABELS = {"corner": {"top": ("top_left", "top_right"), "bottom": ("bottom_left", "bottom_right"), "left": ("top_left", "bottom_left"), "right": ("top_right", "bottom_right")},
               "edge": {"top": ("top",), "bottom": ("bottom",), "left": ("left",), "right": ("right",)},
               "blob": {"top": ("top_left", "top", "top_right"), "bottom": ("bottom_left", "bottom", "bottom_right"),
                        "left": ("top_left", "left", "bottom_left"), "right": ("top_right", "right", "bottom_right")},
               "same": {"top": ("top",), "bottom": ("bottom",), "left": ("left",), "right": ("right",)}}
SIDE_KIND = {"single": "same", "variants": "same", "wang_corner_16": "corner", "dual_grid_16": "corner", "wang_edge_16": "edge", "blob_47": "blob"}
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}


def animation_frame_ids(tileset):
    """The ids of tiles that exist only as frames of another tile's animation. They take the labels of the tile they animate."""
    return {frame["tile"] for animation in tileset.get("animations", []) for frame in animation["frames"] if frame["tile"] != animation["tile"]}


def animation_problems(tileset):
    """Every reason the animations are not sound; empty when they are. A tile has one animation, a frame belongs to one animation, and every id exists."""
    problems, count = [], len(tileset["tiles"])
    animated, owner = {}, {}
    for number, animation in enumerate(tileset.get("animations", []), 1):
        base, name = animation["tile"], f"animation {number} (tile {animation['tile']})"
        if not 0 <= base < count:
            problems.append(f"{name}: tile {base} is not in the tileset")
            continue
        if base in animated:
            problems.append(f"{name}: tile {base} already has animation {animated[base]}; a tile has one animation")
        animated.setdefault(base, number)
        for frame in animation["frames"]:
            tile = frame["tile"]
            if not 0 <= tile < count:
                problems.append(f"{name}: frame tile {tile} is not in the tileset")
            elif tile != base and owner.setdefault(tile, number) != number:
                problems.append(f"{name}: tile {tile} is already a frame of animation {owner[tile]}; a frame belongs to one animation")
    problems += [f"tile {tile} is a frame of animation {number} and is also animated itself; a frame has no animation of its own" for tile, number in sorted(owner.items()) if tile in animated]
    return [f"animation: {problem}" for problem in problems]


def _indexes(layout, neighbours, terrains):
    """The terrain index (0 or 1) of every used side, or None when a used side is missing or names an unknown terrain."""
    result = {}
    for side in USED[layout]:
        label = (neighbours or {}).get(side)
        if label not in terrains:
            return None
        result[side] = terrains.index(label)
    return result


def _normalised(layout, indexes):
    """Blob corners count only when both sides touching them are the inside terrain; every other corner is the outside terrain."""
    if layout != "blob_47":
        return dict(indexes)
    result = dict(indexes)
    for corner, (first, second) in CORNER_SIDES.items():
        if indexes[first] != 0 or indexes[second] != 0:
            result[corner] = 1
    return result


def identity(layout, neighbours, terrains):
    """The tile's place among its layout's tiles, or None when its labels cannot belong to the layout. Blob corners are normalised."""
    indexes = _indexes(layout, neighbours, terrains)
    if indexes is None:
        return None
    if layout in ("single", "variants"):
        return ("all",) if set(indexes.values()) == {0} else None
    normal = _normalised(layout, indexes)
    return tuple(normal[side] for side in USED[layout])


def tile_name(layout, neighbours, terrains):
    """A tile described in words, for messages: which terrain lies at each place the layout uses."""
    if layout in ("single", "variants"):
        return f"{terrains[0]} tile"
    if layout == "blob_47":
        inside = [side for side in SIDES if neighbours.get(side) == terrains[0]]
        return f"{terrains[0]} blob with {terrains[0]} to the " + ", ".join(inside) if inside else f"isolated {terrains[0]} blob"
    kind = "corners" if layout in ("wang_corner_16", "dual_grid_16") else "edges"
    return f"{kind} " + " ".join(f"{side}={neighbours.get(side)}" for side in USED[layout])


def layout_tiles(layout, terrains):
    """The tiles a complete tileset of this layout has, each as {"identity", "neighbours"}; variants and single need one."""
    if layout in ("single", "variants"):
        return [{"identity": ("all",), "neighbours": {side: terrains[0] for side in SIDES}}]
    used = USED[layout]
    seen, tiles = set(), []
    for combo in itertools.product((0, 1), repeat=len(used)):
        normal = _normalised(layout, dict(zip(used, combo)))
        key = tuple(normal[side] for side in used)
        if key in seen:
            continue
        seen.add(key)
        tiles.append({"identity": key, "neighbours": {side: terrains[index] for side, index in zip(used, key)}})
    return tiles


def _label_shape_problems(layout, tile, name, terrains):
    problems = []
    neighbours = tile.get("neighbours") or {}
    for side in SIDES:
        label = neighbours.get(side)
        if side in USED[layout]:
            if label not in terrains:
                problems.append(f"{name}: {side} is {label!r}, which is not one of the terrains {', '.join(terrains)}")
        elif label is not None:
            problems.append(f"{name}: {side} is not used by layout {layout} and must be left out")
    if tile.get("terrain") != terrains[0]:
        problems.append(f"{name}: terrain is {tile.get('terrain')!r}, but the pieces of this tileset are {terrains[0]!r}")
    if layout == "blob_47" and not problems:
        declared = _indexes(layout, neighbours, terrains)
        if declared != _normalised(layout, declared):
            problems.append(f"{name}: a corner is {terrains[0]} while a side next to it is {terrains[1]}; that arrangement is one of the 256 raw combinations "
                            f"but not one of the 47 tiles (the corner does not count), so label the corner {terrains[1]}")
    return problems


def label_problems(tileset):
    """Every reason the tiles' labels do not make a complete, consistent tileset of the declared layout; empty when they do."""
    layout, terrains, tiles = tileset["layout"], tileset["terrains"], tileset["tiles"]
    problems = []
    if len(terrains) != TERRAIN_COUNT[layout]:
        problems.append(f"layout {layout} needs {TERRAIN_COUNT[layout]} terrain(s), but {len(terrains)} are declared")
        return problems
    ids = [tile["id"] for tile in tiles]
    if ids != list(range(len(tiles))):
        problems.append("tile ids must be 0, 1, 2 ... in the order of the atlas frames")
    shape_bad = False
    seen = {}
    frames = animation_frame_ids(tileset)
    for tile in tiles:
        if tile["id"] in frames:
            continue  # a frame of another tile's animation takes that tile's labels, so it is neither a repeat nor a missing piece
        name = f"tile {tile['id']}"
        shape = _label_shape_problems(layout, tile, name, terrains)
        problems += shape
        if shape:
            shape_bad = True
            continue
        key = identity(layout, tile.get("neighbours"), terrains)
        if layout == "single" and seen:
            problems.append(f"{name}: a single-tile layout has exactly one tile")
        elif layout != "variants" and key in seen:
            problems.append(f"{name} ({tile_name(layout, tile['neighbours'], terrains)}) repeats tile {seen[key]}")
        seen.setdefault(key, tile["id"])
    if not tiles:
        problems.append("the tileset has no tiles")
    if not shape_bad and layout not in ("variants",):
        for required in layout_tiles(layout, terrains):
            if required["identity"] not in seen:
                problems.append(f"missing tile: {tile_name(layout, required['neighbours'], terrains)}")
    return problems + animation_problems(tileset)


def edge_signature(layout, neighbours, side):
    """What lies along one side of a tile. Two tiles may sit side by side when the first's right signature equals the second's left one."""
    return tuple(neighbours.get(label) for label in SIDE_LABELS[SIDE_KIND[layout]][side])


def wang_id(layout, neighbours, terrains):
    """Tiled's wang id: eight colour indexes in the order top, top-right, right, bottom-right, bottom, bottom-left, left, top-left, where 1 is
    the first terrain, 2 the second and 0 a place the layout does not use."""
    return [terrains.index(neighbours[side]) + 1 if side in USED[layout] else 0 for side in SIDES]
