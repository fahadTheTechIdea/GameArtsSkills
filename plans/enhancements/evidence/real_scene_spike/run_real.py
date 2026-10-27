"""Scratch: the terrain reader on a real painted pixel-art reference (the owner's test image). Not part of the repository; the image stays out of it."""
import json
import sys
from pathlib import Path

ROOT = Path(r"H:/Source/Repos/fahadTheTechIdea/GameArtsSkills")
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import gamearts_palette as pal  # noqa: E402
import gamearts_terrain as terrain  # noqa: E402

HERE = Path(__file__).resolve().parent
PANELS = {"beach": (0, 453), "village": (476, 1127), "forest": (1154, 1805)}
K = 6


def crop_panel(image, rows):
    top, bottom = rows
    panel = image.crop((0, top, image.width, bottom + 1))
    arr = np.asarray(panel).astype(int)
    dark_cols = (arr.sum(axis=2) < 60).mean(axis=0) > 0.9
    left = int(np.argmax(~dark_cols))
    right = len(dark_cols) - int(np.argmax(~dark_cols[::-1]))
    return panel.crop((left, 0, right, panel.height))


def native_pixel_size(panel):
    """The size of one art pixel in the upscaled picture: the block size k whose block edges carry most of the horizontal colour change."""
    arr = np.asarray(panel.convert("L")).astype(float)
    change = np.abs(np.diff(arr, axis=1)).mean(axis=0)
    best, best_score = 1, 0.0
    for k in range(2, 13):
        phase_scores = [change[phase::k].mean() / (change.mean() + 1e-9) for phase in range(k)]
        score = max(phase_scores)
        if score > best_score:
            best, best_score = k, score
    return best, round(best_score, 2)


def extract_palette(panel, count):
    """The framework's own median-cut palette extraction."""
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "p.png"
        panel.save(path)
        record = pal.extract(path, "p", Path(folder) / "out", count, Path(folder))
    return [tuple(int(c["hex"][i:i + 2], 16) for i in (1, 3, 5)) for c in record["colours"]]


def purity(panel, labels, colours, cell):
    """The share of cells in which at least 70% of the pixels are within a Lab distance of 20 of the colour the cell was given: how well one terrain colour describes the cell."""
    rgb = np.asarray(panel.convert("RGB"))
    h, w = labels.shape
    pure = 0
    lab_cache = {c: pal.rgb_to_lab(c) for c in colours}
    for cy in range(h):
        for cx in range(w):
            block = rgb[cy * cell:(cy + 1) * cell, cx * cell:(cx + 1) * cell].reshape(-1, 3)
            target = np.array(lab_cache[colours[labels[cy, cx]]])
            # sample 24 pixels of the block for speed
            sample = block[:: max(1, len(block) // 24)]
            near = sum(np.linalg.norm(np.array(pal.rgb_to_lab(tuple(int(v) for v in px))) - target) <= 20 for px in sample)
            pure += near / len(sample) >= 0.7
    return round(pure / (h * w), 3)


def main():
    full = Image.open(HERE / "reference.jpg").convert("RGB")
    report = {}
    for name, rows in PANELS.items():
        panel = crop_panel(full, rows)
        panel.save(HERE / f"{name}.png")
        pixel, score = native_pixel_size(panel)
        colours = extract_palette(panel, K)
        terrains = [{"id": f"c{i}", "colour": pal.hex_of(c)} for i, c in enumerate(colours)]
        entry = {"size": list(panel.size), "estimated_art_pixel": pixel, "pixel_grid_score": score, "palette": [pal.hex_of(c) for c in colours], "cells": {}}
        for cell in (16, 32, 48):
            width, height = panel.width // cell * cell, panel.height // cell * cell
            cropped = panel.crop((0, 0, width, height))
            read = terrain.read_labels(cropped, terrains, (cell, cell))
            labels = np.array(read["labels"])
            opened, changes = terrain.area_open(read["labels"], 2)
            combos = {tuple(labels[y:y + 2, x:x + 2].ravel()) for y in range(labels.shape[0] - 1) for x in range(labels.shape[1] - 1)}
            counts = np.bincount(labels.ravel(), minlength=K)
            entry["cells"][cell] = {"grid": [labels.shape[1], labels.shape[0]], "unclassified": len(read["unclassified"]), "label_shares": [round(float(c) / labels.size, 3) for c in counts],
                                    "purity": purity(cropped, labels, colours, cell), "cells_changed_by_area_opening_2": sum(len(c["cells"]) for c in changes),
                                    "distinct_corner_combinations": len(combos)}
            if cell == 32:
                tile = Image.new("RGB", (width, height))
                draw = ImageDraw.Draw(tile)
                for y in range(labels.shape[0]):
                    for x in range(labels.shape[1]):
                        draw.rectangle((x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1), fill=colours[labels[y, x]])
                both = Image.new("RGB", (width * 2 + 8, height), (0, 0, 0))
                both.paste(cropped, (0, 0))
                both.paste(tile, (width + 8, 0))
                both.save(HERE / f"{name}_labels32.png")
        report[name] = entry
    (HERE / "real_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
