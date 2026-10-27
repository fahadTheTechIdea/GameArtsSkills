#!/usr/bin/env python3
"""Single owner of pixel-grid detection: where a picture's colour changes, whether those changes sit on a regular grid, and its period.

Used by the pixel-grid style check (is a picture built from whole blocks?) and by the snapper (recover the native picture from one that
was drawn large). An 'edge' is a column or row across which the colour changes in a large part of the picture; position p means the
change between pixel p-1 and pixel p. Nothing here changes a picture.
"""
import math

CHANGE_TOLERANCE = 12  # a per-channel difference above this counts as a colour change; fainter noise does not
MIN_PERIOD = 2.0
MAX_PERIOD = 64.0
STRONG_SHARE = 0.1  # an edge is strong when it is at least this share of the strongest one
MIN_STRONG_EDGES = 8  # fewer strong edges than this cannot show a grid
GRID_WINDOW = 0.75  # pixels: an edge lies on the grid when it is this close to a grid line (rounding to whole pixels takes up to half)
GOOD_SCORE = 0.9


def edge_profiles(image):
    """([strength per vertical boundary], [strength per horizontal boundary]): for each boundary, how much of the picture changes colour
    across it, 0 to 255. Index i is the boundary at position i + 1."""
    from PIL import Image, ImageChops
    rgb = image.convert("RGB")
    width, height = rgb.size
    profiles = []
    for axis in (0, 1):
        if axis == 0:
            a, b, shape = rgb.crop((1, 0, width, height)), rgb.crop((0, 0, width - 1, height)), (max(width - 1, 1), 1)
        else:
            a, b, shape = rgb.crop((0, 1, width, height)), rgb.crop((0, 0, width, height - 1)), (1, max(height - 1, 1))
        r, g, blue = ImageChops.difference(a, b).split()
        changed = ImageChops.lighter(ImageChops.lighter(r, g), blue).point(lambda v: 255 if v > CHANGE_TOLERANCE else 0)
        profiles.append(list(changed.resize(shape, Image.BOX).tobytes()) if min(rgb.size) > 1 else [])
    return profiles[0], profiles[1]


def strong_positions(profile, share):
    """Boundary positions whose strength is at least `share` of the strongest one."""
    peak = max(profile, default=0)
    return [i + 1 for i, v in enumerate(profile) if peak and v >= peak * share]


def block_size(positions, min_aligned, min_edges, largest=32):
    """The largest block size that at least `min_aligned` of the edge positions are multiples of; 1 when there is none; None when there
    are fewer than `min_edges` edges, too few to tell."""
    if len(positions) < min_edges:
        return None
    best = 1
    for k in range(2, largest + 1):
        if sum(1 for p in positions if p % k == 0) / len(positions) >= min_aligned:
            best = k
    return best


def _fit(positions, period, phase):
    """Least-squares refinement of (period, phase) so that each edge position is phase + n * period for a whole number n.

    Handles a fractional period (a picture enlarged by a non-whole number, where cells are 7 or 8 pixels wide) and edges that are missing
    because neighbouring cells share a colour. Each edge's cell number is built up gap by gap (a gap of about two periods is two cells),
    never from its distance to the first edge, so a small error in the period cannot grow into a whole-cell mistake along a long picture."""
    for _ in range(4):
        cells = [0]
        for earlier, later in zip(positions, positions[1:]):
            cells.append(cells[-1] + max(1, round((later - earlier) / period)))
        mean_n, mean_e = sum(cells) / len(cells), sum(positions) / len(positions)
        spread = sum((n - mean_n) ** 2 for n in cells)
        if spread == 0:
            break
        slope = sum((n - mean_n) * (e - mean_e) for n, e in zip(cells, positions)) / spread
        if not 0.7 * period <= slope <= 1.3 * period:
            break  # a fit that wanders far from the spacing the edges suggest is not a better grid
        period, phase = slope, mean_e - slope * mean_n
    return period, phase % period


def _score(profile, total, period, phase):
    """How well the grid phase + n * period explains the edges, from 0 (no better than a random grid of that period) to 1 (every edge on it).

    A fine grid catches many edges by chance (a 2.5-pixel grid with a one-and-a-half-pixel window catches 60% of any edges), so the share
    of edge strength within the window of a grid line is measured above the share a random grid of the same period would catch."""
    window = min(GRID_WINDOW, 0.25 * period)
    hit = 0
    for i, strength in enumerate(profile):
        if strength:
            offset = (i + 1 - phase) % period
            if min(offset, period - offset) <= window:
                hit += strength
    chance = min(1.0, 2 * window / period)
    return max(0.0, (hit / total - chance) / (1 - chance))


def _circular_phase(positions, period):
    """The most common position of the edges within one period, found on the circle so 0 and period - 1 are neighbours."""
    angle = 2 * math.pi / period
    x = sum(math.cos(angle * e) for e in positions)
    y = sum(math.sin(angle * e) for e in positions)
    return (math.atan2(y, x) / angle) % period


def detect_period(profile):
    """(period, phase, score) of the regular grid the edges lie on, or None when there is none. The score is 0 to 1 above chance (see _score).

    The spacing between neighbouring strong edges suggests a period; a least-squares fit refines it, fractions of it (a half, a third,
    a quarter) are tried, and the **largest** period that scores at least 0.9 wins: a multiple of the true period leaves some edges off
    its lines, a fraction of it catches them all but only because it has more lines than edges need. When none reaches 0.9 the best is
    returned for the caller to judge."""
    total = sum(profile)
    positions = strong_positions(profile, STRONG_SHARE)
    if total == 0 or len(positions) < MIN_STRONG_EDGES:
        return None
    gaps = [b - a for a, b in zip(positions, positions[1:])]
    counts = {}
    for gap in gaps:
        counts[gap] = counts.get(gap, 0) + 1
    common = max(sorted(counts), key=lambda gap: counts[gap])
    near = [gap for gap in gaps if abs(gap - common) <= 1]
    estimate = sum(near) / len(near)
    best = None
    for divisor in (1, 2, 3, 4):
        period = estimate / divisor
        if period < MIN_PERIOD or period > MAX_PERIOD:
            continue
        period, phase = _fit(positions, period, _circular_phase(positions, period))
        score = _score(profile, total, period, phase)
        if score >= GOOD_SCORE:
            return round(period, 3), round(phase, 3), round(score, 3)
        if best is None or score > best[2]:
            best = (round(period, 3), round(phase, 3), round(score, 3))
    return best
