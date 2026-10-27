"""Tilesets (plan P12.1): layouts, required tiles, a builder, and a validator that names what is missing, mismatched or the wrong size."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit as kit  # noqa: E402  (also puts scripts/ on sys.path)

import build_tileset as builder  # noqa: E402
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_tileset as rules  # noqa: E402
import validate_tileset as validator  # noqa: E402

GRASS, WATER = (60, 160, 70, 255), (50, 90, 200, 255)
COLOURS = {"grass": GRASS, "water": WATER}
TERRAINS = ["grass", "water"]
SIZE = 8


def paint(image, box, colour):
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        for x in range(x0, x1):
            image.putpixel((x, y), colour)


def corner_art(neighbours):
    """Four quadrants, each the colour of the terrain at that corner."""
    image = Image.new("RGBA", (SIZE, SIZE), GRASS)
    half = SIZE // 2
    boxes = {"top_left": (0, 0, half, half), "top_right": (half, 0, SIZE, half), "bottom_right": (half, half, SIZE, SIZE), "bottom_left": (0, half, half, SIZE)}
    for side, box in boxes.items():
        paint(image, box, COLOURS[neighbours[side]])
    return image


def edge_art(neighbours):
    """Grass everywhere except the middle of each edge, which has the colour of that edge's terrain."""
    image = Image.new("RGBA", (SIZE, SIZE), GRASS)
    paint(image, (2, 0, 6, 2), COLOURS[neighbours["top"]])
    paint(image, (6, 2, 8, 6), COLOURS[neighbours["right"]])
    paint(image, (2, 6, 6, 8), COLOURS[neighbours["bottom"]])
    paint(image, (0, 2, 2, 6), COLOURS[neighbours["left"]])
    return image


def blob_art(neighbours):
    """Grass, with a band of water along every side whose neighbour is water and a notch at every corner whose neighbour is water."""
    image = Image.new("RGBA", (SIZE, SIZE), GRASS)
    if neighbours["top"] == "water":
        paint(image, (0, 0, SIZE, 2), WATER)
    if neighbours["bottom"] == "water":
        paint(image, (0, SIZE - 2, SIZE, SIZE), WATER)
    if neighbours["left"] == "water":
        paint(image, (0, 0, 2, SIZE), WATER)
    if neighbours["right"] == "water":
        paint(image, (SIZE - 2, 0, SIZE, SIZE), WATER)
    for corner, box in (("top_left", (0, 0, 2, 2)), ("top_right", (SIZE - 2, 0, SIZE, 2)), ("bottom_left", (0, SIZE - 2, 2, SIZE)), ("bottom_right", (SIZE - 2, SIZE - 2, SIZE, SIZE))):
        if neighbours[corner] == "water":
            paint(image, box, WATER)
    return image


ART = {"wang_corner_16": corner_art, "dual_grid_16": corner_art, "wang_edge_16": edge_art, "blob_47": blob_art}


def flat_art(_neighbours=None, colour=GRASS):
    return Image.new("RGBA", (SIZE, SIZE), colour)


class RuleTests(unittest.TestCase):
    def test_each_layout_requires_the_documented_number_of_distinct_tiles(self):
        expected = {"single": 1, "variants": 1, "wang_corner_16": 16, "wang_edge_16": 16, "blob_47": 47, "dual_grid_16": 16}
        for layout, count in expected.items():
            with self.subTest(layout):
                terrains = TERRAINS[:rules.TERRAIN_COUNT[layout]]
                tiles = rules.layout_tiles(layout, terrains)
                self.assertEqual(len(tiles), count)
                self.assertEqual(len({t["identity"] for t in tiles}), count)

    def test_names_describe_a_tile_in_words_with_the_terrain_names(self):
        names = {rules.tile_name("wang_corner_16", t["neighbours"], TERRAINS) for t in rules.layout_tiles("wang_corner_16", TERRAINS)}
        self.assertEqual(len(names), 16)
        self.assertTrue(all("grass" in n or "water" in n for n in names))
        blob = {rules.tile_name("blob_47", t["neighbours"], TERRAINS) for t in rules.layout_tiles("blob_47", TERRAINS)}
        self.assertEqual(len(blob), 47)

    def test_only_the_places_a_layout_uses_carry_labels(self):
        for layout, used in (("wang_corner_16", rules.CORNERS), ("dual_grid_16", rules.CORNERS), ("wang_edge_16", rules.EDGES), ("blob_47", rules.SIDES)):
            for tile in rules.layout_tiles(layout, TERRAINS):
                self.assertEqual(set(tile["neighbours"]), set(used), layout)

    def test_a_blob_corner_counts_only_when_both_sides_next_to_it_are_inside(self):
        raw = {s: "water" for s in rules.SIDES}
        raw.update(top="grass", right="water", top_right="grass")  # corner grass, but the side to its right is water
        same = {**raw, "top_right": "water"}
        self.assertEqual(rules.identity("blob_47", raw, TERRAINS), rules.identity("blob_47", same, TERRAINS))
        counted = {s: "grass" for s in rules.SIDES}
        self.assertNotEqual(rules.identity("blob_47", counted, TERRAINS), rules.identity("blob_47", {**counted, "top_right": "water"}, TERRAINS))

    def test_wang_ids_follow_tileds_order_with_zero_for_unused_places(self):
        corner = {"top_left": "grass", "top_right": "water", "bottom_right": "grass", "bottom_left": "water"}
        self.assertEqual(rules.wang_id("wang_corner_16", corner, TERRAINS), [0, 2, 0, 1, 0, 2, 0, 1])
        edge = {"top": "water", "right": "grass", "bottom": "grass", "left": "water"}
        self.assertEqual(rules.wang_id("wang_edge_16", edge, TERRAINS), [2, 0, 1, 0, 1, 0, 2, 0])
        everything = {s: "water" for s in rules.SIDES}
        self.assertEqual(rules.wang_id("blob_47", everything, TERRAINS), [2] * 8)

    def test_edge_signatures_say_which_tiles_can_sit_side_by_side(self):
        a = {"top_left": "grass", "top_right": "water", "bottom_right": "grass", "bottom_left": "water"}
        b = {"top_left": "water", "top_right": "grass", "bottom_right": "grass", "bottom_left": "grass"}
        # a's right side reads (water, grass) from top to bottom; b's left side reads (water, grass) too
        self.assertEqual(rules.edge_signature("wang_corner_16", a, "right"), rules.edge_signature("wang_corner_16", b, "left"))
        self.assertNotEqual(rules.edge_signature("wang_corner_16", a, "left"), rules.edge_signature("wang_corner_16", b, "left"))


def tileset_of(layout, terrains=None, drop=(), extra=()):
    terrains = terrains or TERRAINS[:rules.TERRAIN_COUNT[layout]]
    tiles = [t for t in rules.layout_tiles(layout, terrains) if t["identity"] not in drop]
    entries = [{"id": i, "terrain": terrains[0], "neighbours": dict(t["neighbours"])} for i, t in enumerate(tiles)]
    for extra_tile in extra:
        entries.append({"id": len(entries), "terrain": terrains[0], "neighbours": dict(extra_tile)})
    return {"layout": layout, "terrains": terrains, "tiles": entries}


class LabelTests(unittest.TestCase):
    def test_a_complete_tileset_of_every_layout_has_no_problems(self):
        for layout in rules.LAYOUTS:
            with self.subTest(layout):
                self.assertEqual(rules.label_problems(tileset_of(layout)), [])

    def test_variants_may_be_many_but_must_all_be_the_inside_terrain(self):
        many = tileset_of("variants")
        many["tiles"] += [{"id": i, "terrain": "grass", "neighbours": {s: "grass" for s in rules.SIDES}} for i in (1, 2)]
        self.assertEqual(rules.label_problems(many), [])

    def test_a_single_layout_has_exactly_one_tile(self):
        two = tileset_of("single")
        two["tiles"].append({"id": 1, "terrain": "grass", "neighbours": {s: "grass" for s in rules.SIDES}})
        self.assertTrue(any("exactly one" in p for p in rules.label_problems(two)))

    def test_a_missing_tile_is_named_in_words(self):
        for layout in ("wang_corner_16", "wang_edge_16", "blob_47", "dual_grid_16"):
            with self.subTest(layout):
                tiles = rules.layout_tiles(layout, TERRAINS)
                gone = tiles[5]
                problems = rules.label_problems(tileset_of(layout, drop={gone["identity"]}))
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("missing tile: " + rules.tile_name(layout, gone["neighbours"], TERRAINS), problems[0])

    def test_a_repeated_tile_names_both(self):
        ts = tileset_of("wang_corner_16")
        ts["tiles"].append({"id": 16, "terrain": "grass", "neighbours": dict(ts["tiles"][3]["neighbours"])})
        self.assertTrue(any("tile 16" in p and "repeats tile 3" in p for p in rules.label_problems(ts)))

    def test_labels_outside_the_layout_or_the_terrains_are_refused(self):
        ts = tileset_of("wang_corner_16")
        ts["tiles"][0]["neighbours"]["top"] = "grass"
        self.assertTrue(any("top is not used by layout wang_corner_16" in p for p in rules.label_problems(ts)))
        ts = tileset_of("wang_corner_16")
        ts["tiles"][0]["neighbours"]["top_left"] = "lava"
        self.assertTrue(any("lava" in p and "not one of the terrains" in p for p in rules.label_problems(ts)))
        ts = tileset_of("wang_corner_16")
        ts["tiles"][0]["terrain"] = "water"
        self.assertTrue(any("terrain is 'water'" in p for p in rules.label_problems(ts)))

    def test_a_blob_tile_with_an_impossible_corner_is_explained(self):
        ts = tileset_of("blob_47")
        tile = ts["tiles"][-1]
        tile["neighbours"] = {s: "grass" for s in rules.SIDES}
        tile["neighbours"]["right"] = "water"  # side is water, yet the corner next to it is grass
        problems = rules.label_problems(ts)
        self.assertTrue(any("47 tiles" in p and "label the corner water" in p for p in problems), problems)

    def test_the_wrong_number_of_terrains_for_a_layout_is_named(self):
        ts = tileset_of("wang_corner_16")
        ts["terrains"] = ["grass"]
        self.assertTrue(any("needs 2 terrain(s)" in p for p in rules.label_problems(ts)))

    def test_ids_must_follow_the_frame_order(self):
        ts = tileset_of("wang_edge_16")
        ts["tiles"][0]["id"] = 9
        self.assertTrue(any("ids must be 0, 1, 2" in p for p in rules.label_problems(ts)))


class BuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.out = self.root / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def job(self, layout="wang_corner_16", drop=(), art=None, **overrides):
        terrains = TERRAINS[:rules.TERRAIN_COUNT[layout]]
        draw = art or ART.get(layout, flat_art)
        tiles = []
        for index, tile in enumerate(t for t in rules.layout_tiles(layout, terrains) if t["identity"] not in drop):
            name = f"t{index:03d}.png"
            draw(tile["neighbours"]).save(self.src / name)
            item = {"file": name}
            if layout not in ("single", "variants"):
                item["neighbours"] = tile["neighbours"]
            tiles.append(item)
        job = {"_input_dir": str(self.src), "name": f"{layout}_set", "tile_size": [SIZE, SIZE], "layout": layout, "terrains": terrains, "tiles": tiles}
        job.update(overrides)
        return job

    def build(self, **kwargs):
        return builder.build(self.job(**kwargs), self.out)


class BuildTests(BuildCase):
    def test_every_layout_builds_a_sheet_an_atlas_and_a_tileset_that_all_validate(self):
        for layout in rules.LAYOUTS:
            with self.subTest(layout):
                self.out = self.root / f"out_{layout}"
                png, atlas, tileset = self.build(layout=layout)
                self.assertEqual(png.name, f"{layout}_set.png")
                self.assertEqual(tileset.name, f"{layout}_set.tileset.json")
                self.assertEqual(validator.validate(tileset), [], layout)

    def test_the_sheet_is_a_regular_grid_of_tiles_with_the_tile_id_as_the_frame_index(self):
        png, atlas, tileset = self.build(layout="blob_47", columns=8)
        data = json.loads(atlas.read_text(encoding="utf-8"))
        meta = json.loads(tileset.read_text(encoding="utf-8"))
        self.assertEqual(len(data["frames"]), 47)
        self.assertEqual(meta["columns"], 8)
        for frame in data["frames"]:
            i = frame["index"]
            self.assertEqual(frame["rect"], [(i % 8) * SIZE, (i // 8) * SIZE, SIZE, SIZE])
        self.assertEqual([t["id"] for t in meta["tiles"]], list(range(47)))
        with Image.open(png) as shown:
            self.assertEqual(shown.size, (8 * SIZE, 6 * SIZE))

    def test_the_tileset_file_points_at_the_atlas_and_records_the_layout_and_terrains(self):
        _, _, tileset = self.build(layout="wang_edge_16")
        meta = json.loads(tileset.read_text(encoding="utf-8"))
        self.assertEqual((meta["atlas"], meta["layout"], meta["terrains"], meta["tile_size"]), ("wang_edge_16_set.atlas.json", "wang_edge_16", TERRAINS, [SIZE, SIZE]))
        self.assertTrue(meta["full_bleed"])

    def test_single_and_variant_tiles_get_their_labels_filled_in(self):
        _, _, tileset = self.build(layout="single")
        meta = json.loads(tileset.read_text(encoding="utf-8"))
        self.assertEqual(meta["tiles"][0]["neighbours"], {s: "grass" for s in rules.SIDES})

    def test_the_tile_pixels_are_the_source_pixels(self):
        png, _, _ = self.build(layout="wang_corner_16", columns=4)
        sheet = Image.open(png).convert("RGBA")
        first = Image.open(self.src / "t000.png").convert("RGBA")
        self.assertEqual(sheet.crop((0, 0, SIZE, SIZE)).tobytes(), first.tobytes())

    def test_an_incomplete_set_is_refused_and_the_missing_tile_is_named(self):
        gone = rules.layout_tiles("wang_corner_16", TERRAINS)[7]
        with self.assertRaisesRegex(ValueError, "missing tile: " + rules.tile_name("wang_corner_16", gone["neighbours"], TERRAINS)):
            self.build(drop={gone["identity"]})
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_a_tile_of_the_wrong_size_is_refused_by_file_name(self):
        job = self.job()
        Image.new("RGBA", (SIZE + 1, SIZE), GRASS).save(self.src / "t003.png")
        with self.assertRaisesRegex(ValueError, "t003.png.*9x8.*8x8"):
            builder.build(job, self.out)

    def test_an_existing_output_is_never_overwritten(self):
        self.build()
        with self.assertRaises(FileExistsError):
            self.build()

    def test_a_failed_build_leaves_nothing_behind(self):
        job = self.job()
        job["tiles"][2]["file"] = "does_not_exist.png"
        with self.assertRaises(ValueError):
            builder.build(job, self.out)
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_a_layout_the_schema_does_not_know_is_refused(self):
        job = self.job()
        job["layout"] = "hexagon_9"
        with self.assertRaises(ValueError):
            builder.build(job, self.out)


class ValidatorTests(BuildCase):
    def built(self, layout="wang_corner_16", **kwargs):
        _, atlas, tileset = self.build(layout=layout, **kwargs)
        return atlas, tileset

    def edit(self, path, change):
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_a_good_tileset_has_no_issues(self):
        _, tileset = self.built()
        self.assertEqual(validator.validate(tileset), [])

    def test_a_tile_removed_from_a_finished_tileset_is_named(self):
        _, tileset = self.built()
        self.edit(tileset, lambda d: d["tiles"].pop(4))
        self.assertTrue(any("missing tile" in i or "tile ids" in i for i in validator.validate(tileset)))

    def test_a_tile_size_that_disagrees_with_the_sheet_is_reported(self):
        _, tileset = self.built()
        self.edit(tileset, lambda d: d.update(tile_size=[16, 16]))
        self.assertTrue(any("tile size" in i for i in validator.validate(tileset)))

    def test_a_sheet_that_is_not_a_regular_grid_is_reported(self):
        atlas, tileset = self.built()
        self.edit(atlas, lambda d: d["frames"][3].update(rect=[d["frames"][3]["rect"][0] + 1, d["frames"][3]["rect"][1], SIZE, SIZE]))
        self.assertTrue(any("tile 3" in i and "grid" in i for i in validator.validate(tileset)))

    def test_art_that_does_not_match_the_next_tile_is_reported_with_both_tiles(self):
        # repaint the right half of one tile in the wrong terrain: its right side no longer lines up with the tiles that claim the same side
        png, atlas, tileset = self.build(layout="wang_corner_16", columns=4)
        meta = json.loads(tileset.read_text(encoding="utf-8"))
        target = next(t for t in meta["tiles"] if t["neighbours"]["top_right"] == "grass" and t["neighbours"]["bottom_right"] == "grass")
        sheet = Image.open(png).convert("RGBA")
        x0, y0 = (target["id"] % 4) * SIZE, (target["id"] // 4) * SIZE
        paint(sheet, (x0 + SIZE // 2, y0, x0 + SIZE, y0 + SIZE), WATER)
        sheet.save(png)
        issues = validator.validate(tileset)
        self.assertTrue(any(f"tile {target['id']}" in i and "right" in i and "do not line up" in i for i in issues), issues)

    def test_a_mismatch_along_the_bottom_side_is_found_as_well_as_the_right_one(self):
        png, atlas, tileset = self.build(layout="wang_corner_16", columns=4)
        meta = json.loads(tileset.read_text(encoding="utf-8"))
        target = next(t for t in meta["tiles"] if t["neighbours"]["bottom_left"] == "grass" and t["neighbours"]["bottom_right"] == "grass")
        sheet = Image.open(png).convert("RGBA")
        x0, y0 = (target["id"] % 4) * SIZE, (target["id"] // 4) * SIZE
        paint(sheet, (x0, y0 + SIZE // 2, x0 + SIZE, y0 + SIZE), WATER)
        sheet.save(png)
        issues = validator.validate(tileset)
        self.assertTrue(any(f"tile {target['id']}" in i and "bottom side" in i and "do not line up" in i for i in issues), issues)

    def test_the_atlas_and_the_tileset_must_agree_about_full_bleed(self):
        atlas, tileset = self.built()
        self.edit(tileset, lambda d: d.update(full_bleed=False))
        self.assertTrue(any("disagree about full_bleed" in i for i in validator.validate(tileset)))

    def test_a_tileset_with_fewer_tiles_than_the_atlas_has_frames_is_named_as_such(self):
        _, tileset = self.built()
        self.edit(tileset, lambda d: d["tiles"].pop())
        self.assertTrue(any("the atlas has 16 frames but the tileset lists 15 tiles" in i for i in validator.validate(tileset)))

    def test_a_perfect_set_has_no_seam_issues_even_when_every_tile_can_touch_itself(self):
        atlas, tileset = self.built(layout="single")
        self.assertEqual(validator.validate(tileset), [])

    def test_a_tile_that_does_not_tile_with_itself_is_reported(self):
        png, atlas, tileset = self.build(layout="single")
        sheet = Image.open(png).convert("RGBA")
        paint(sheet, (0, 0, 2, SIZE), WATER)  # the left edge differs from the right edge
        sheet.save(png)
        self.assertTrue(any("tile 0" in i and "do not line up" in i for i in validator.validate(tileset)))

    def test_a_texture_is_judged_against_its_own_variation_not_against_zero(self):
        def striped(_neighbours=None):  # neighbouring columns differ by about 200, so a seam of that size is just the texture
            image = Image.new("RGBA", (SIZE, SIZE))
            image.putdata([(30, 30, 30, 255) if x % 2 == 0 else (230, 230, 230, 255) for y in range(SIZE) for x in range(SIZE)])
            return image
        _, _, tileset = self.build(layout="single", art=striped)
        self.assertEqual(validator.validate(tileset), [])
        self.assertTrue(validator.validate(tileset, tolerance=0) == [], "the texture's own variation, not the tolerance, is what allows it")

    def test_a_key_coloured_pixel_in_a_full_bleed_tile_is_reported(self):
        png, atlas, tileset = self.build(layout="wang_corner_16")
        sheet = Image.open(png).convert("RGBA")
        sheet.putpixel((3, 3), (255, 0, 255, 255))
        sheet.save(png)
        issues = validator.validate(tileset)
        self.assertTrue(any("tile 0" in i and "key colour #FF00FF" in i and "full-bleed" in i for i in issues), issues)

    def test_a_tileset_whose_atlas_is_missing_is_reported_not_crashed(self):
        atlas, tileset = self.built()
        atlas.unlink()
        self.assertTrue(any("atlas" in i for i in validator.validate(tileset)))

    def test_a_tileset_file_that_breaks_the_contract_is_reported(self):
        _, tileset = self.built()
        self.edit(tileset, lambda d: d.update(layout="hexagon_9"))
        issues = validator.validate(tileset)
        self.assertTrue(issues and "tileset contract" in issues[0])


class GateTests(BuildCase):
    """A registered bundle that holds a tileset is checked as one, so a broken tileset cannot be approved."""

    def register(self, edit=None):
        kit.write_settings(self.root)
        image, metadata = kit.make_mockup(self.root, "scene-a", "v001", "world")
        life.register_mockup(self.root, metadata, image)
        life.approve_mockup(self.root, "scene-a", "v001", "approved")
        folder = self.root / ".gamearts/outputs/assets/generated/ground_v001"
        self.out = folder
        _, _, tileset = self.build(layout="wang_corner_16", name="ground")
        if edit:
            data = json.loads(tileset.read_text(encoding="utf-8"))
            edit(data)
            tileset.write_text(json.dumps(data), encoding="utf-8")
        return life.register_asset(self.root, "ground_v001", "v001", ".gamearts/outputs/assets/generated/ground_v001", [("scene-a", "v001")])

    def test_a_complete_tileset_passes_the_gate_and_is_listed_in_the_record(self):
        result = self.register()
        self.assertEqual(result["technical_validation"], "passed", result.get("technical_issues"))
        record = life.records(self.root, "assets")[0]
        self.assertEqual(record["technical_validation"]["tilesets"], ["ground.tileset.json"])

    def test_a_tileset_with_a_missing_tile_fails_the_gate_by_name_and_cannot_be_approved(self):
        result = self.register(lambda data: data["tiles"].pop())
        self.assertEqual(result["technical_validation"], "failed")
        self.assertTrue(any("ground.tileset.json" in i and "missing tile" in i for i in result["technical_issues"]), result["technical_issues"])
        with self.assertRaisesRegex(ValueError, "Technical artwork gate failed"):
            life.approve_asset(self.root, "ground_v001", "looks fine")

    def test_a_sheet_problem_is_reported_once_not_twice(self):
        folder = self.root / ".gamearts/outputs/assets/generated/ground_v001"
        self.register()
        sheet = Image.open(folder / "ground.png").convert("RGBA")
        sheet.putpixel((0, 0), (254, 1, 254, 255))  # near the key colour
        sheet.save(folder / "ground.png")
        technical = life.technical_check_bundle(folder)
        near_key = [i for i in technical["issues"] if "near-#FF00FF" in i]
        self.assertEqual(len(near_key), 1, technical["issues"])


if __name__ == "__main__":
    unittest.main()
