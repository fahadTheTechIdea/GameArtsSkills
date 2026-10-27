#!/usr/bin/env python3
"""Build real framework output and load it in headless Godot (plan A14.5). Evidence, not shipped.

  python plans/enhancements/evidence/godot_integration/run.py [--godot PATH] [--keep]

Builds, with the framework's own tools in a scratch folder: a corner tileset and a blob tileset, a sheet with tags and per-frame times, an interface kit
with nine-slice margins and button states, and animation tracks with easing and stepped keys; derives the engine-ready (transparent) copies; then runs
`verify_integration.gd` in the installed Godot console build, which loads those files and reports what the engine made of them. Every observation is compared
here with what the framework computed, and the result is written to output.json next to this file. Exit status 1 when any check fails.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

from PIL import Image  # noqa: E402

import build_component_bundle as components  # noqa: E402
import build_sheet_atlas as sheets  # noqa: E402
import build_tileset as tilesets  # noqa: E402
import export_runtime as runtime  # noqa: E402
import gamearts_atlas as atlas_rules  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_tileset as tile_rules  # noqa: E402
from test_tileset import ART, TERRAINS  # noqa: E402  (the same tile pictures the tileset tests draw from each tile's labels)

GODOT = r"H:\dev\Godot\Godot_v4.7.2-stable_mono_win64_console.exe"
KEY = (255, 0, 255, 255)
TIMES = [0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1]


def block(size, box, colour, edge=None):
    image = Image.new("RGBA", size, KEY)
    x, y, w, h = box
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            on_edge = edge and (xx in (x, x + w - 1) or yy in (y, y + h - 1))
            image.putpixel((xx, yy), edge if on_edge else colour)
    return image


def key_pixels(sheet_path):
    with Image.open(sheet_path) as opened:
        rgba = opened.convert("RGBA")
    return rgba.width * rgba.height - common.mask_count(common.nonkey_mask(rgba))


def export(built, proj, name):
    destination = proj / "data" / name
    runtime.export_bundle(built, destination)
    return destination


def tileset_fixture(work, proj, layout, name, columns):
    src = work / f"src_{name}"
    src.mkdir()
    tiles = []
    for index, tile in enumerate(tile_rules.layout_tiles(layout, TERRAINS)):
        ART[layout](tile["neighbours"]).save(src / f"t{index:03d}.png")
        tiles.append({"file": f"t{index:03d}.png", "neighbours": tile["neighbours"]})
    built = work / "built" / name
    tilesets.build({"_input_dir": str(src), "name": name, "tile_size": [8, 8], "layout": layout, "terrains": TERRAINS, "tiles": tiles, "columns": columns}, built)
    destination = export(built, proj, name)
    blob = layout == "blob_47"
    spec = {"tileset": f"res://data/{name}/{name}.tileset.json", "atlas": f"res://data/{name}/{name}.atlas.json", "png": f"res://data/{name}/{name}.png",
            "map_size": 7 if blob else 6, "block_from": 2 if blob else 1, "block_to": 4 if blob else 3, "outside_is_empty": blob}
    return spec, {"png": spec["png"], "key_pixels": key_pixels(built / f"{name}.png"), "source_size": list(Image.open(built / f"{name}.png").size)}, destination


def hero_fixture(work, proj):
    src = work / "src_hero"
    src.mkdir()
    durations = [80, 80, 120, 80, 160, 80, 80, 240]
    colours = [(30 + 25 * i, 200 - 20 * i, 90 + 10 * i, 255) for i in range(8)]
    items = []
    for index in range(8):
        block((24, 24), (7, 7, 10, 10), colours[index]).save(src / f"f{index}.png")
        items.append({"file": f"f{index}.png", "name": f"hero_{index}", "duration_ms": durations[index], "pivot": [12, 23]})
    tags = [{"name": "walk", "from": 0, "to": 3, "direction": "forward"}, {"name": "hit", "from": 4, "to": 5, "direction": "reverse", "repeat": 1},
            {"name": "blink", "from": 6, "to": 7, "direction": "pingpong"}]
    built = work / "built" / "hero"
    _, atlas_path = sheets.build({"_input_dir": str(src), "name": "hero", "asset_id": "hero", "columns": 4, "padding": 2, "frames": items, "tags": tags}, built)
    export(built, proj, "hero")
    atlas = common.read_json(atlas_path)
    base = 40
    frames = [{"rect": list(atlas_rules.image_rect(f)), "duration_ms": f["duration_ms"], "colour": list(colours[f["index"]])} for f in atlas["frames"]]
    spec = {"png": "res://data/hero/hero.png", "tags": tags, "frames": frames, "base_ms": base, "fps": 1000.0 / base}
    expected = {}
    for tag in tags:
        order = list(range(tag["from"], tag["to"] + 1))
        if tag["direction"] == "reverse":
            order.reverse()
        expected[tag["name"]] = {"frames": len(order), "loop": tag.get("repeat", 0) == 0, "speed": 1000.0 / base, "frame_indexes": order,
                                 "durations": [durations[i] / base for i in order], "centre_colours": [list(colours[i]) for i in order], "region_sizes": frames[order[0]]["rect"][2:]}
    return spec, {"png": spec["png"], "key_pixels": key_pixels(built / "hero.png"), "source_size": list(atlas["image_size"])}, expected


def ui_fixture(work, proj):
    src = work / "src_ui"
    src.mkdir()
    states = ["normal", "hover", "pressed", "disabled"]
    items = []
    for index, state in enumerate(states):
        block((24, 16), (0, 0, 24, 16), (60 + 40 * index, 90, 160, 255), edge=(10, 10, 40, 255)).save(src / f"b{index}.png")
        items.append({"file": f"b{index}.png", "name": f"button_{state}", "control": "button", "state": state, "nine_slice": [6, 5, 6, 5], "pivot": [0, 0]})
    block((32, 32), (0, 0, 32, 32), (200, 190, 150, 255), edge=(60, 40, 20, 255)).save(src / "panel.png")
    items.append({"file": "panel.png", "name": "panel", "nine_slice": [8, 7, 8, 7], "pivot": [0, 0]})
    built = work / "built" / "ui"
    _, atlas_path = sheets.build({"_input_dir": str(src), "name": "ui", "asset_id": "ui", "columns": 3, "padding": 2, "frames": items,
                                  "controls": [{"name": "button", "states": states}]}, built)
    export(built, proj, "ui")
    atlas = common.read_json(atlas_path)
    by_name = {f["name"]: f for f in atlas["frames"]}
    spec = {"png": "res://data/ui/ui.png",
            "panels": [{"name": "panel", "rect": list(atlas_rules.image_rect(by_name["panel"])), "nine_slice": by_name["panel"]["nine_slice"]}],
            "states": [{"state": s, "rect": list(atlas_rules.image_rect(by_name[f"button_{s}"])), "nine_slice": by_name[f"button_{s}"]["nine_slice"]} for s in states]}
    return spec, {"png": spec["png"], "key_pixels": key_pixels(built / "ui.png"), "source_size": list(atlas["image_size"])}, by_name


def curve_fixture():
    base = [(0, 0), (0.5, 10), (1, 0)]
    variants = {"linear": ("linear", "linear"), "ease_in": ("linear", "ease_in"), "ease_out": ("linear", "ease_out"), "ease_in_out": ("linear", "ease_in_out"),
                "nearest": ("nearest", "linear"), "cubic": ("cubic", "linear")}
    curves, expected = [], {}
    for name, (interpolation, easing) in variants.items():
        track = []
        for index, (time, value) in enumerate(base):
            key = {"time": time, "position": [value, 0]}
            if index < len(base) - 1:
                key.update(interpolation=interpolation, easing=easing)
            track.append(key)
        curves.append({"name": name, "interpolation": interpolation,
                       "keys": [{"time": k["time"], "value": k["position"][0], **({"easing": easing} if k.get("easing") else {})} for k in track]})
        expected[name] = [round(components.animate(track, t, name)["position"][0], 4) for t in TIMES]
    return {"curves": curves, "times": TIMES}, expected


def expected_labels(layout, cell, block_cells):
    """The terrain the painted block implies around one block cell, from the geometry alone (independent of the engine and of the framework's tile data)."""
    x, y = cell
    inside = lambda cx, cy: (cx, cy) in block_cells
    grass, other = TERRAINS[0], TERRAINS[1]
    if layout == "wang_corner_16":
        around = {"top_left": [(x - 1, y - 1), (x, y - 1), (x - 1, y), (x, y)], "top_right": [(x, y - 1), (x + 1, y - 1), (x, y), (x + 1, y)],
                  "bottom_right": [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)], "bottom_left": [(x - 1, y), (x, y), (x - 1, y + 1), (x, y + 1)]}
        return {place: (grass if all(inside(*c) for c in cells) else other) for place, cells in around.items()}
    offsets = {"top": (0, -1), "top_right": (1, -1), "right": (1, 0), "bottom_right": (1, 1), "bottom": (0, 1), "bottom_left": (-1, 1), "left": (-1, 0), "top_left": (-1, -1)}
    return {place: (grass if inside(x + dx, y + dy) else other) for place, (dx, dy) in offsets.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--godot", default=GODOT)
    parser.add_argument("--keep", action="store_true", help="Keep the scratch project and print where it is")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="gamearts-godot-integration-"))
    try:
        proj = work / "proj"
        (proj / "data").mkdir(parents=True)
        shutil.copyfile(HERE.parent / "godot_profile_verification" / "project.godot", proj / "project.godot")
        shutil.copyfile(HERE / "verify_integration.gd", proj / "verify_integration.gd")
        spec = {"pngs": {}, "tilesets": {}}
        facts = {}
        for layout, name, columns in (("wang_corner_16", "ground_corner", 4), ("blob_47", "ground_blob", 8)):
            tile_spec, png_fact, _ = tileset_fixture(work, proj, layout, name, columns)
            spec["tilesets"][name] = tile_spec
            spec["pngs"][name] = {"png": tile_spec["png"]}
            facts[name] = png_fact
        hero_spec, hero_fact, hero_expected = hero_fixture(work, proj)
        spec["tags"], spec["pngs"]["hero"], facts["hero"] = hero_spec, {"png": hero_spec["png"]}, hero_fact
        ui_spec, ui_fact, ui_frames = ui_fixture(work, proj)
        spec["ui"], spec["pngs"]["ui"], facts["ui"] = ui_spec, {"png": ui_spec["png"]}, ui_fact
        spec["curves"], curve_expected = curve_fixture()
        (proj / "expected.json").write_text(json.dumps(spec), encoding="utf-8")
        command = [args.godot, "--headless", "--path", str(proj), "--script", "res://verify_integration.gd"]
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        line = next((l for l in run.stdout.splitlines() if l.startswith("VERIFY_JSON ")), None)
        if run.returncode != 0 or line is None:
            print("The engine run failed.\n", run.stdout[-2000:], run.stderr[-2000:], file=sys.stderr)
            return 1
        observed = json.loads(line[len("VERIFY_JSON "):])
        checks = []

        def check(name, ok, detail=""):
            checks.append({"name": name, "ok": bool(ok), "detail": detail})

        for name, fact in facts.items():
            seen = observed["runtime_png"][name]
            check(f"{name}: the engine-ready PNG loads as RGBA at the delivered size", seen["has_alpha_format"] and seen["size"] == fact["source_size"], str(seen["size"]))
            check(f"{name}: every key-colour pixel is fully transparent and every other pixel is opaque",
                  seen["transparent"] == fact["key_pixels"] and seen["partial"] == 0 and seen["opaque"] == seen["size"][0] * seen["size"][1] - fact["key_pixels"],
                  f"transparent {seen['transparent']} of {fact['key_pixels']} key pixels, partial {seen['partial']}")
        for tag, want in hero_expected.items():
            got = observed["tags"][tag]
            for key in ("frames", "loop", "frame_indexes", "region_sizes"):
                check(f"tag {tag}: {key} as the atlas says", got[key] == want[key], f"{got[key]} vs {want[key]}")
            check(f"tag {tag}: frame durations are the atlas times relative to the base time", got["durations"] == want["durations"], f"{got['durations']} vs {want['durations']}")
            check(f"tag {tag}: each frame region shows that frame's colour in the engine-ready sheet", got["centre_colours"] == want["centre_colours"], str(got["centre_colours"]))
        check("a pingpong tag has no engine setting, so the game plays it forward then back itself", hero_spec["tags"][2]["direction"] == "pingpong", "reported, not a pass of a native feature")
        panel = ui_frames["panel"]
        got_patch = observed["ui"]["patches"]["panel"]
        check("ui: NinePatchRect margins are the frame's nine_slice", got_patch["margins"] == panel["nine_slice"], str(got_patch["margins"]))
        check("ui: the nine-patch texture is the whole frame, untrimmed", got_patch["texture_size"] == panel["source_size"], str(got_patch["texture_size"]))
        for state in ("normal", "hover", "pressed", "disabled"):
            got_state = observed["ui"]["states"][state]
            frame = ui_frames[f"button_{state}"]
            check(f"ui: Button style box '{state}' takes the state's frame and margins", got_state["is_ours"] and got_state["margins"] == frame["nine_slice"]
                  and got_state["texture_size"] == frame["source_size"], str(got_state))
        for name, want in curve_expected.items():
            got = observed["curves"][name]
            close = all(abs(a - b) <= 0.001 for a, b in zip(got, want))
            if name == "cubic":
                check("curves: the engine's cubic is NOT the framework's (the profile marks it needs_custom)", not close, f"engine {got} framework {want}")
            else:
                check(f"curves: {name} matches the framework's sampled values", close, f"engine {got} framework {want}")
        for name, tile_spec in spec["tilesets"].items():
            meta = common.read_json(proj / "data" / name / f"{name}.tileset.json")
            got = observed["tilesets"][name]
            layout = meta["layout"]
            check(f"{name}: every neutral label is accepted as a peering bit and reads back", got["peering_bits_read_back_equal"] == got["peering_bits_read_back_total"] == got["peering_bits_set"],
                  f"{got['peering_bits_read_back_equal']} of {got['peering_bits_read_back_total']}")
            check(f"{name}: the tileset and the atlas agree on the number of tiles", got["atlas_frames"] == got["tile_count"] == len(tile_rules.layout_tiles(layout, TERRAINS)), str(got["tile_count"]))
            block_cells = {(x, y) for x in range(tile_spec["block_from"], tile_spec["block_to"] + 1) for y in range(tile_spec["block_from"], tile_spec["block_to"] + 1)}
            tiles = {t["id"]: t for t in meta["tiles"]}
            wrong = []
            for cell in sorted(block_cells):
                picked = got["picked_tile_ids"][cell[1]][cell[0]]
                want = expected_labels(layout, cell, block_cells)
                if picked < 0:
                    wrong.append((cell, "no tile"))
                elif tile_rules.identity(layout, tiles[picked]["neighbours"], TERRAINS) != tile_rules.identity(layout, want, TERRAINS):
                    wrong.append((cell, picked))
            check(f"{name}: painting a 3 x 3 block of grass makes the engine choose, for every cell, the tile whose labels describe its surroundings", not wrong, f"wrong cells: {wrong}")
        result = {"godot": observed["godot"], "command": " ".join(command[:1] + ["--headless", "--path", "<scratch project>", "--script", "res://verify_integration.gd"]),
                  "exit_status": run.returncode, "observed": observed, "framework": {"curves": curve_expected, "tags": hero_expected}, "checks": checks,
                  "failed": [c["name"] for c in checks if not c["ok"]]}
        (HERE / "output.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{len(checks)} checks, {len(result['failed'])} failed (Godot {observed['godot']})")
        for name in result["failed"]:
            print("FAILED:", name)
        if args.keep:
            print("scratch project kept at", proj)
        return 1 if result["failed"] else 0
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
