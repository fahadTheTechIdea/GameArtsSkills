"""Scratch: the club-arrival mockup read with an occlusion mask (regions drawn by hand from the picture), against colour-only reading."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"H:/Source/Repos/fahadTheTechIdea/GameArtsSkills")
sys.path.insert(0, str(ROOT / "scripts"))
from PIL import Image, ImageDraw  # noqa: E402

HERE = Path(__file__).resolve().parent
CELL = 32
BOXES = [
    (45, 65, 805, 445), (950, 60, 1470, 265), (1480, 125, 1590, 270),                         # the two buildings and the van
    (170, 330, 310, 510), (700, 400, 800, 560), (870, 280, 980, 430), (880, 60, 970, 190), (60, 520, 200, 700), (0, 0, 120, 200),
    (500, 860, 1672, 941), (1380, 470, 1480, 600),                                              # trees and the foliage row
    (0, 568, 1672, 660),                                                                         # the fence, gates and hedges along the pavement
    (1000, 300, 1100, 410), (1120, 300, 1230, 410), (1260, 300, 1360, 410), (990, 465, 1095, 575), (1125, 465, 1230, 575), (240, 740, 410, 835), (1100, 775, 1255, 860),  # cars
    (150, 450, 200, 515), (380, 475, 420, 550), (450, 420, 495, 490), (560, 445, 605, 525), (215, 640, 255, 705), (1085, 640, 1130, 710), (1300, 205, 1340, 270),
    (830, 115, 860, 180), (840, 245, 875, 310),                                                  # people
    (1395, 20, 1650, 110), (15, 865, 290, 925),                                                  # the HUD
    (60, 490, 90, 690), (830, 490, 860, 680), (1410, 285, 1440, 370),                            # lamp posts
]


def run(name, with_colour):
    out = HERE / f"map_{name}"
    if out.exists():
        import shutil
        shutil.rmtree(out)
    command = [sys.executable, str(ROOT / "scripts/gamearts_layered_map.py"), "build", "--image", str(HERE / "scene.png"), "--terrains", str(HERE / "terrains.json"),
               "--cell", f"{CELL}x{CELL}", "--name", name, "--output-dir", str(out)]
    if name != "colour_only":
        command += ["--occlusion-mask", str(HERE / "mask.png")]
    if with_colour:
        command += ["--occluders", str(HERE / "occluders.json")]
    done = subprocess.run(command, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return json.loads((out / f"{name}.layered_map.json").read_text(encoding="utf-8"))


def main():
    source = Image.open(HERE / "scene.png")
    mask = Image.new("L", source.size, 0)
    draw = ImageDraw.Draw(mask)
    for box in BOXES:
        draw.rectangle(box, fill=255)
    mask.save(HERE / "mask.png")
    terrains = json.loads((HERE / "terrains.json").read_text(encoding="utf-8"))
    names = {t["symbol"]: t["id"] for t in terrains}
    cols, rows = source.width // CELL, source.height // CELL

    def region(x0, y0, x1, y1):
        return {(x, y) for x in range(x0 // CELL, x1 // CELL + 1) for y in range(y0 // CELL, y1 // CELL + 1) if x < cols and y < rows}
    building = region(60, 120, 790, 410)
    crossing = region(415, 735, 505, 905)
    bay = region(1290, 490, 1395, 575)
    results = {}
    for label, name, colour in (("colour occluders only", "colour_only", True), ("mask only", "mask_only", False), ("mask + colour occluders", "mask_colour", True)):
        data = run(name, colour)
        hidden = {tuple(c) for c in data["source"]["read"]["occluded_cells"]}
        grid = data["labels"]
        shares = {}
        for row in grid:
            for ch in row:
                shares[names[ch]] = shares.get(names[ch], 0) + 1
        total = rows * cols
        cw = {(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "c"}
        bl = {(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "y"}
        combos = {(grid[y][x], grid[y][x + 1], grid[y + 1][x + 1], grid[y + 1][x]) for y in range(rows - 1) for x in range(cols - 1)}
        results[label] = {"hidden_share": round(len(hidden) / total, 3), "building_cells_read_as_visible_ground": len(building - hidden), "of": len(building),
                          "crosswalk_cells_outside_real_crossing": len(cw - crossing), "crosswalk_cells_inside": len(cw & crossing), "blue_bay_cells_outside_real_bay": len(bl - bay),
                          "ground_shares": {k: round(v / total, 3) for k, v in sorted(shares.items(), key=lambda kv: -kv[1])}, "distinct_corner_combinations": len(combos)}
        if name == "mask_only":
            colours = {"asphalt": (70, 72, 80), "paving": (215, 190, 150), "grass": (80, 170, 60), "crosswalk": (240, 235, 220), "tactile": (230, 190, 60), "bay_blue": (50, 110, 200)}
            symbol_colour = {t["symbol"]: colours[t["id"]] for t in terrains}
            ground = Image.new("RGB", (cols * CELL, rows * CELL))
            d = ImageDraw.Draw(ground)
            for y, row in enumerate(grid):
                for x, ch in enumerate(row):
                    colour = symbol_colour[ch]
                    if (x, y) in hidden:
                        colour = tuple(int(v * 0.6) for v in colour)
                    d.rectangle((x * CELL, y * CELL, (x + 1) * CELL - 1, (y + 1) * CELL - 1), fill=colour)
            sheet = Image.new("RGB", (cols * CELL * 2 + 8, rows * CELL), (0, 0, 0))
            sheet.paste(source.crop((0, 0, cols * CELL, rows * CELL)), (0, 0))
            sheet.paste(ground, (cols * CELL + 8, 0))
            sheet.save(HERE / "compare_mask.png")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
