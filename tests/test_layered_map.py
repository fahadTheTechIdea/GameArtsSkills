"""Layered maps (plan P16): a scene read into terrain layers and objects, and the checks that it holds together."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)
from PIL import Image

import build_tileset as tileset_builder  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402
import gamearts_tileset as tile_rules  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_layered_map.py"
CELL = 8
COLOURS = {"water": (60, 110, 190), "sand": (222, 205, 150), "grass": (96, 170, 80)}
TERRAINS = [{"id": "water", "symbol": "~", "colours": ["#3C6EBE"], "priority": 0, "walkable": False},
            {"id": "sand", "symbol": ".", "colours": ["#DECD96"], "priority": 1, "walkable": True},
            {"id": "grass", "symbol": "g", "colours": ["#60AA50"], "priority": 2, "walkable": True}]
ROWS = ["~~..gg",
        "~...gg",
        "~~.ggg",
        "~~~...",
        ]
INDEX = {"~": 0, ".": 1, "g": 2}


def scene(rows=ROWS):
    image = Image.new("RGB", (len(rows[0]) * CELL, len(rows) * CELL))
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            image.paste(COLOURS[("water", "sand", "grass")[INDEX[char]]], (x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL))
    return image


def make_tileset(folder, name, layout, terrains, colours):
    """A real tileset built with the framework's builder: flat tiles for a base, corner tiles for an overlay."""
    src = Path(folder) / f"src_{name}"
    src.mkdir()
    tiles = []
    for index, tile in enumerate(tile_rules.layout_tiles(layout, terrains)):
        file = f"t{index:03d}.png"
        if layout in ("single", "variants"):
            Image.new("RGBA", (CELL, CELL), colours[terrains[0]] + (255,)).save(src / file)
            tiles.append({"file": file})
        else:
            image = Image.new("RGBA", (CELL, CELL))
            half = CELL // 2
            boxes = {"top_left": (0, 0, half, half), "top_right": (half, 0, CELL, half), "bottom_right": (half, half, CELL, CELL), "bottom_left": (0, half, half, CELL)}
            for side, box in boxes.items():
                image.paste((colours[terrains[0]] if tile["neighbours"][side] == terrains[0] else colours[terrains[1]]) + (255,), box)
            image.save(src / file)
            tiles.append({"file": file, "neighbours": tile["neighbours"]})
    job = {"_input_dir": str(src), "name": name, "tile_size": [CELL, CELL], "layout": layout, "terrains": terrains, "tiles": tiles}
    tileset_builder.build(job, Path(folder))


class MapCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.out = self.root / "map"
        self.out.mkdir()
        scene().save(self.root / "scene.png")
        below = (10, 10, 10)
        make_tileset(self.out, "water_ground", "single", ["water"], {"water": COLOURS["water"]})
        make_tileset(self.out, "sand_overlay", "dual_grid_16", ["sand", "below"], {"sand": COLOURS["sand"], "below": below})
        make_tileset(self.out, "grass_overlay", "dual_grid_16", ["grass", "below"], {"grass": COLOURS["grass"], "below": below})
        kit.make_sheet(self.out, "rocks", "rocks")
        self.terrains = [dict(t) for t in TERRAINS]
        for entry, file in zip(self.terrains, ("water_ground.tileset.json", "sand_overlay.tileset.json", "grass_overlay.tileset.json")):
            entry["tileset"] = file

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, name="shore", **kwargs):
        kwargs.setdefault("terrains", self.terrains)
        terrains = kwargs.pop("terrains")
        return layered.build(self.root / "scene.png", terrains, (CELL, CELL), name, self.out, **kwargs)

    def rock(self, identifier, x, y, **extra):
        return dict({"id": identifier, "class": "prop", "sprite": {"atlas": "rocks.atlas.json", "frame": "S0"}, "position_px": [x, y]}, **extra)


class BuildTests(MapCase):
    def test_the_scene_becomes_labels_and_a_layer_stack_in_priority_order(self):
        path, data = self.build()
        self.assertEqual(data["labels"], ROWS)
        self.assertEqual([layer["id"] for layer in data["layers"]], ["ground_water", "overlay_sand", "overlay_grass", "objects", "gameplay"])
        self.assertEqual((data["grid"]["width"], data["grid"]["height"]), (6, 4))
        self.assertEqual(layered.validate(path), [])
        self.assertEqual(data["validation"]["engine_validation"], "not_tested")

    def test_nothing_is_overwritten_and_a_map_that_fails_its_check_is_not_left_behind(self):
        self.build()
        with self.assertRaises(FileExistsError):
            self.build()
        before = sorted(p.name for p in self.out.iterdir())
        with self.assertRaisesRegex(ValueError, "do(es)? not hold together|overlap"):
            self.build("other", objects=[self.rock("a", 20, 20, footprint_px=[8, 8]), self.rock("b", 22, 20, footprint_px=[8, 8])])
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), before)

    def test_two_terrains_may_not_share_an_id_a_symbol_or_a_priority(self):
        for key, value in (("id", "water"), ("symbol", "~"), ("priority", 0)):
            terrains = [dict(t) for t in self.terrains]
            terrains[1][key] = value
            with self.subTest(key), self.assertRaisesRegex(ValueError, f"share a {key}"):
                self.build("clash", terrains=terrains)

    def test_a_cell_far_from_every_terrain_is_listed_as_unclassified(self):
        image = scene()
        image.paste((250, 20, 250), (0, 0, CELL, CELL))
        image.save(self.root / "scene.png")
        _, data = self.build()
        self.assertEqual(data["source"]["read"]["unclassified_cells"], [[0, 0]])

    def test_cleanup_is_off_unless_asked_and_reports_what_it_changed(self):
        rows = ["~~~~~~", "~~.~~~", "~~~~~~", "~~~~~~"]
        scene(rows).save(self.root / "scene.png")
        _, kept = self.build("kept")
        self.assertEqual((kept["labels"], kept["source"]["read"]["cells_changed"]), (rows, 0))
        _, tidied = self.build("tidied", min_region=2)
        self.assertEqual(tidied["labels"][1], "~~~~~~")
        self.assertEqual(tidied["source"]["read"], dict(tidied["source"]["read"], area_opening_minimum=2, cells_changed=1))


class OccluderBuildTests(MapCase):
    def test_what_is_drawn_over_the_ground_is_read_as_the_ground_around_it_and_listed(self):
        image = scene()
        image.paste((30, 80, 40), (2 * CELL, 1 * CELL, 3 * CELL, 2 * CELL))  # a tree over the cell at (2, 1), which is sand
        image.save(self.root / "scene.png")
        occluders = [{"id": "tree", "colours": ["#1E5028"]}]
        path, data = self.build("tree", occluders=occluders)
        self.assertEqual(data["labels"], ROWS)  # the tree's cell is the sand around it, as the unobstructed scene has it
        self.assertEqual(data["source"]["read"]["occluded_cells"], [[2, 1]])
        self.assertEqual(layered.validate(path), [])

    def test_without_occluders_nothing_is_filled_and_the_list_is_empty(self):
        _, data = self.build()
        self.assertEqual(data["source"]["read"]["occluded_cells"], [])

    def test_the_command_takes_an_occluders_file(self):
        image = scene()
        image.paste((30, 80, 40), (2 * CELL, 1 * CELL, 3 * CELL, 2 * CELL))
        image.save(self.root / "scene.png")
        (self.root / "terrains.json").write_text(json.dumps(self.terrains), encoding="utf-8")
        (self.root / "occluders.json").write_text(json.dumps([{"id": "tree", "colours": ["#1E5028"]}]), encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "build", "--image", str(self.root / "scene.png"), "--terrains", str(self.root / "terrains.json"), "--cell", "8x8",
                               "--name", "occ", "--output-dir", str(self.out), "--occluders", str(self.root / "occluders.json")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["occluded_cells"], 1)


class MaskBuildTests(MapCase):
    def misleading_scene(self):
        image = scene()
        image.paste(COLOURS["grass"], (2 * CELL, 1 * CELL, 3 * CELL, 2 * CELL))  # an object whose colour is a ground colour: the read alone calls it grass
        image.save(self.root / "scene.png")

    def mask_file(self, covering=(2, 1)):
        mask = Image.new("L", (6 * CELL, 4 * CELL), 0)
        mask.paste(255, (covering[0] * CELL, covering[1] * CELL, (covering[0] + 1) * CELL, (covering[1] + 1) * CELL))
        path = self.root / "mask.png"
        mask.save(path)
        return path

    def test_without_the_mask_the_misleading_colour_is_read_as_ground(self):
        self.misleading_scene()
        _, data = self.build("plain")
        self.assertEqual(data["labels"][1][2], "g")

    def test_the_cells_a_mask_covers_take_the_ground_around_them_and_are_listed_with_the_masks_hash(self):
        self.misleading_scene()
        path, data = self.build("masked", occlusion_mask=self.mask_file())
        self.assertEqual(data["labels"], ROWS)  # the object's cell is the sand around it
        self.assertEqual(data["source"]["read"]["occluded_cells"], [[2, 1]])
        self.assertEqual(data["source"]["read"]["occlusion_mask_sha256"], common.sha256_file(self.root / "mask.png"))
        self.assertEqual(layered.validate(path), [])

    def test_a_mask_of_another_size_is_refused_and_leaves_no_map(self):
        self.misleading_scene()
        Image.new("L", (10, 10)).save(self.root / "small.png")
        before = sorted(p.name for p in self.out.iterdir())
        with self.assertRaisesRegex(ValueError, "the occlusion mask is 10 x 10"):
            self.build("bad", occlusion_mask=self.root / "small.png")
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), before)

    def test_the_command_takes_a_mask(self):
        self.misleading_scene()
        (self.root / "terrains.json").write_text(json.dumps(self.terrains), encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "build", "--image", str(self.root / "scene.png"), "--terrains", str(self.root / "terrains.json"), "--cell", "8x8",
                               "--name", "viamask", "--output-dir", str(self.out), "--occlusion-mask", str(self.mask_file())], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["occluded_cells"], 1)


class SolidAndSwatchTests(MapCase):
    def solid_file(self, cells=((2, 2),)):
        mask = Image.new("L", (6 * CELL, 4 * CELL), 0)
        for x, y in cells:
            mask.paste(255, (x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL))
        path = self.root / "solid.png"
        mask.save(path)
        return path

    def test_a_solid_cell_blocks_movement_though_its_inferred_ground_is_walkable(self):
        _, plain = self.build("plain")
        self.assertEqual(layered.gameplay_grid(plain)[2][2], ".")
        _, data = self.build("solid", solid_mask=self.solid_file())
        self.assertEqual(layered.gameplay_grid(data)[2][2], "#")
        self.assertEqual(data["source"]["read"]["solid_cells"], [[2, 2]])
        self.assertEqual(data["source"]["read"]["solid_mask_sha256"], common.sha256_file(self.root / "solid.png"))
        self.assertIn([2, 2], data["source"]["read"]["occluded_cells"])  # the ground under it is inferred, and said to be

    def test_solid_cells_are_listed_in_reading_order_and_the_map_validates(self):
        path, data = self.build("solid", solid_mask=self.solid_file(((4, 1), (0, 3), (2, 1))))
        self.assertEqual(data["source"]["read"]["solid_cells"], [[2, 1], [4, 1], [0, 3]])
        self.assertEqual(layered.validate(path), [])

    def test_a_solid_mask_of_another_size_is_refused(self):
        Image.new("L", (10, 10)).save(self.root / "small.png")
        with self.assertRaisesRegex(ValueError, "the solid mask is 10 x 10"):
            self.build("bad", solid_mask=self.root / "small.png")

    def test_the_cleanest_crop_of_each_terrain_is_written_as_a_reference_and_never_overwritten(self):
        path, _ = self.build("swatch")
        result = layered.plan(path, None, self.root / "scene.png", self.root / "swatches")
        by_terrain = {item["terrain"]: item["reference_swatch"] for item in result["tilesets"]}
        for terrain_id in ("water", "sand", "grass"):
            self.assertTrue(by_terrain[terrain_id]["file"], terrain_id)
            crop = Image.open(self.root / "swatches" / by_terrain[terrain_id]["file"])
            size = by_terrain[terrain_id]["cells"][2]
            self.assertEqual(crop.size, (size * CELL, size * CELL))
            self.assertEqual(len(set(crop.convert("RGB").getdata())), 1)  # the scene was painted flat, so a clean crop is one colour
        with self.assertRaisesRegex(ValueError, "already exists"):
            layered.plan(path, None, self.root / "scene.png", self.root / "swatches")

    def test_a_cell_the_ground_read_had_to_infer_is_never_inside_a_swatch(self):
        mask = Image.new("L", (6 * CELL, 4 * CELL), 0)
        mask.paste(255, (5 * CELL, 0, 6 * CELL, CELL))  # an object stands on one grass cell in the corner: its label is filled from the grass beside it
        mask.save(self.root / "occ.png")
        path, data = self.build("inferred", occlusion_mask=self.root / "occ.png")
        self.assertEqual(data["labels"][0][5], "g")
        result = layered.plan(path, None, self.root / "scene.png", self.root / "swatches")
        grass = next(i for i in result["tilesets"] if i["terrain"] == "grass")["reference_swatch"]
        self.assertEqual(grass["cells"], [4, 1, 2])  # the 2 x 2 patch that includes the inferred cell is passed over for the one beside it

    def test_a_terrain_with_no_cell_in_plain_view_says_so_instead_of_cropping(self):
        path, _ = self.build("hidden", solid_mask=self.solid_file(tuple((x, y) for x in range(6) for y in range(4) if ROWS[y][x] == "g")))
        result = layered.plan(path, None, self.root / "scene.png", self.root / "swatches")
        grass = next(i for i in result["tilesets"] if i["terrain"] == "grass")["reference_swatch"]
        self.assertIsNone(grass["file"])
        self.assertIn("plain view", grass["why"])

    def test_a_scene_of_another_size_is_refused_for_swatches(self):
        path, _ = self.build("size")
        Image.new("RGB", (10, 10)).save(self.root / "other.png")
        with self.assertRaisesRegex(ValueError, "not the size of the map"):
            layered.plan(path, None, self.root / "other.png", self.root / "swatches")

    def test_the_mask_command_writes_a_picture_from_boxes_and_never_overwrites(self):
        (self.root / "boxes.json").write_text(json.dumps([[0, 0, 8, 8]]), encoding="utf-8")
        argv = [sys.executable, str(SCRIPT), "mask", "--size", "48x32", "--boxes", str(self.root / "boxes.json"), "--output", str(self.root / "m.png")]
        done = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(Image.open(self.root / "m.png").getpixel((0, 0)), 255)
        again = subprocess.run(argv, capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("already exists", again.stderr + again.stdout)


class OverlayTests(MapCase):
    def test_every_position_of_an_overlay_gets_a_tile_the_tileset_has(self):
        path, data = self.build()
        for terrain_id in ("sand", "grass"):
            plan = layered.overlay_plan(data, self.out, terrain_id)
            self.assertEqual(plan["missing"], [], terrain_id)
            self.assertEqual(len(plan["tiles"]) + plan["empty_positions"], (6 + 1) * (4 + 1))
        # the sand overlay covers sand and grass cells, so the whole right side is drawn
        self.assertGreater(len(layered.overlay_plan(data, self.out, "sand")["tiles"]), len(layered.overlay_plan(data, self.out, "grass")["tiles"]))

    def test_each_position_gets_the_tile_made_of_the_overlay_terrain_where_the_overlay_covers_it(self):
        _, data = self.build()
        tileset = common.read_json(self.out / "sand_overlay.tileset.json")
        by_id = {tile["id"]: tile for tile in tileset["tiles"]}
        plan = layered.overlay_plan(data, self.out, "sand")
        inside = plan["tiles"][(4, 2)]  # four sand or grass cells meet here: the overlay covers all of them
        self.assertEqual(set(by_id[inside]["neighbours"].values()), {"sand"})
        edge = plan["tiles"][(1, 1)]  # water, sand and a mix: some corners are covered and some are not
        self.assertEqual(set(by_id[edge]["neighbours"].values()), {"sand", "below"})

    def test_a_tile_the_tileset_lacks_is_named_and_the_map_check_fails(self):
        path, data = self.build()
        file = self.out / "sand_overlay.tileset.json"
        tileset = common.read_json(file)
        tileset["tiles"] = [tile for tile in tileset["tiles"] if tile_rules.identity(tileset["layout"], tile["neighbours"], tileset["terrains"]) != (0, 0, 0, 1)]
        common.atomic_write_json(file, tileset)
        plan = layered.overlay_plan(data, self.out, "sand")
        self.assertTrue(plan["missing"])
        self.assertTrue(any("no tile for position" in p for p in layered.validate(path)))

    def test_the_wrong_layout_order_or_size_of_a_tileset_is_named(self):
        path, _ = self.build()
        file = self.out / "sand_overlay.tileset.json"
        tileset = common.read_json(file)
        tileset["terrains"] = ["below", "sand"]
        common.atomic_write_json(file, tileset)
        self.assertTrue(any("must list sand" in p for p in layered.validate(path)))
        tileset["terrains"] = ["sand", "below"]
        tileset["tile_size"] = [16, 16]
        common.atomic_write_json(file, tileset)
        self.assertTrue(any("tiles are [16, 16]" in p for p in layered.validate(path)))
        data = common.read_json(path)
        data["terrains"][1]["tileset"] = "water_ground.tileset.json"
        common.atomic_write_json(path, data)
        self.assertTrue(any("needs dual_grid_16" in p for p in layered.validate(path)))


class ObjectTests(MapCase):
    def validate_with(self, objects):
        self.count = getattr(self, "count", 0) + 1
        path, data = self.build(f"with_objects_{self.count}")
        data["objects"] = objects
        data["layers"] = layered.layers_for(data["terrains"], objects)
        common.atomic_write_json(path, data)
        return layered.validate(path)

    def test_a_well_placed_object_passes_and_each_fault_is_named(self):
        self.assertEqual(self.validate_with([self.rock("a", 20, 20, footprint_px=[8, 8], collision="footprint")]), [])
        found = self.validate_with([self.rock("a", 500, 20), self.rock("a", 20, 20)])
        self.assertTrue(any("share an id" in p for p in found) and any("lies outside" in p for p in found))
        wrong = self.rock("b", 20, 20)
        wrong["sprite"] = {"atlas": "rocks.atlas.json", "frame": "nope"}
        self.assertTrue(any("no frame named nope" in p for p in self.validate_with([wrong])))
        wrong["sprite"] = {"atlas": "missing.atlas.json", "frame": "S0"}
        self.assertTrue(any("is missing" in p for p in self.validate_with([wrong])))
        self.assertTrue(any("no footprint_px" in p for p in self.validate_with([self.rock("c", 20, 20, collision="footprint")])))
        self.assertTrue(any("runs outside the map" in p for p in self.validate_with([self.rock("d", 4, 6, footprint_px=[16, 16])])))

    def test_footprints_may_not_overlap_unless_they_say_so(self):
        close = [self.rock("a", 20, 20, footprint_px=[8, 8]), self.rock("b", 22, 20, footprint_px=[8, 8])]
        self.assertTrue(any("overlap on the ground" in p for p in self.validate_with(close)))
        close[1]["allow_overlap"] = True
        self.assertEqual(self.validate_with(close), [])

    def test_an_overhead_object_adds_its_layer(self):
        path, data = self.build("high")
        data["objects"] = [self.rock("roof", 20, 20, layer="overhead")]
        self.assertIn("overhead", [layer["id"] for layer in layered.layers_for(data["terrains"], data["objects"])])
        self.assertEqual(self.validate_with(data["objects"]), [])


class StructureTests(MapCase):
    def test_hand_edited_layers_labels_and_grid_are_found(self):
        path, _ = self.build()
        data = common.read_json(path)
        data["layers"] = list(reversed(data["layers"]))
        common.atomic_write_json(path, data)
        self.assertTrue(any("layers are not the stack" in p for p in layered.validate(path)))
        data = common.read_json(path)
        data["layers"] = layered.layers_for(data["terrains"], [])
        data["labels"][0] = "~~..gX"
        common.atomic_write_json(path, data)
        self.assertTrue(any("is no terrain's symbol" in p for p in layered.validate(path)))
        data["labels"][0] = "~~..g"
        common.atomic_write_json(path, data)
        self.assertTrue(any("every row must be as long" in p for p in layered.validate(path)))
        data["labels"] = ["~~..gg"] * 3
        common.atomic_write_json(path, data)
        self.assertTrue(any("the grid says 6 x 4" in p for p in layered.validate(path)))

    def test_a_map_that_is_not_json_or_breaks_the_contract_is_reported_not_raised(self):
        bad = self.out / "bad.layered_map.json"
        bad.write_text("{", encoding="utf-8")
        self.assertTrue(layered.validate(bad)[0].startswith("layered map contract"))


class GameplayTests(MapCase):
    def test_water_is_blocked_land_is_walkable_and_an_objects_footprint_blocks_the_cells_it_covers(self):
        path, data = self.build()
        grid = layered.gameplay_grid(data)
        self.assertEqual(grid[0], "##....")  # two water cells blocked, the rest walkable
        self.assertEqual(grid[3], "###...")
        data["objects"] = [self.rock("a", 4 * CELL + 4, 2 * CELL, footprint_px=[CELL, CELL], collision="footprint")]
        self.assertEqual(layered.gameplay_grid(data)[1][4], "#")
        self.assertEqual(layered.gameplay_grid(data)[1][3], ".")
        data["objects"][0]["collision"] = "none"
        self.assertEqual(layered.gameplay_grid(data)[1][4], ".")


class CommandTests(MapCase):
    def run_script(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True)

    def test_the_commands_build_validate_list_an_overlay_and_print_the_gameplay_grid(self):
        terrains = self.root / "terrains.json"
        terrains.write_text(json.dumps(self.terrains), encoding="utf-8")
        done = self.run_script("build", "--image", str(self.root / "scene.png"), "--terrains", str(terrains), "--cell", "8x8", "--name", "cli", "--output-dir", str(self.out))
        self.assertEqual(done.returncode, 0, done.stderr)
        checked = self.run_script("validate", str(self.out / "cli.layered_map.json"))
        self.assertEqual((checked.returncode, json.loads(checked.stdout)["status"]), (0, "passed"))
        self.assertIn("not_assessed", checked.stdout)
        overlay = json.loads(self.run_script("overlay", str(self.out / "cli.layered_map.json"), "--terrain", "sand").stdout)
        self.assertEqual(overlay["missing"], [])
        self.assertEqual(json.loads(self.run_script("gameplay", str(self.out / "cli.layered_map.json")).stdout)["gameplay"][0], "##....")
        again = self.run_script("build", "--image", str(self.root / "scene.png"), "--terrains", str(terrains), "--cell", "8x8", "--name", "cli", "--output-dir", str(self.out))
        self.assertEqual(again.returncode, 1)


if __name__ == "__main__":
    unittest.main()
