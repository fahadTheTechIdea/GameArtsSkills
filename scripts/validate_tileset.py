#!/usr/bin/env python3
"""Check a tileset: complete and consistent labels, a regular grid of tile-sized cells, the sheet's pixel contract, and that tiles which claim the same
side line up.

  python scripts/validate_tileset.py NAME.tileset.json [--tolerance 16]

Reports every problem it finds, each in words that name the tiles: a missing tile is described by the terrain at each place it needs, a tile of the
wrong size or off the grid is named, and two tiles that claim the same side (for example both have water at the top-right corner and grass at the
bottom-right) but whose pixels along it differ are named with the measured difference. The seam test compares the outermost pixel row or column of one
tile with that of the tile it would sit next to, and allows the difference the tile's own texture already has between its outermost and next row plus
`--tolerance` (a mean difference over the colour channels, 0 to 255, default 16). It proves the tiles can be placed without a visible break, not that
they look good. Exit status 1 when anything is reported.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamearts_common as common  # noqa: E402
import gamearts_tileset as rules  # noqa: E402
import validate_sheet_atlas as sheet_validator  # noqa: E402

SEAM_TOLERANCE = 16.0


def _difference(first, second):
    """Mean absolute difference between two same-size pictures over the colour channels, 0 (identical) to 255."""
    from PIL import ImageChops, ImageStat
    stat = ImageStat.Stat(ImageChops.difference(first.convert("RGB"), second.convert("RGB")))
    return sum(stat.mean) / len(stat.mean)


def _strips(cell):
    """For each side: the outermost row or column of the tile and the one just inside it."""
    width, height = cell.size
    outer = {"left": cell.crop((0, 0, 1, height)), "right": cell.crop((width - 1, 0, width, height)),
             "top": cell.crop((0, 0, width, 1)), "bottom": cell.crop((0, height - 1, width, height))}
    inner = {"left": cell.crop((min(1, width - 1), 0, min(1, width - 1) + 1, height)),
             "right": cell.crop((max(width - 2, 0), 0, max(width - 2, 0) + 1, height)),
             "top": cell.crop((0, min(1, height - 1), width, min(1, height - 1) + 1)),
             "bottom": cell.crop((0, max(height - 2, 0), width, max(height - 2, 0) + 1))}
    return outer, inner


def seam_issues(tileset, cells, tolerance):
    """Every pair of tiles that claim the same side but whose pixels along it differ by more than the texture's own variation plus `tolerance`."""
    layout = tileset["layout"]
    tiles = {tile["id"]: tile for tile in tileset["tiles"]}
    strips = {tile_id: _strips(cells[tile_id]) for tile_id in tiles}
    issues = []
    for side in ("right", "bottom"):
        opposite = rules.OPPOSITE[side]
        by_signature = {}
        for tile_id, tile in tiles.items():
            by_signature.setdefault(rules.edge_signature(layout, tile["neighbours"], opposite), []).append(tile_id)
        for first_id, first in tiles.items():
            signature = rules.edge_signature(layout, first["neighbours"], side)
            for second_id in by_signature.get(signature, []):
                seam = _difference(strips[first_id][0][side], strips[second_id][0][opposite])
                own = max(_difference(strips[first_id][0][side], strips[first_id][1][side]),
                          _difference(strips[second_id][0][opposite], strips[second_id][1][opposite]))
                if seam > own + tolerance:
                    issues.append(f"tile {first_id} and tile {second_id} do not line up: the {side} side of tile {first_id} and the {opposite} side of tile {second_id} "
                                  f"both have {'/'.join(str(label) for label in signature)} but differ by {seam:.1f} (their own texture allows {own:.1f} plus {tolerance:g})")
    return issues


def validate(tileset_path, tolerance=SEAM_TOLERANCE, check_sheet=True):
    """Return a list of problems with one tileset and its sheet (empty means it holds). The technical artwork gate already checks every
    atlas, so it passes check_sheet=False to avoid reporting the same sheet problem twice."""
    from PIL import Image
    path = Path(tileset_path)
    try:
        tileset = common.read_json(path)
        common.validate_schema(tileset, "gamearts-tileset")
    except ValueError as exc:  # unreadable JSON, schema violation or a missing validator all block the check
        return [f"tileset contract: {exc}"]
    issues = [f"layout: {problem}" for problem in rules.label_problems(tileset)]
    atlas_path = path.with_name(Path(tileset["atlas"]).name)
    if not atlas_path.is_file():
        return issues + [f"the atlas {tileset['atlas']} is missing from the tileset's folder"]
    try:
        atlas = common.read_json(atlas_path)
        common.validate_schema(atlas, "gamearts-atlas")
    except ValueError as exc:
        return issues + [f"atlas contract: {exc}"]
    image_path = path.with_name(Path(atlas["image"]).name)
    if check_sheet:
        issues += [f"sheet: {problem}" for problem in sheet_validator.validate(image_path, atlas_path)]
    tile_w, tile_h = tileset["tile_size"]
    frames, tiles = atlas["frames"], tileset["tiles"]
    if len(frames) != len(tiles):
        issues.append(f"the atlas has {len(frames)} frames but the tileset lists {len(tiles)} tiles")
        return issues
    columns = tileset.get("columns") or atlas.get("columns") or len(frames)
    geometry = []
    for tile, frame in zip(tiles, frames):
        x, y, w, h = frame["rect"]
        if (w, h) != (tile_w, tile_h):
            geometry.append(f"tile {tile['id']}: its cell in the sheet is {w}x{h}, but the tile size is {tile_w}x{tile_h}")
        elif [x, y] != [(tile["id"] % columns) * tile_w, (tile["id"] // columns) * tile_h]:
            geometry.append(f"tile {tile['id']}: its cell {frame['rect']} is not where a regular grid of {columns} columns of {tile_w}x{tile_h} tiles puts it")
    if bool(atlas.get("full_bleed")) != bool(tileset.get("full_bleed", True)):
        geometry.append("the tileset and its atlas disagree about full_bleed (ground tiles fill their square with no key colour)")
    issues += geometry
    if geometry or not image_path.is_file():
        return issues
    with Image.open(image_path) as opened:
        sheet = opened.convert("RGBA")
    cells = {tile["id"]: sheet.crop((x, y, x + w, y + h)) for tile, (x, y, w, h) in ((t, f["rect"]) for t, f in zip(tiles, frames))}
    if tileset.get("full_bleed", True):
        for tile_id, cell in cells.items():
            keyed = cell.width * cell.height - common.mask_count(common.nonkey_mask(cell))
            if keyed:
                issues.append(f"tile {tile_id}: {keyed} pixel(s) are the key colour {common.KEY_HEX}, which a full-bleed tile must not contain "
                              "(they would become transparent where the key colour is removed)")
    if not [i for i in issues if i.startswith("layout:")]:  # lining up is judged on a layout that makes sense
        issues += seam_issues(tileset, cells, tolerance)
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tileset", type=Path)
    parser.add_argument("--tolerance", type=float, default=SEAM_TOLERANCE, help="extra mean difference allowed along a shared side (default %g)" % SEAM_TOLERANCE)
    args = parser.parse_args(argv)
    try:
        issues = validate(args.tileset, args.tolerance)
    except (OSError, ValueError) as exc:
        print("FAIL", exc)
        return 1
    if issues:
        for issue in issues:
            print("FAIL", issue)
        return 1
    print("PASS labels, grid, sheet contract and shared sides. Whether the tiles look good is NOT assessed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
