"""Scratch: the layered-map pipeline on the owner's Cozy Soccer club-arrival mockup (read from its own repository; copied here, never changed)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"H:/Source/Repos/fahadTheTechIdea/GameArtsSkills")
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import gamearts_palette as pal  # noqa: E402

HERE = Path(__file__).resolve().parent
CELL = int(sys.argv[1]) if len(sys.argv) > 1 else 32

GROUND = {
    "asphalt": [(600, 765), (900, 850), (100, 845), (1300, 850), (1560, 300), (1100, 262), (1200, 455), (1050, 480), (1480, 700)],
    "paving": [(700, 700), (300, 700), (1200, 700), (900, 690), (250, 520), (520, 545), (400, 595), (850, 150), (840, 400), (620, 520)],
    "grass": [(330, 22), (1050, 14), (1200, 10), (1330, 22), (480, 18)],
    "crosswalk": [(460, 762), (460, 802), (460, 842)],
    "tactile": [(460, 700), (460, 897)],
    "bay_blue": [(1330, 535), (1365, 548)],
}
OCCLUDERS = {
    "brick": [(90, 340), (230, 110), (360, 600), (690, 600), (1000, 185), (1450, 150)],
    "cream_wall": [(300, 240), (480, 250), (1020, 150)],
    "blue_roof": [(300, 130), (500, 130), (1100, 90), (200, 135)],
    "window_door_dark": [(150, 260), (420, 385), (1270, 185), (1070, 185)],
    "foliage": [(240, 400), (770, 460), (940, 350), (900, 110), (100, 610), (700, 880), (1500, 900)],
    "hedge": [(1150, 312), (1000, 585), (1200, 600), (280, 420)],
    "car_white": [(1045, 345), (1530, 200)], "car_blue": [(1170, 350), (1175, 510)], "car_red": [(1310, 350)], "car_gray": [(1040, 515), (320, 790)],
    "car_cyan": [(1170, 810)],
    "iron_fence": [(420, 605), (900, 612), (1100, 610)],
    "person": [(175, 480), (475, 440), (850, 135), (855, 265), (240, 670), (1110, 680), (1320, 225), (395, 500), (580, 490)],
    "hud": [(1500, 60), (140, 895)],
    "lamp_bin": [(75, 520), (845, 520), (735, 660), (1425, 330)],
}


def median_colour(rgb, x, y, r=3):
    patch = rgb[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3)
    return "#%02X%02X%02X" % tuple(int(np.median(patch[:, i])) for i in range(3))


def native_pixel(image):
    arr = np.asarray(image.convert("L")).astype(float)
    change = np.abs(np.diff(arr, axis=1)).mean(axis=0)
    out = {}
    for k in range(2, 13):
        out[k] = round(max(change[p::k].mean() for p in range(k)) / (change.mean() + 1e-9), 2)
    return out


def main():
    source = Image.open(HERE / "club_arrival.png").convert("RGB")
    cols, rows = source.width // CELL, source.height // CELL
    cropped = source.crop((0, 0, cols * CELL, rows * CELL))
    cropped.save(HERE / "scene.png")
    rgb = np.asarray(source)
    print("size", source.size, "cells", cols, "x", rows, "cell", CELL)
    print("pixel-grid score by block size (a clean grid gives a clear peak):", native_pixel(source))
    terrains, symbols = [], "~.gcty"
    walkable = {"asphalt": True, "paving": True, "grass": True, "crosswalk": True, "tactile": True, "bay_blue": True}
    for priority, (name, points) in enumerate(GROUND.items()):
        terrains.append({"id": name, "symbol": symbols[priority], "colours": sorted({median_colour(rgb, x, y) for x, y in points}), "priority": priority, "walkable": walkable[name]})
    occluders = [{"id": name, "colours": sorted({median_colour(rgb, x, y) for x, y in points})} for name, points in OCCLUDERS.items()]
    (HERE / "terrains.json").write_text(json.dumps(terrains), encoding="utf-8")
    (HERE / "occluders.json").write_text(json.dumps(occluders), encoding="utf-8")
    out = HERE / f"map{CELL}"
    if out.exists():
        import shutil
        shutil.rmtree(out)
    done = subprocess.run([sys.executable, str(ROOT / "scripts/gamearts_layered_map.py"), "build", "--image", str(HERE / "scene.png"), "--terrains", str(HERE / "terrains.json"),
                           "--cell", f"{CELL}x{CELL}", "--name", f"club{CELL}", "--output-dir", str(out), "--occluders", str(HERE / "occluders.json")], capture_output=True, text=True)
    print("build:", done.returncode, done.stdout[-600:], done.stderr[-400:])
    data = json.loads((out / f"club{CELL}.layered_map.json").read_text(encoding="utf-8"))
    labels = data["labels"]
    counts = {}
    for row in labels:
        for ch in row:
            counts[ch] = counts.get(ch, 0) + 1
    total = sum(counts.values())
    names = {t["symbol"]: t["id"] for t in terrains}
    print("ground shares:", {names[k]: round(v / total, 3) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])})
    read = data["source"]["read"]
    print("unclassified:", len(read["unclassified_cells"]), "occluded (inferred):", len(read["occluded_cells"]), "of", total, "=", round(len(read["occluded_cells"]) / total, 3))
    combos = {(labels[y][x], labels[y][x + 1], labels[y + 1][x + 1], labels[y + 1][x]) for y in range(len(labels) - 1) for x in range(len(labels[0]) - 1)}
    print("distinct four-corner combinations of the ground:", len(combos))
    colour = {"asphalt": (70, 72, 80), "paving": (215, 190, 150), "grass": (80, 170, 60), "crosswalk": (240, 235, 220), "tactile": (230, 190, 60), "bay_blue": (50, 110, 200)}
    sym = {t["symbol"]: colour[t["id"]] for t in terrains}
    ground = Image.new("RGB", (cols * CELL, rows * CELL))
    marked = Image.new("RGB", (cols * CELL, rows * CELL))
    d, m = ImageDraw.Draw(ground), ImageDraw.Draw(marked)
    hidden = {tuple(c) for c in read["occluded_cells"]}
    for y, row in enumerate(labels):
        for x, ch in enumerate(row):
            box = (x * CELL, y * CELL, (x + 1) * CELL - 1, (y + 1) * CELL - 1)
            d.rectangle(box, fill=sym[ch])
            m.rectangle(box, fill=sym[ch] if (x, y) not in hidden else tuple(int(v * 0.45) for v in sym[ch]))
    sheet = Image.new("RGB", (cropped.width * 2 + 8, cropped.height), (0, 0, 0))
    sheet.paste(cropped, (0, 0))
    sheet.paste(ground, (cropped.width + 8, 0))
    sheet.save(HERE / f"compare{CELL}.png")
    print("saved", HERE / f"compare{CELL}.png")


if __name__ == "__main__":
    main()
