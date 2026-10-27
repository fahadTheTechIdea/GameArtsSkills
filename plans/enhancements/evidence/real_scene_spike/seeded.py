"""Scratch: terrains defined by sample points on the real village panel (what an agent could propose from the mockup), objects left out and their ground filled in."""
import sys
from collections import deque
from pathlib import Path

ROOT = Path(r"H:/Source/Repos/fahadTheTechIdea/GameArtsSkills")
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import gamearts_palette as pal  # noqa: E402

HERE = Path(__file__).resolve().parent
SCALE = 1.155  # the panel as displayed (1000 px wide) to its real size (1155 px)
# (name, group, displayed x, displayed y). Ground terrains first; objects are what the picture draws on top of the ground.
SAMPLES = [
    ("grass_light", "ground", 480, 330), ("grass_light", "ground", 700, 200), ("grass_light", "ground", 300, 250), ("grass_light", "ground", 560, 420),
    ("grass_shade", "ground", 420, 440), ("grass_shade", "ground", 180, 400), ("grass_shade", "ground", 330, 300),
    ("path", "ground", 580, 215), ("path", "ground", 540, 450), ("path", "ground", 760, 215), ("path", "ground", 130, 430),
    ("water", "ground", 760, 510), ("water", "ground", 640, 520), ("water", "ground", 40, 120), ("water", "ground", 190, 40),
    ("canopy", "object", 700, 350), ("canopy", "object", 940, 330), ("canopy", "object", 880, 160), ("canopy", "object", 700, 520),
    ("roof", "object", 130, 250), ("roof", "object", 420, 40), ("wall", "object", 330, 110), ("door", "object", 60, 330),
    ("character", "object", 330, 320), ("character", "object", 600, 220), ("shadow", "object", 310, 375), ("shadow", "object", 580, 255),
]
CELL = 32


def median_colour(rgb, x, y, r=3):
    patch = rgb[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3)
    return tuple(int(np.median(patch[:, i])) for i in range(3))


def main():
    panel = Image.open(HERE / "village.png").convert("RGB")
    rgb = np.asarray(panel)
    samples = [(n, g, median_colour(rgb, int(x * SCALE), int(y * SCALE))) for n, g, x, y in SAMPLES]
    names = sorted({n for n, _, _ in samples})
    group = {n: g for n, g, _ in samples}
    lab = [(n, np.array(pal.rgb_to_lab(c))) for n, _, c in samples]
    width, height = panel.width // CELL * CELL, panel.height // CELL * CELL
    cols, rows = width // CELL, height // CELL
    labels = [[None] * cols for _ in range(rows)]
    distance = [[0.0] * cols for _ in range(rows)]
    for cy in range(rows):
        for cx in range(cols):
            block = rgb[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL].reshape(-1, 3)
            med = tuple(int(np.median(block[:, i])) for i in range(3))
            v = np.array(pal.rgb_to_lab(med))
            best = min(lab, key=lambda s: np.linalg.norm(s[1] - v))
            labels[cy][cx] = best[0]
            distance[cy][cx] = float(np.linalg.norm(best[1] - v))
    object_cells = [(x, y) for y in range(rows) for x in range(cols) if group[labels[y][x]] == "object"]
    # fill each object cell with the nearest ground cell's terrain (breadth-first from all ground cells)
    ground = [[labels[y][x] if group[labels[y][x]] == "ground" else None for x in range(cols)] for y in range(rows)]
    queue = deque((x, y) for y in range(rows) for x in range(cols) if ground[y][x] is not None)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < cols and 0 <= ny < rows and ground[ny][nx] is None:
                ground[ny][nx] = ground[y][x]
                queue.append((nx, ny))
    colour = {"grass_light": (170, 210, 60), "grass_shade": (90, 130, 40), "path": (150, 100, 60), "water": (90, 190, 200), "canopy": (20, 60, 30), "roof": (120, 80, 50),
              "wall": (230, 200, 150), "door": (200, 140, 40), "character": (230, 120, 60), "shadow": (30, 30, 30)}

    def render(grid):
        img = Image.new("RGB", (width, height))
        d = ImageDraw.Draw(img)
        for y in range(rows):
            for x in range(cols):
                d.rectangle((x * CELL, y * CELL, (x + 1) * CELL - 1, (y + 1) * CELL - 1), fill=colour[grid[y][x]])
        return img
    out = Image.new("RGB", (width * 3 + 16, height), (0, 0, 0))
    out.paste(panel.crop((0, 0, width, height)), (0, 0))
    out.paste(render(labels), (width + 8, 0))
    out.paste(render(ground), (width * 2 + 16, 0))
    out.save(HERE / "village_seeded.png")
    share = {n: sum(row.count(n) for row in labels) / (rows * cols) for n in names}
    print("samples:", {n: [tuple(c) for nn, g, c in samples if nn == n][:1] for n in names})
    print("cell shares:", {k: round(v, 3) for k, v in sorted(share.items(), key=lambda kv: -kv[1])})
    print("object cells:", len(object_cells), "of", rows * cols, "->", round(len(object_cells) / (rows * cols), 3))
    far = sum(1 for y in range(rows) for x in range(cols) if distance[y][x] > 25)
    print("cells farther than Lab 25 from every sample:", far)
    ground_terrains = sorted({ground[y][x] for y in range(rows) for x in range(cols)})
    print("ground terrains after filling:", ground_terrains)
    combos = {(ground[y][x], ground[y][x + 1], ground[y + 1][x + 1], ground[y + 1][x]) for y in range(rows - 1) for x in range(cols - 1)}
    print("distinct four-corner combinations of the ground:", len(combos))


if __name__ == "__main__":
    main()
