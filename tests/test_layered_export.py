"""The last two steps of the tileset pipeline (plan P16): what a layered map still needs, and the Tiled map of the whole scene."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)
from PIL import Image

import export_exchange as exchange  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402
import gamearts_tileset as tile_rules  # noqa: E402
from test_layered_map import CELL, MapCase  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_exchange.py"


class Case(MapCase):
    def built(self, objects=()):
        path, data = self.build("scene", objects=list(objects))
        return path, data


class PlanTests(Case):
    def test_a_map_whose_tilesets_are_all_there_is_ready(self):
        path, _ = self.built()
        plan = layered.plan(path)
        self.assertTrue(plan["ready"])
        self.assertEqual([(t["terrain"], t["status"], t["layout"]) for t in plan["tilesets"]],
                         [("water", "present", "single"), ("sand", "present", "dual_grid_16"), ("grass", "present", "dual_grid_16")])
        self.assertTrue(all(t["tiles"] == [] for t in plan["tilesets"]))

    def test_a_terrain_with_no_tileset_lists_every_picture_to_make_in_words(self):
        terrains = [dict(t) for t in self.terrains]
        del terrains[1]["tileset"]
        path, _ = self.build("bare", terrains=terrains)
        plan = layered.plan(path)
        sand = next(t for t in plan["tilesets"] if t["terrain"] == "sand")
        self.assertEqual((sand["status"], sand["pictures"], sand["terrains"]), ("missing", 16, ["sand", "below"]))
        self.assertEqual(len(sand["tiles"]), 16)
        self.assertTrue(all(tile["describes"].startswith("corners ") for tile in sand["tiles"]))
        self.assertIn("never drawn", sand["note"])
        self.assertFalse(plan["ready"])

    def test_a_tileset_that_is_named_but_whose_file_is_missing_is_missing_not_invalid(self):
        path, _ = self.built()
        (self.out / "grass_overlay.tileset.json").unlink()
        grass = next(t for t in layered.plan(path)["tilesets"] if t["terrain"] == "grass")
        self.assertEqual(grass["status"], "missing")
        self.assertEqual(len(grass["tiles"]), 16)

    def test_a_damaged_tileset_is_reported_invalid_with_its_problems(self):
        path, _ = self.built()
        file = self.out / "sand_overlay.tileset.json"
        tileset = common.read_json(file)
        tileset["tiles"] = tileset["tiles"][:-1]
        common.atomic_write_json(file, tileset)
        sand = next(t for t in layered.plan(path)["tilesets"] if t["terrain"] == "sand")
        self.assertEqual(sand["status"], "invalid")
        self.assertTrue(sand["problems"])

    def test_job_skeletons_cover_every_tile_of_the_layout_and_are_never_overwritten(self):
        terrains = [dict(t) for t in self.terrains]
        del terrains[2]["tileset"]
        path, _ = self.build("jobs", terrains=terrains)
        jobs = self.root / "jobs"
        plan = layered.plan(path, jobs)
        grass = next(t for t in plan["tilesets"] if t["terrain"] == "grass")
        job = common.read_json(jobs / grass["job"])
        self.assertEqual((job["layout"], job["terrains"], job["tile_size"]), ("dual_grid_16", ["grass", "below"], [CELL, CELL]))
        identities = {tile_rules.identity(job["layout"], tile["neighbours"], job["terrains"]) for tile in job["tiles"]}
        self.assertEqual(identities, {tile["identity"] for tile in tile_rules.layout_tiles("dual_grid_16", ["grass", "below"])})
        self.assertEqual(len({tile["file"] for tile in job["tiles"]}), 16)
        with self.assertRaisesRegex(ValueError, "never overwritten"):
            layered.plan(path, jobs)
        self.assertEqual([p.name for p in jobs.iterdir()], ["grass_tileset_job.json"])  # the present tilesets got no skeleton

    def test_the_cells_that_are_inferred_or_unclassified_are_counted_so_the_read_is_not_over_trusted(self):
        path, _ = self.built()
        self.assertEqual(layered.plan(path)["uncertain"], {"unclassified_cells": 0, "occluded_cells": 0})


class WholeRouteTests(MapCase):
    def draw(self, tile, over, below):
        """A picture for one planned tile: each corner the colour of the terrain the plan says it shows."""
        image = Image.new("RGBA", (CELL, CELL))
        half = CELL // 2
        boxes = {"top_left": (0, 0, half, half), "top_right": (half, 0, CELL, half), "bottom_right": (half, half, CELL, CELL), "bottom_left": (0, half, half, CELL)}
        for side, box in boxes.items():
            colour = over if tile["neighbours"][side] != "below" else below
            image.paste(colour + (255,), box)
        return image

    def test_the_route_in_the_guide_goes_from_a_bare_scene_to_a_tiled_map(self):
        import build_tileset as builder
        terrains = [{k: v for k, v in t.items() if k != "tileset"} for t in self.terrains]
        path, _ = self.build("route", terrains=terrains)  # 1-2: read the scene
        jobs = self.root / "jobs"
        plan = layered.plan(path, jobs)  # 3: plan the art and write a skeleton for each tileset still to make
        self.assertFalse(plan["ready"])
        self.assertEqual({t["status"] for t in plan["tilesets"]}, {"missing"})
        below = (10, 10, 10)
        data = common.read_json(path)
        for entry in plan["tilesets"]:  # 4: make the pictures, build each tileset from its job
            job = common.read_json(jobs / entry["job"])
            over = fixtures_colour(entry["terrain"])
            for tile in entry["tiles"]:
                if entry["layout"] == "single":
                    Image.new("RGBA", (CELL, CELL), over + (255,)).save(jobs / tile["picture"])
                else:
                    self.draw(tile, over, below).save(jobs / tile["picture"])
            job["_input_dir"] = str(jobs)
            builder.build(job, self.out)
            for terrain in data["terrains"]:
                if terrain["id"] == entry["terrain"]:
                    terrain["tileset"] = f"{job['name']}.tileset.json"
        common.atomic_write_json(path, data)
        self.assertTrue(layered.plan(path)["ready"])  # 5: every tileset is now there and valid
        self.assertEqual(layered.validate(path), [])
        written = exchange.export_layered_map(path)  # 6: export
        self.assertEqual(json.loads(written.read_text(encoding="utf-8"))["layers"][0]["name"], "ground_water")


def fixtures_colour(terrain):
    from test_layered_map import COLOURS
    return COLOURS[terrain]


class TiledMapTests(Case):
    def export(self, objects=()):
        path, data = self.built(objects)
        return path, data, exchange.tiled_map(path)

    def test_the_layers_come_in_the_maps_order_on_a_grid_one_cell_larger(self):
        path, data, tiled = self.export([self.rock("a", 20, 20, footprint_px=[8, 8], collision="footprint")])
        self.assertEqual((tiled["type"], tiled["orientation"], tiled["infinite"]), ("map", "orthogonal", False))
        self.assertEqual((tiled["width"], tiled["height"], tiled["tilewidth"], tiled["tileheight"]), (7, 5, CELL, CELL))
        self.assertEqual([layer["name"] for layer in tiled["layers"]], ["ground_water", "overlay_sand", "overlay_grass", "objects", "collision"])
        self.assertEqual([layer["type"] for layer in tiled["layers"]], ["tilelayer", "tilelayer", "tilelayer", "objectgroup", "objectgroup"])

    def test_the_overlays_are_offset_by_half_a_cell_and_the_ground_is_not(self):
        _, _, tiled = self.export()
        ground, sand = tiled["layers"][0], tiled["layers"][1]
        self.assertNotIn("offsetx", ground)
        self.assertEqual((sand["offsetx"], sand["offsety"]), (-CELL / 2, -CELL / 2))

    def test_every_tile_is_the_one_the_frameworks_plan_chose_inside_its_tilesets_range(self):
        path, data, tiled = self.export()
        starts = {ts["name"]: ts["firstgid"] for ts in tiled["tilesets"]}
        water_first = starts["water_ground"]
        ground = tiled["layers"][0]["data"]
        self.assertEqual({ground[y * 7 + x] for y in range(4) for x in range(6)}, {water_first})  # every scene cell is the base tile
        self.assertTrue(all(ground[y * 7 + 6] == 0 for y in range(5)) and all(ground[4 * 7 + x] == 0 for x in range(7)))  # the extra row and column are empty
        sand = tiled["layers"][1]["data"]
        plan = layered.overlay_plan(data, self.out, "sand")
        for (x, y), tile_id in plan["tiles"].items():
            self.assertEqual(sand[y * 7 + x], starts["sand_overlay"] + tile_id)
        self.assertEqual(sum(1 for gid in sand if gid), len(plan["tiles"]))
        ranges = [(ts["firstgid"], ts["firstgid"] + ts["tilecount"]) for ts in tiled["tilesets"]]
        self.assertTrue(all(any(a <= gid < b for a, b in ranges) for layer in tiled["layers"][:3] for gid in layer["data"] if gid))
        self.assertEqual(sorted(ranges), ranges)
        self.assertTrue(all(ranges[i][1] == ranges[i + 1][0] for i in range(len(ranges) - 1)))  # tile ids never overlap between tilesets

    def test_an_object_sits_so_that_its_pivot_lands_on_its_position(self):
        path, data, tiled = self.export([self.rock("rock_a", 20, 20)])
        objects = next(layer for layer in tiled["layers"] if layer["name"] == "objects")
        atlas = common.read_json(self.out / "rocks.atlas.json")
        frame = atlas["frames"][0]
        placed = objects["objects"][0]
        rocks = next(ts for ts in tiled["tilesets"] if ts["name"] == "rocks")
        self.assertEqual(placed["gid"], rocks["firstgid"] + 0)
        self.assertEqual((placed["x"], placed["y"]), (20 - frame["pivot"][0], 20 - frame["pivot"][1] + frame["rect"][3]))  # Tiled puts a tile object's y at its bottom
        self.assertEqual(objects["draworder"], "topdown")
        tile = rocks["tiles"][0]
        self.assertEqual((tile["x"], tile["y"], tile["width"], tile["height"]), tuple(frame["rect"]))

    def test_blocking_footprints_become_a_collision_layer_and_the_gameplay_grid_rides_along(self):
        path, data, tiled = self.export([self.rock("rock_a", 20, 20, footprint_px=[8, 8], collision="footprint"), self.rock("rock_b", 36, 28, footprint_px=[8, 8])])
        collision = next(layer for layer in tiled["layers"] if layer["name"] == "collision")
        self.assertEqual([(o["name"], o["x"], o["y"], o["width"], o["height"]) for o in collision["objects"]], [("rock_a", 16, 12, 8, 8)])
        props = {p["name"]: p["value"] for p in tiled["properties"]}
        self.assertEqual(props["gameplay"].split("\n"), layered.gameplay_grid(data))
        self.assertEqual(props["base_terrain"], "water")

    def test_a_terrain_with_no_tileset_and_a_map_that_fails_its_check_are_refused(self):
        terrains = [dict(t) for t in self.terrains]
        del terrains[1]["tileset"]
        path, _ = self.build("bare", terrains=terrains)
        with self.assertRaisesRegex(ValueError, "terrain sand names no tileset"):
            exchange.tiled_map(path)
        good, _ = self.built()
        data = common.read_json(good)
        data["labels"][0] = "~~..gX"
        common.atomic_write_json(good, data)
        with self.assertRaisesRegex(ValueError, "fails its own checks"):
            exchange.tiled_map(good)

    def test_a_file_is_written_never_overwritten_and_the_command_does_the_same(self):
        path, _ = self.built([self.rock("rock_a", 20, 20)])
        written = exchange.export_layered_map(path)
        self.assertEqual(written.name, "scene.tmj")
        self.assertEqual(json.loads(written.read_text(encoding="utf-8"))["type"], "map")
        with self.assertRaisesRegex(ValueError, "never overwrites"):
            exchange.export_layered_map(path)
        done = subprocess.run([sys.executable, str(SCRIPT), "--layered-map", str(path), "--output", str(self.out / "other.tmj")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), "--layered-map", str(path), "--format", "aseprite-array", "--output", str(self.out / "x.tmj")],
                                        capture_output=True, text=True).returncode, 1)


if __name__ == "__main__":
    unittest.main()
