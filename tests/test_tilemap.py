"""One command from a scene to a complete tilemap: surface plus environment objects (plan P16). A tiny invented scene, no game's art."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from PIL import Image  # noqa: E402

import gamearts_common as common  # noqa: E402
import gamearts_layered_map as layered  # noqa: E402
import gamearts_tilemap as tilemap  # noqa: E402

SCRIPT = ROOT / "scripts" / "gamearts_tilemap.py"
SAND, GRASS, LEAF, TRUNK, WALL = (222, 205, 150), (96, 170, 80), (20, 110, 30), (110, 70, 30), (170, 60, 60)
TERRAINS = [{"id": "sand", "symbol": ".", "colours": ["#DECD96"], "priority": 0, "walkable": True},
            {"id": "grass", "symbol": "g", "colours": ["#60AA50"], "priority": 1, "walkable": True}]


class TilemapCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scene = Image.new("RGB", (64, 48), SAND)
        scene.paste(GRASS, (32, 0, 64, 48))
        scene.paste(LEAF, (36, 8, 52, 24))     # a tree crown on the grass
        scene.paste(TRUNK, (42, 24, 46, 32))   # its trunk
        scene.paste(WALL, (4, 4, 20, 20))      # a building on the sand
        scene.save(self.root / "scene.png")
        for name, boxes in {"trees": [(36, 8, 52, 24), (42, 24, 46, 32)], "solid": [(4, 4, 20, 20)]}.items():
            mask = Image.new("L", (64, 48), 0)
            for box in boxes:
                mask.paste(255, box)
            mask.save(self.root / f"{name}.png")
        self.job = {"cell": [8, 8], "terrains": TERRAINS, "solid_mask": "solid.png", "environment": {"classes": [{"id": "trees", "kind": "tree", "mask": "trees.png"}]},
                    "_input_dir": str(self.root)}
        self.out = self.root / "out"

    def build(self, job=None, name="yard", **kw):
        return tilemap.build(self.root / "scene.png", job or self.job, name, self.out, **kw)


class BuildTests(TilemapCase):
    def test_the_surface_the_environment_and_the_plan_come_from_one_call(self):
        report = self.build()
        self.assertEqual(report["grid"], [8, 6])
        self.assertEqual(report["objects"], 1)
        self.assertEqual(report["surface"]["solid_cells"], 5)  # the building covers half or more of a plus-shaped five cells
        self.assertGreater(report["surface"]["occluded_cells"], 4)  # the tree's cells and the building's cells are hidden from the ground read
        self.assertEqual(report["tilesets_still_to_make"], ["sand", "grass"])  # neither terrain names a tileset yet
        for name in ("yard.layered_map.json", "yard.objects.json", "yard.props.atlas.json", "yard.props.atlas.png", "yard.occlusion.png"):
            self.assertTrue((self.out / name).is_file(), name)
        self.assertTrue((self.out / "yard.swatches").is_dir())
        self.assertTrue((self.out / "yard.jobs").is_dir())
        self.assertEqual(layered.validate(self.out / "yard.layered_map.json"), [])

    def test_the_tiled_map_is_refused_before_anything_is_written_while_a_terrain_has_no_tileset(self):
        with self.assertRaisesRegex(ValueError, "names none"):
            self.build(tiled=True, name="early")
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_the_ground_under_the_tree_is_the_grass_around_it_and_the_building_blocks_walking(self):
        self.build()
        data = common.read_json(self.out / "yard.layered_map.json")
        self.assertEqual(data["labels"][2][5], "g")  # under the crown
        self.assertEqual(data["labels"][1][1], ".")  # under the building: the sand around it
        grid = layered.gameplay_grid(data)
        self.assertEqual(grid[1][1], "#")
        self.assertEqual(grid[5][0], ".")

    def test_a_job_without_an_environment_builds_the_surface_alone(self):
        job = {k: v for k, v in self.job.items() if k != "environment"}
        report = self.build(job)
        self.assertEqual(report["objects"], 0)
        self.assertFalse((self.out / "yard.objects.json").exists())

    def test_a_given_occlusion_mask_and_the_environment_masks_are_both_applied(self):
        extra = Image.new("L", (64, 48), 0)
        extra.paste(255, (0, 40, 8, 48))
        extra.save(self.root / "extra.png")
        job = dict(self.job, occlusion_mask="extra.png")
        self.build(job)
        hidden = {tuple(c) for c in common.read_json(self.out / "yard.layered_map.json")["source"]["read"]["occluded_cells"]}
        self.assertIn((0, 5), hidden)  # from the given mask
        self.assertIn((5, 2), hidden)  # from the tree
        self.assertTrue((self.out / "yard.all.occlusion.png").is_file())

    def test_structures_and_characters_are_refused_as_environment_and_nothing_is_left(self):
        for kind in ("building", "character"):
            job = dict(self.job, environment={"classes": [{"id": "x", "kind": kind, "mask": "trees.png"}]})
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "handled separately"):
                self.build(job, name="no" + kind)
            self.assertEqual([p.name for p in self.out.glob("no" + kind + "*")] if self.out.exists() else [], [])

    def test_a_scene_that_is_not_whole_cells_is_refused(self):
        Image.new("RGB", (65, 48)).save(self.root / "odd.png")
        with self.assertRaisesRegex(ValueError, "whole cells"):
            tilemap.build(self.root / "odd.png", self.job, "odd", self.out)

    def test_a_second_build_of_the_same_name_is_refused_and_changes_nothing(self):
        self.build()
        before = {p.name: p.stat().st_mtime_ns for p in self.out.iterdir() if p.is_file()}
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.build()
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in self.out.iterdir() if p.is_file()}, before)

    def test_an_existing_map_stops_the_build_before_any_environment_file_is_written(self):
        self.out.mkdir()
        (self.out / "yard.layered_map.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "yard.layered_map.json already exists"):
            self.build()
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["yard.layered_map.json"])

    def test_a_job_that_breaks_its_contract_is_refused(self):
        with self.assertRaises(ValueError):
            self.build({"cell": [8], "terrains": TERRAINS})
        with self.assertRaises(ValueError):
            self.build({"cell": [8, 8], "terrains": TERRAINS, "surprise": 1})

    def test_the_command_runs_from_a_job_file(self):
        (self.root / "job.json").write_text(json.dumps({k: v for k, v in self.job.items() if k != "_input_dir"}), encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "build", "--image", str(self.root / "scene.png"), "--job", str(self.root / "job.json"), "--name", "viacli",
                               "--output-dir", str(self.out)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertIsNone(report["tiled_map"])
        self.assertTrue(any("engine" in item for item in report["not_assessed"]))


if __name__ == "__main__":
    unittest.main()
