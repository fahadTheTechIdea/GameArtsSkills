"""Scratch: does treating near-ties between a ground class and an occluder class as uncertain fix the cream-wall-as-crosswalk and blue-roof-as-bay errors? Hand-made truth regions, no ML."""
import json
import sys
from pathlib import Path

ROOT = Path(r"H:/Source/Repos/fahadTheTechIdea/GameArtsSkills")
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import gamearts_palette as pal  # noqa: E402
import gamearts_terrain as terrain  # noqa: E402

HERE = Path(__file__).resolve().parent
CELL = 32
terrains = json.loads((HERE / "terrains.json").read_text(encoding="utf-8"))
occluders = json.loads((HERE / "occluders.json").read_text(encoding="utf-8"))
image = Image.open(HERE / "scene.png")
classes = terrain.class_colours(terrains, occluders)
ground_n = len(terrains)
rgb = image.convert("RGB")
cols, rows = image.width // CELL, image.height // CELL

# per cell: the nearest ground class and the nearest occluder class, with their distances
cells = {}
for cy in range(rows):
    for cx in range(cols):
        data = rgb.crop((cx * CELL, cy * CELL, (cx + 1) * CELL, (cy + 1) * CELL)).tobytes()
        med = tuple(sorted(data[i::3])[len(data) // 6] for i in range(3))
        gaps = [min(pal.lab_distance(med, s) for s in samples) for samples in classes]
        g = min(range(ground_n), key=lambda i: gaps[i])
        o = min(range(ground_n, len(classes)), key=lambda i: gaps[i])
        cells[(cx, cy)] = (g, gaps[g], o, gaps[o])


def labels_with(margin):
    out = [[None] * cols for _ in range(rows)]
    for (cx, cy), (g, gd, o, od) in cells.items():
        occluded = od < gd + margin  # an occluder is the nearer class, or nearly as near as the nearest ground
        out[cy][cx] = ground_n if occluded else g
    filled, hidden = terrain.fill_occluded(out, ground_n)
    return filled, hidden


# truth regions chosen by looking at the picture (original pixel coordinates -> cells)
def region(x0, y0, x1, y1):
    return {(x, y) for x in range(x0 // CELL, x1 // CELL + 1) for y in range(y0 // CELL, y1 // CELL + 1) if x < cols and y < rows}


building = region(60, 120, 790, 410)            # the club facade: roof, walls, windows: not ground at all
roof_blue = region(60, 100, 790, 200)           # the blue roof
crosswalk_truth = region(415, 735, 505, 905)    # the zebra crossing
names = [t["id"] for t in terrains]
for margin in (0, 3, 6, 10, 15):
    labels, hidden = labels_with(margin)
    ground_in_building = sum(1 for c in building if (c not in set(map(tuple, hidden))))
    cw_index = names.index("crosswalk")
    bay_index = names.index("bay_blue")
    crosswalk_cells = {(x, y) for y in range(rows) for x in range(cols) if labels[y][x] == cw_index}
    crosswalk_outside = len(crosswalk_cells - crosswalk_truth)
    bay_cells = {(x, y) for y in range(rows) for x in range(cols) if labels[y][x] == bay_index}
    bay_truth = region(1290, 490, 1395, 575)
    print(f"margin {margin:>2}: hidden cells {len(hidden):4d} ({len(hidden) / (rows * cols):.0%}); building cells read as VISIBLE ground {ground_in_building:3d} of {len(building)}; "
          f"crosswalk cells {len(crosswalk_cells):3d} (outside the real crossing: {crosswalk_outside:3d}); blue bay cells {len(bay_cells):3d} (outside the real bay: {len(bay_cells - bay_truth):3d})")
