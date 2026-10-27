#!/usr/bin/env python3
"""Does a library make a difference to reading terrain from a scene? (plan P16, research decision of 2026-10-27)

Runs the same job through different libraries on the same seeded synthetic scenes and prints what changed: accuracy against the known labels, agreement with the
framework's own Pillow-only reader, time, and for cleanup and object placement the same comparison. Everything here except the Pillow reader is OPTIONAL
tooling: this file is evidence, it is not shipped, and the framework does not import any of these libraries.

  python plans/enhancements/evidence/terrain_backend_comparison.py [--libs DIR]    (DIR holds extra site-packages, put first on the path)

A library that is not installed is reported as missing, not skipped silently. The scenes are synthetic and easy (clean palette, no art style): the result
says how the libraries compare on this job, not how well any of them reads a real painted mockup (that is task P16.0).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--libs", type=Path)
ARGS = parser.parse_args()
if ARGS.libs:
    sys.path.insert(0, str(ARGS.libs))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import gamearts_palette as palette  # noqa: E402
import gamearts_terrain as terrain  # noqa: E402

WIDTH, HEIGHT, CELL = 64, 48, 16
OBJECTS = 90  # per scene, on the 64 x 48 cell map
NAMES = ["water", "sand", "grass", "forest", "rock"]
COLOURS = {"water": (60, 110, 190), "sand": (222, 205, 150), "grass": (96, 170, 80), "forest": (50, 110, 60), "rock": (130, 128, 125)}
TERRAINS = [{"id": name, "colour": palette.hex_of(COLOURS[name])} for name in NAMES]
PALETTE = [COLOURS[name] for name in NAMES]


def present(name):
    try:
        module = __import__(name)
        return getattr(module, "__version__", "installed")
    except ImportError:
        return None


VERSIONS = {name: present(name) for name in ("numpy", "PIL", "cv2", "scipy", "skimage")}


# --------------------------------------------------------------------------------------------- the scene (seeded, no library but numpy and PIL)
def smooth(rng, scale):
    small = rng.random((HEIGHT // scale + 2, WIDTH // scale + 2)).astype(np.float32)
    big = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((WIDTH, HEIGHT), Image.BICUBIC), np.float32) / 255
    return big


def truth_labels(rng):
    elevation = smooth(rng, 8) * 0.7 + smooth(rng, 3) * 0.3
    moisture = smooth(rng, 6)
    elevation = (elevation - elevation.min()) / (np.ptp(elevation) + 1e-9)
    moisture = (moisture - moisture.min()) / (np.ptp(moisture) + 1e-9)
    labels = np.full((HEIGHT, WIDTH), 2, np.uint8)
    labels[elevation < 0.30] = 0
    labels[(elevation >= 0.30) & (elevation < 0.38)] = 1
    labels[(elevation >= 0.38) & (moisture > 0.62)] = 3
    labels[elevation > 0.78] = 4
    return labels


def render(labels, rng, cell):
    """Paint each cell's terrain colour with texture noise and boundaries warped off the grid, then dot rocks over it."""
    big = np.kron(labels, np.ones((cell, cell), np.uint8))
    image = np.zeros(big.shape + (3,), np.float32)
    for index, name in enumerate(NAMES):
        image[big == index] = COLOURS[name]
    shift = rng.integers(-3, 4, size=big.shape[0])
    for y in range(big.shape[0]):  # a per-row horizontal wobble, so boundaries do not follow the grid
        image[y] = np.roll(image[y], int(shift[y]), axis=0)
    image += rng.standard_normal(image.shape).astype(np.float32) * 9
    picture = Image.fromarray(np.clip(image, 0, 255).astype(np.uint8))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(picture)
    for _ in range(OBJECTS):  # rocks and bushes drawn over the terrain: what makes a mean differ from a median
        x, y = int(rng.integers(20, picture.width - 20)), int(rng.integers(20, picture.height - 20))
        r = int(rng.integers(cell // 3, cell * 3 // 4))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(88, 86, 90) if rng.random() < 0.5 else (30, 80, 40))
    return np.asarray(picture)


# --------------------------------------------------------------------------------------------- the job, through each library
def lab_cie76(rgb_float):
    """CIE L*a*b* (D65) of sRGB values, vectorised the way the framework's palette module computes it for one colour."""
    c = rgb_float / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


PALETTE_LAB = lab_cie76(np.array(PALETTE, np.float64))


def nearest(medians_lab):
    distance = ((medians_lab[:, :, None, :] - PALETTE_LAB[None, None, :, :]) ** 2).sum(-1)
    return distance.argmin(axis=2).astype(np.uint8)


def cell_blocks(image, cell):
    h, w, _ = image.shape
    return image.reshape(h // cell, cell, w // cell, cell, 3).transpose(0, 2, 1, 3, 4).reshape(h // cell, w // cell, cell * cell, 3)


def backend_pillow(image, cell):
    return np.array(terrain.read_labels(Image.fromarray(image), TERRAINS, (cell, cell))["labels"], np.uint8)


def backend_numpy(image, cell):
    median = np.median(cell_blocks(image, cell), axis=2)
    return nearest(lab_cie76(median))


def backend_opencv(image, cell):
    import cv2
    median = np.median(cell_blocks(image, cell), axis=2).astype(np.float32)
    lab = cv2.cvtColor((median / 255.0).reshape(1, -1, 3), cv2.COLOR_RGB2LAB).reshape(median.shape)  # OpenCV's own colour conversion
    return nearest(lab)


def backend_opencv_area_mean(image, cell):
    """The cheapest OpenCV route: resize by area (a mean, not a median) and convert, with no per-cell median at all."""
    import cv2
    small = cv2.resize(image, (image.shape[1] // cell, image.shape[0] // cell), interpolation=cv2.INTER_AREA).astype(np.float32)
    return nearest(cv2.cvtColor(small / 255.0, cv2.COLOR_RGB2LAB))


def backend_skimage(image, cell):
    from skimage import color, measure
    median = measure.block_reduce(image, (cell, cell, 1), np.median)
    return nearest(color.rgb2lab(median / 255.0))


READERS = {"pillow (the framework's reader)": backend_pillow, "numpy": backend_numpy, "opencv": backend_opencv, "opencv area-mean": backend_opencv_area_mean,
           "scikit-image": backend_skimage}
NEEDS = {"numpy": "numpy", "opencv": "cv2", "opencv area-mean": "cv2", "scikit-image": "skimage"}


def open_pillow(labels, minimum):
    return np.array(terrain.area_open([list(map(int, row)) for row in labels], minimum)[0], np.uint8)


def open_scipy(labels, minimum):
    from scipy import ndimage
    out = labels.copy()
    for label in range(len(NAMES)):
        parts, count = ndimage.label(out == label)
        sizes = ndimage.sum(np.ones_like(parts), parts, index=range(1, count + 1))
        for part, size in enumerate(sizes, 1):
            if size < minimum:
                region = parts == part
                ring = ndimage.binary_dilation(region) & ~region
                around = out[ring]
                if around.size:
                    out[region] = np.bincount(around, minlength=len(NAMES)).argmax()
    return out


def open_skimage(labels, minimum):
    from skimage import morphology
    out = labels.copy()
    for label in range(len(NAMES)):
        mask = morphology.remove_small_objects(out == label, max_size=minimum - 1, connectivity=1) if minimum > 1 else out == label
        removed = (out == label) & ~mask
        if removed.any():
            from scipy import ndimage
            ring = ndimage.binary_dilation(removed) & ~removed
            around = out[ring]
            if around.size:
                out[removed] = np.bincount(around, minlength=len(NAMES)).argmax()
    return out


def open_opencv(labels, minimum):
    import cv2
    out = labels.copy()
    for label in range(len(NAMES)):
        count, parts, stats, _ = cv2.connectedComponentsWithStats((out == label).astype(np.uint8), connectivity=4)
        for part in range(1, count):
            if stats[part, cv2.CC_STAT_AREA] < minimum:
                region = parts == part
                ring = cv2.dilate(region.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                around = out[ring & ~region]
                if around.size:
                    out[region] = np.bincount(around, minlength=len(NAMES)).argmax()
    return out


OPENERS = {"pillow (the framework's code)": open_pillow, "scipy.ndimage": open_scipy, "scikit-image": open_skimage, "opencv": open_opencv}
OPENER_NEEDS = {"scipy.ndimage": "scipy", "scikit-image": "skimage", "opencv": "cv2"}


def best_of(function, *args, repeat=3):
    best = 1e9
    for _ in range(repeat):
        start = time.perf_counter()
        result = function(*args)
        best = min(best, time.perf_counter() - start)
    return result, best


def bridson(rng, width, height, radius, k=30):
    cell = radius / np.sqrt(2)
    cols, rows = int(width / cell) + 1, int(height / cell) + 1
    grid = -np.ones((rows, cols), int)
    points, active = [(rng.uniform(0, width), rng.uniform(0, height))], [0]
    grid[int(points[0][1] / cell), int(points[0][0] / cell)] = 0
    while active:
        pick = rng.integers(len(active))
        px, py = points[active[pick]]
        for _ in range(k):
            angle, dist = rng.uniform(0, 2 * np.pi), rng.uniform(radius, 2 * radius)
            nx, ny = px + dist * np.cos(angle), py + dist * np.sin(angle)
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            gx, gy = int(nx / cell), int(ny / cell)
            if all(grid[yy, xx] < 0 or (points[grid[yy, xx]][0] - nx) ** 2 + (points[grid[yy, xx]][1] - ny) ** 2 >= radius ** 2
                   for yy in range(max(0, gy - 2), min(rows, gy + 3)) for xx in range(max(0, gx - 2), min(cols, gx + 3))):
                points.append((nx, ny))
                active.append(len(points) - 1)
                grid[gy, gx] = len(points) - 1
                break
        else:
            active.pop(pick)
    return points


def minimum_gap(points):
    pts = np.array(points)
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(d, 1e9)
    return float(d.min())


def main():
    report = {"versions": VERSIONS, "python": sys.version.split()[0]}
    scenes = []
    for seed in range(5):
        rng = np.random.default_rng(seed)
        truth = truth_labels(rng)
        scenes.append((truth, render(truth, rng, CELL)))
    big = []
    for truth, image in scenes[:2]:
        big.append((truth, np.kron(truth, np.ones((64, 64), np.uint8))))
    big_images = []
    for truth, _ in big:
        rng = np.random.default_rng(99)
        image = np.zeros(truth.shape + (1,), np.uint8)
        painted = np.zeros((truth.shape[0] * 64, truth.shape[1] * 64, 3), np.float32)
        base = np.kron(truth, np.ones((64, 64), np.uint8))
        for index, name in enumerate(NAMES):
            painted[base == index] = COLOURS[name]
        painted += rng.standard_normal(painted.shape).astype(np.float32) * 9
        big_images.append((truth, np.clip(painted, 0, 255).astype(np.uint8)))

    reference = {}
    readers = {}
    for name, function in READERS.items():
        need = NEEDS.get(name)
        if need and not VERSIONS.get(need):
            readers[name] = "not installed"
            continue
        accuracy, agreement, seconds = [], [], []
        for index, (truth, image) in enumerate(scenes):
            labels, took = best_of(function, image, CELL, repeat=2)
            accuracy.append(float((labels == truth).mean()))
            seconds.append(took)
            if name.startswith("pillow"):
                reference[index] = labels
            else:
                agreement.append(float((labels == reference[index]).mean()))
        large_seconds = []
        for truth, image in big_images:
            _, took = best_of(function, image, 64, repeat=1)
            large_seconds.append(took)
        readers[name] = {"accuracy": round(float(np.mean(accuracy)), 4), "same_labels_as_pillow": None if not agreement else round(float(np.mean(agreement)), 4),
                         "seconds_1024x768": round(float(np.mean(seconds)), 4), "seconds_4096x3072": round(float(np.mean(large_seconds)), 3)}
    report["cell_reader"] = readers

    openers = {}
    noisy = []
    for truth, image in scenes:
        raw = backend_numpy(image, CELL)
        noisy.append((truth, raw))
    for name, function in OPENERS.items():
        need = OPENER_NEEDS.get(name)
        if need and not VERSIONS.get(need):
            openers[name] = "not installed"
            continue
        same, accuracy, seconds = [], [], []
        for index, (truth, raw) in enumerate(noisy):
            out, took = best_of(function, raw, 3, repeat=3)
            accuracy.append(float((out == truth).mean()))
            seconds.append(took)
            same.append(float((out == open_pillow(raw, 3)).mean()))
        openers[name] = {"accuracy": round(float(np.mean(accuracy)), 4), "same_result_as_pillow": round(float(np.mean(same)), 4), "seconds_64x48": round(float(np.mean(seconds)), 5)}
    report["area_opening"] = openers

    placement = {}
    start = time.perf_counter()
    points = bridson(np.random.default_rng(1), 400, 300, 24)
    placement["pure python Bridson"] = {"points": len(points), "minimum_gap": round(minimum_gap(points), 2), "seconds": round(time.perf_counter() - start, 4)}
    if VERSIONS["scipy"]:
        from scipy.stats import qmc
        start = time.perf_counter()
        engine = qmc.PoissonDisk(d=2, radius=24 / 400, rng=np.random.default_rng(1), ncandidates=30)
        pts = engine.fill_space() * np.array([400, 300 / 300 * 400])
        pts = pts[pts[:, 1] < 300]
        placement["scipy.stats.qmc.PoissonDisk"] = {"points": len(pts), "minimum_gap": round(minimum_gap(pts), 2), "seconds": round(time.perf_counter() - start, 4)}
    report["poisson_disk"] = placement
    json.dump(report, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
