#!/usr/bin/env python3
"""Terrain from a scene: one owner of how a picture becomes a grid of terrain labels and how labels become overlay tiles (plan P16).

A scene mockup is a painting, not a tile map. This module reads one label per grid cell by taking the median colour of the cell and choosing the nearest
colour of the terrains' own palette (in L*a*b*, with the framework's palette module), says plainly which cells it could not classify, and can absorb tiny
regions with a report of what changed (it never does so unasked: a measured 3x3 majority filter erased real one-cell shores). Terrains have a priority; the
ground is the lowest and every other terrain is an overlay drawn above it, and an overlay covers every cell whose terrain has at least its priority. Each
overlay is a dual grid: a display tile sits where four cells meet, so its tile is chosen by which of those four cells the overlay covers.

A real painted scene needs two things the first design lacked (found on a painted pixel-art reference, 2026-10-27): a terrain is described by SEVERAL sample colours (grass has
light and shaded tones, and one palette colour describes only about a third of a busy scene's cells), and the things drawn on top of the ground (trees, roofs, characters)
are named classes of their own, "occluders". A cell whose nearest class is an occluder has no visible ground, so its terrain is filled in from the nearest ground cells and
the cell is reported as inferred, never as read. Filling the occluded cells cut the distinct tile combinations a scene needs by 2 to 4 times on the three test scenes.

Pillow and the standard library only, so it runs wherever the framework runs. Measured on synthetic scenes: 99.5% of cells right, 0.35 s for a 1024 x 768
picture and about 6 s for 4096 x 3072 at 64 px cells.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_palette as palette  # noqa: E402

UNKNOWN_DISTANCE = 25.0  # L*a*b* distance beyond which a cell is not near any terrain colour (about ten times the smallest difference an eye can see)


def parse_colour(text):
    """'#RRGGBB' to an (r, g, b) tuple."""
    if not (isinstance(text, str) and len(text) == 7 and text[0] == "#"):
        raise ValueError(f"a colour must be written #RRGGBB, not {text!r}")
    try:
        return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        raise ValueError(f"a colour must be written #RRGGBB, not {text!r}") from None


def _median(values):
    return sorted(values)[len(values) // 2]


def class_colours(terrains, occluders=()):
    """The sample colours of every class a cell can have: the ground terrains first, then the occluders. Each class lists one or more #RRGGBB colours."""
    classes = []
    for item in list(terrains) + list(occluders):
        samples = item.get("colours")
        if not samples:
            raise ValueError(f"{item.get('id', 'a terrain')} needs at least one sample colour (colours)")
        classes.append([parse_colour(c) for c in samples])
    return classes


def read_labels(image, terrains, cell_px, unknown_distance=UNKNOWN_DISTANCE, occluders=()):
    """The class of every cell of `image`: {"labels": rows of class indexes (the ground terrains first, then the occluders), "distance": the colour distance of each
    cell's choice, "unclassified": the (x, y) of cells farther than `unknown_distance` from every sample colour}. A class's distance is that of its nearest sample.
    The picture must be a whole number of cells wide and tall."""
    cell_w, cell_h = cell_px
    width, height = image.size
    if cell_w < 1 or cell_h < 1 or width % cell_w or height % cell_h:
        raise ValueError(f"the picture is {width} x {height} and the cell is {cell_w} x {cell_h}; it must hold a whole number of cells")
    classes = class_colours(terrains, occluders)
    rgb = image.convert("RGB")
    labels, distance, unclassified = [], [], []
    for cy in range(height // cell_h):
        label_row, distance_row = [], []
        for cx in range(width // cell_w):
            data = rgb.crop((cx * cell_w, cy * cell_h, (cx + 1) * cell_w, (cy + 1) * cell_h)).tobytes()  # bytes keep this fast and independent of Pillow's version
            median = (_median(data[0::3]), _median(data[1::3]), _median(data[2::3]))
            gaps = [min(palette.lab_distance(median, sample) for sample in samples) for samples in classes]
            best = min(range(len(classes)), key=lambda i: gaps[i])
            gap = gaps[best]
            label_row.append(best)
            distance_row.append(round(gap, 3))
            if gap > unknown_distance:
                unclassified.append((cx, cy))
        labels.append(label_row)
        distance.append(distance_row)
    return {"labels": labels, "distance": distance, "unclassified": unclassified}


def cells_from_mask(mask, cell_px, threshold=0.5):
    """The (x, y) of every cell that an occlusion mask covers by at least `threshold`. The mask is a picture the size of the scene in which white (128 or more) means an
    object lies there: a segmenter's output, or regions measured from the approved scene. A cell it covers is hidden whatever its colour, which is the only reliable way to
    separate an object from ground of a similar colour (measured: a cream wall read as a cream crossing, a blue roof as a blue parking bay)."""
    cell_w, cell_h = cell_px
    width, height = mask.size
    if cell_w < 1 or cell_h < 1 or width % cell_w or height % cell_h:
        raise ValueError(f"the mask is {width} x {height} and the cell is {cell_w} x {cell_h}; it must hold a whole number of cells")
    if not 0 < threshold <= 1:
        raise ValueError("the share of a cell the mask must cover is above 0 and at most 1")
    on = mask.convert("L").point(lambda value: 255 if value >= 128 else 0)
    cells = set()
    for cy in range(height // cell_h):
        for cx in range(width // cell_w):
            covered = on.crop((cx * cell_w, cy * cell_h, (cx + 1) * cell_w, (cy + 1) * cell_h)).tobytes().count(255)
            if covered / (cell_w * cell_h) >= threshold:
                cells.add((cx, cy))
    return cells


def mask_from_boxes(size, boxes):
    """An occlusion mask (white where an object lies) from measured regions: each box is [x, y, width, height] in the scene's pixels, or {"box": [...]}. This is the bridge
    from the scene's analysis, which measures regions, to the reader, which wants a mask; no segmenter is needed for a region someone has already measured."""
    from PIL import Image, ImageDraw
    width, height = size
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for index, item in enumerate(boxes):
        box = item["box"] if isinstance(item, dict) else item
        if not (isinstance(box, (list, tuple)) and len(box) == 4 and all(type(v) is int for v in box)):
            raise ValueError(f"box {index} must be four whole numbers [x, y, width, height]")
        x, y, w, h = box
        if w < 1 or h < 1 or x < 0 or y < 0 or x + w > width or y + h > height:
            raise ValueError(f"box {index} {box} is empty or lies outside the {width} x {height} scene")
        draw.rectangle((x, y, x + w - 1, y + h - 1), fill=255)
    return mask


def largest_square(clean):
    """The biggest square of True cells in a grid of booleans: (x, y, size), the first such in reading order, or None when no cell is True. The cleanest patch of a
    terrain to crop as a reference swatch."""
    rows, cols = len(clean), len(clean[0])
    best, where = 0, None
    above = [0] * cols
    previous = [0] * cols
    for y in range(rows):
        current = [0] * cols
        for x in range(cols):
            if clean[y][x]:
                current[x] = 1 + (min(previous[x], current[x - 1], previous[x - 1]) if x and y else 0)
                if current[x] > best:
                    best, where = current[x], (x - current[x] + 1, y - current[x] + 1)
        previous = current
    return None if where is None else (where[0], where[1], best)


def fill_occluded(labels, ground_count):
    """Give every cell whose class is an occluder (index `ground_count` or more) the terrain of the nearest ground cell, found by a breadth-first search outward from all
    ground cells, so a tie is settled by reading order and the result is the same every time. Returns (filled labels, the (x, y) of each cell that was filled): those cells
    are inferred from their surroundings, not seen."""
    rows, cols = len(labels), len(labels[0])
    out = [[label if label < ground_count else None for label in row] for row in labels]
    queue = [(x, y) for y in range(rows) for x in range(cols) if out[y][x] is not None]
    if not queue:
        raise ValueError("every cell is covered by an object, so there is no ground to read a terrain from")
    occluded = [(x, y) for y in range(rows) for x in range(cols) if out[y][x] is None]  # in reading order
    head = 0
    while head < len(queue):
        x, y = queue[head]
        head += 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < cols and 0 <= ny < rows and out[ny][nx] is None:
                out[ny][nx] = out[y][x]
                queue.append((nx, ny))
    return out, occluded


def area_open(labels, minimum):
    """Absorb every four-connected region of fewer than `minimum` cells into its most common neighbouring label. Returns (new labels, the changes made): each change
    names the cells, the label they had and the label they took. `minimum` 1 changes nothing."""
    rows, cols = len(labels), len(labels[0])
    out = [row[:] for row in labels]
    seen = [[False] * cols for _ in range(rows)]
    changes = []
    for y in range(rows):
        for x in range(cols):
            if seen[y][x]:
                continue
            label, stack, region = labels[y][x], [(y, x)], []
            seen[y][x] = True
            while stack:
                cy, cx = stack.pop()
                region.append((cx, cy))
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < rows and 0 <= nx < cols and not seen[ny][nx] and labels[ny][nx] == label:
                        seen[ny][nx] = True
                        stack.append((ny, nx))
            if len(region) >= minimum:
                continue
            around = {}
            for cx, cy in region:
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < rows and 0 <= nx < cols and labels[ny][nx] != label:
                        around[labels[ny][nx]] = around.get(labels[ny][nx], 0) + 1
            if not around:
                continue  # a region with no neighbour (the whole map) stays as it is
            taker = sorted(around, key=lambda candidate: (-around[candidate], candidate))[0]
            for cx, cy in region:
                out[cy][cx] = taker
            changes.append({"cells": sorted(region), "from": label, "to": taker})
    return out, changes


def encode_rows(labels, symbols):
    """Rows of terrain indexes as rows of the terrains' one-character symbols."""
    return ["".join(symbols[i] for i in row) for row in labels]


def decode_rows(rows, symbols):
    """The inverse of `encode_rows`; a character that is no terrain's symbol is refused by name."""
    index = {symbol: i for i, symbol in enumerate(symbols)}
    width = len(rows[0]) if rows else 0
    labels = []
    for y, row in enumerate(rows):
        if len(row) != width:
            raise ValueError(f"row {y} has {len(row)} cells and row 0 has {width}; every row must be as long as the first")
        for x, char in enumerate(row):
            if char not in index:
                raise ValueError(f"cell ({x}, {y}) is {char!r}, which is no terrain's symbol")
        labels.append([index[c] for c in row])
    return labels


def covered(labels, priorities, terrain_index):
    """The cells an overlay of `terrain_index` covers: those whose terrain has at least its priority (the base is lowest, so it covers everything)."""
    wanted = priorities[terrain_index]
    return [[priorities[label] >= wanted for label in row] for row in labels]


def overlay_corners(mask):
    """The dual grid of an overlay: for each display tile position (x, y), 0 <= x <= width and 0 <= y <= height, the four cells that meet there as
    (top_left, top_right, bottom_right, bottom_left), each True when the overlay covers it. A cell outside the map counts as the nearest cell inside, so the
    overlay runs off the edge instead of ending in a border."""
    rows, cols = len(mask), len(mask[0])

    def cell(x, y):
        return mask[min(max(y, 0), rows - 1)][min(max(x, 0), cols - 1)]
    return {(x, y): (cell(x - 1, y - 1), cell(x, y - 1), cell(x, y), cell(x - 1, y)) for y in range(rows + 1) for x in range(cols + 1)}


def corner_number(corners):
    """The four corners as one number, top_left 1, top_right 2, bottom_right 4, bottom_left 8: 0 is no overlay here, 15 is the overlay's whole interior."""
    return sum(bit for bit, on in zip((1, 2, 4, 8), corners) if on)
