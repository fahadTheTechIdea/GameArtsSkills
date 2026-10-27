"""Placing repeated objects (plan P16): a guaranteed minimum distance, the same positions for the same seed, and only where the owner said."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)

import gamearts_common as common  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402
import gamearts_placement as placement  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gamearts_placement.py"
TERRAINS = [{"id": "water", "symbol": "~", "colours": ["#3C6EBE"], "priority": 0, "walkable": False},
            {"id": "sand", "symbol": ".", "colours": ["#DECD96"], "priority": 1, "walkable": True},
            {"id": "grass", "symbol": "g", "colours": ["#60AA50"], "priority": 2, "walkable": True}]
ROWS = ["~~~~~~~~~~", "~~....gggg", "~~....gggg", "~~....gggg", "~~....gggg", "~~~~~~~~~~"]


def data(objects=()):
    return {"schema_version": "1.0", "name": "m", "grid": {"width": 10, "height": 6, "cell_px": [16, 16]}, "terrains": TERRAINS, "labels": ROWS,
            "layers": layered.layers_for(TERRAINS, list(objects)), "objects": list(objects)}


def gap(points):
    return min(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for i, a in enumerate(points) for b in points[i + 1:])


class SamplerTests(unittest.TestCase):
    def test_every_pair_of_points_is_at_least_the_radius_apart_and_inside_the_area(self):
        points = placement.poisson_disk(400, 300, 24, seed=1)
        self.assertGreater(len(points), 80)
        self.assertGreaterEqual(gap(points), 24)
        self.assertTrue(all(0 <= x < 400 and 0 <= y < 300 for x, y in points))

    def test_the_same_seed_gives_the_same_points_and_another_seed_gives_others(self):
        first = placement.poisson_disk(200, 200, 20, seed=5)
        self.assertEqual(first, placement.poisson_disk(200, 200, 20, seed=5))
        self.assertNotEqual(first, placement.poisson_disk(200, 200, 20, seed=6))

    def test_points_are_only_where_accepted_and_nowhere_accepted_gives_none(self):
        left = placement.poisson_disk(200, 200, 20, seed=2, accept=lambda x, y: x < 100)
        self.assertTrue(left and all(x < 100 for x, _ in left))
        self.assertEqual(placement.poisson_disk(200, 200, 20, seed=2, accept=lambda x, y: False), [])

    def test_a_radius_or_area_that_is_not_positive_is_refused(self):
        for arguments in ((100, 100, 0), (100, 100, -5), (0, 100, 10)):
            with self.subTest(arguments), self.assertRaisesRegex(ValueError, "positive"):
                placement.poisson_disk(*arguments, seed=1)

    def test_it_beats_uniform_random_on_spacing(self):
        import random
        rng = random.Random(1)
        uniform = [(rng.uniform(0, 400), rng.uniform(0, 300)) for _ in range(120)]
        self.assertLess(gap(uniform), 24)  # uniform points land on top of each other
        self.assertGreaterEqual(gap(placement.poisson_disk(400, 300, 24, seed=1)), 24)


class ScatterTests(unittest.TestCase):
    def test_objects_stand_only_on_the_named_terrains(self):
        positions = placement.scatter(data(), ["grass"], 20, "a")
        self.assertTrue(positions)
        labels = layered.labels_of(data())
        self.assertTrue(all(labels[y // 16][x // 16] == 2 for x, y in positions))

    def test_the_same_seed_places_the_same_objects(self):
        self.assertEqual(placement.scatter(data(), ["sand", "grass"], 20, "seed-a", density={"grass": 0.5}),
                         placement.scatter(data(), ["sand", "grass"], 20, "seed-a", density={"grass": 0.5}))
        self.assertNotEqual(placement.scatter(data(), ["grass"], 20, "seed-a"), placement.scatter(data(), ["grass"], 20, "seed-b"))

    def test_the_density_thins_a_terrain_without_moving_the_others(self):
        full = placement.scatter(data(), ["sand", "grass"], 20, "a")
        thin = placement.scatter(data(), ["sand", "grass"], 20, "a", density={"grass": 0.0})
        labels = layered.labels_of(data())
        self.assertFalse(any(labels[y // 16][x // 16] == 2 for x, y in thin))
        self.assertEqual([p for p in full if labels[p[1] // 16][p[0] // 16] == 1], thin)

    def test_it_keeps_clear_of_the_objects_already_on_the_map(self):
        existing = [{"id": "r", "class": "prop", "sprite": {"atlas": "a", "frame": "f"}, "position_px": [120, 40]}]
        positions = placement.scatter(data(existing), ["grass"], 30, "a")
        self.assertTrue(all((x - 120) ** 2 + (y - 40) ** 2 >= 30 ** 2 for x, y in positions))

    def test_an_unknown_terrain_is_named(self):
        with self.assertRaisesRegex(ValueError, "no terrain 'lava'"):
            placement.scatter(data(), ["lava"], 20, "a")
        with self.assertRaisesRegex(ValueError, "no terrain 'lava'"):
            placement.scatter(data(), ["sand"], 20, "a", density={"lava": 0.5})


class CommandTests(unittest.TestCase):
    def test_the_command_writes_objects_the_map_accepts_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            kit.make_sheet(folder, "rocks", "rocks")
            map_path = folder / "m.layered_map.json"
            body = data()
            body["source"] = {"image": "x.png", "image_sha256": "0" * 64, "read": {"method": "nearest_palette_colour_of_cell_median", "unclassified_cells": [],
                                                                                 "area_opening_minimum": 1, "cells_changed": 0, "occluded_cells": []}}
            body["validation"] = {"geometry": "supplied", "engine_validation": "not_tested"}
            common.atomic_write_json(map_path, body)
            out = folder / "rocks.json"
            run = lambda: subprocess.run([sys.executable, str(SCRIPT), "scatter", "--map", str(map_path), "--on", "grass,sand", "--radius", "40", "--seed", "7", "--atlas",
                                          "rocks.atlas.json", "--frame", "S0", "--footprint", "8x8", "--id-prefix", "rock", "--density", "sand=0.5", "--output", str(out)],
                                         capture_output=True, text=True)  # noqa: E731
            done = run()
            self.assertEqual(done.returncode, 0, done.stderr)
            objects = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(done.stdout)["objects"], len(objects))
            self.assertTrue(objects and all(o["collision"] == "footprint" for o in objects))
            body["objects"] = objects
            body["layers"] = layered.layers_for(body["terrains"], objects)
            common.atomic_write_json(map_path, body)
            self.assertEqual([p for p in layered.validate(map_path) if "overlap" in p or "frame" in p or "atlas" in p], [])
            self.assertEqual(run().returncode, 1)


if __name__ == "__main__":
    unittest.main()
