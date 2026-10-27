"""Scratch: terrains defined by sample points on the real beach and forest panels, objects left out and their ground filled in (coordinates are the panel's own pixels)."""
import json
import sys
from collections import deque
from pathlib import Path

ROOT = Path(r"H:/Source/Repos/fahadTheTechIdea/GameArtsSkills")
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import gamearts_palette as pal  # noqa: E402

HERE = Path(__file__).resolve().parent
CELL = 32
PANELS = {
    "beach": {
        "colours": {"sand": (222, 180, 110), "wet_sand": (180, 140, 90), "shallow": (120, 150, 170), "foam": (240, 240, 240), "rock": (80, 85, 70), "character": (230, 120, 60),
                    "jelly": (240, 110, 100), "wood": (80, 55, 45), "shadow": (30, 30, 30), "plant": (60, 110, 50)},
        "samples": [("sand", "ground", 600, 300), ("sand", "ground", 400, 330), ("sand", "ground", 200, 360), ("sand", "ground", 300, 430), ("sand", "ground", 700, 250),
                    ("sand", "ground", 500, 200), ("wet_sand", "ground", 170, 150), ("wet_sand", "ground", 280, 30), ("wet_sand", "ground", 390, 22),
                    ("shallow", "ground", 60, 105), ("shallow", "ground", 210, 100), ("shallow", "ground", 230, 160), ("foam", "ground", 30, 40), ("foam", "ground", 60, 70),
                    ("rock", "object", 60, 200), ("rock", "object", 1000, 400), ("rock", "object", 1100, 150), ("rock", "object", 560, 400), ("rock", "object", 860, 170),
                    ("character", "object", 560, 110), ("character", "object", 750, 120), ("jelly", "object", 320, 170), ("jelly", "object", 30, 290), ("wood", "object", 180, 50),
                    ("wood", "object", 880, 60), ("shadow", "object", 560, 150), ("shadow", "object", 740, 170), ("shadow", "object", 330, 255), ("plant", "object", 355, 70)],
    },
    "forest": {
        "colours": {"dirt": (150, 85, 70), "moss": (170, 160, 50), "moss_dark": (80, 110, 40), "trunk": (110, 70, 40), "leaf_orange": (230, 110, 50), "character": (80, 170, 170),
                    "stone": (120, 125, 100), "ghost": (240, 230, 190), "branch": (40, 25, 25), "deer": (60, 120, 60)},
        "samples": [("dirt", "ground", 500, 400), ("dirt", "ground", 560, 330), ("dirt", "ground", 300, 430), ("dirt", "ground", 450, 360), ("dirt", "ground", 610, 440),
                    ("moss", "ground", 470, 200), ("moss", "ground", 650, 280), ("moss", "ground", 300, 300), ("moss", "ground", 200, 360), ("moss", "ground", 800, 330),
                    ("moss", "ground", 330, 580), ("moss_dark", "ground", 120, 120), ("moss_dark", "ground", 250, 520), ("moss_dark", "ground", 620, 480),
                    ("trunk", "object", 380, 230), ("trunk", "object", 620, 350), ("trunk", "object", 260, 190), ("trunk", "object", 600, 120), ("trunk", "object", 60, 290),
                    ("leaf_orange", "object", 900, 110), ("leaf_orange", "object", 850, 330), ("character", "object", 415, 420), ("stone", "object", 460, 130), ("stone", "object", 770, 260),
                    ("stone", "object", 510, 540), ("ghost", "object", 290, 250), ("branch", "object", 700, 500), ("branch", "object", 1000, 480), ("deer", "object", 725, 110)],
    },
}


def median_colour(rgb, x, y, r=3):
    patch = rgb[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3)
    return tuple(int(np.median(patch[:, i])) for i in range(3))


def run(name, spec):
    panel = Image.open(HERE / f"{name}.png").convert("RGB")
    rgb = np.asarray(panel)
    samples = [(n, g, median_colour(rgb, x, y)) for n, g, x, y in spec["samples"]]
    group = {n: g for n, g, _ in samples}
    lab = [(n, np.array(pal.rgb_to_lab(c))) for n, _, c in samples]
    width, height = panel.width // CELL * CELL, panel.height // CELL * CELL
    cols, rows = width // CELL, height // CELL
    labels = [[None] * cols for _ in range(rows)]
    far = 0
    for cy in range(rows):
        for cx in range(cols):
            block = rgb[cy * CELL:(cy + 1) * CELL, cx * CELL:(cx + 1) * CELL].reshape(-1, 3)
            v = np.array(pal.rgb_to_lab(tuple(int(np.median(block[:, i])) for i in range(3))))
            best = min(lab, key=lambda s: np.linalg.norm(s[1] - v))
            labels[cy][cx] = best[0]
            far += np.linalg.norm(best[1] - v) > 25
    ground = [[labels[y][x] if group[labels[y][x]] == "ground" else None for x in range(cols)] for y in range(rows)]
    queue = deque((x, y) for y in range(rows) for x in range(cols) if ground[y][x] is not None)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < cols and 0 <= ny < rows and ground[ny][nx] is None:
                ground[ny][nx] = ground[y][x]
                queue.append((nx, ny))
    colour = spec["colours"]

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
    out.save(HERE / f"{name}_seeded.png")
    objects = sum(1 for y in range(rows) for x in range(cols) if group[labels[y][x]] == "object")
    share = {}
    for y in range(rows):
        for x in range(cols):
            share[ground[y][x]] = share.get(ground[y][x], 0) + 1
    combos = {(ground[y][x], ground[y][x + 1], ground[y + 1][x + 1], ground[y + 1][x]) for y in range(rows - 1) for x in range(cols - 1)}
    result = {"panel": name, "cells": [cols, rows], "object_cells": objects, "object_share": round(objects / (rows * cols), 3), "far_from_every_sample": int(far),
              "ground_terrains": sorted(share), "ground_shares": {k: round(v / (rows * cols), 3) for k, v in sorted(share.items(), key=lambda kv: -kv[1])},
              "ground_corner_combinations": len(combos)}
    return result


if __name__ == "__main__":
    print(json.dumps([run(name, spec) for name, spec in PANELS.items()], indent=1))
