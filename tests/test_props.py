"""Environment objects cut out of a scene for a layered map (plan P16): regions of a mask become sprites, objects and an atlas; structures and characters are refused."""
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
import gamearts_props as props  # noqa: E402

SCRIPT = ROOT / "scripts" / "gamearts_props.py"
GREEN, BROWN, GREY = (40, 160, 50), (110, 70, 30), (150, 150, 160)


class PropsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        scene = Image.new("RGB", (48, 32), (200, 190, 150))
        scene.paste(GREEN, (4, 2, 14, 12))     # a tree crown
        scene.paste(BROWN, (8, 12, 10, 18))    # its trunk
        scene.paste(GREY, (20, 20, 44, 23))    # a fence run
        scene.paste(BROWN, (30, 4, 34, 8))     # a rock-like prop
        scene.save(self.root / "scene.png")
        self.masks = {}
        for name, boxes in {"trees": [(4, 2, 14, 12), (8, 12, 10, 18)], "fences": [(20, 20, 44, 23)], "rocks": [(30, 4, 34, 8), (40, 4, 41, 5)]}.items():
            mask = Image.new("L", (48, 32), 0)
            for box in boxes:
                mask.paste(255, (box[0], box[1], box[2], box[3]))
            mask.save(self.root / f"{name}.png")
        self.job = {"classes": [{"id": "trees", "kind": "tree", "mask": "trees.png"}, {"id": "fences", "kind": "fence", "mask": "fences.png"},
                                {"id": "rocks", "kind": "rock", "mask": "rocks.png"}], "_input_dir": str(self.root)}
        self.out = self.root / "out"

    def extract(self, **kw):
        return props.extract(self.root / "scene.png", kw.pop("job", self.job), kw.pop("name", "yard"), self.out, **kw)


class ExtractTests(PropsCase):
    def test_each_region_becomes_one_object_with_a_sprite_and_a_bottom_centre_position(self):
        report = self.extract()
        objects = common.read_json(self.out / "yard.objects.json")
        self.assertEqual(report["objects"], 3)  # the one-pixel speck is below the minimum area
        self.assertEqual(report["by_class"]["rocks"]["dropped_below_min_area"], 1)
        tree = next(o for o in objects if o["kind"] == "tree")
        self.assertEqual(tree["position_px"], [9, 17])  # the box 4..14 x 2..18: centre 9, last row 17
        self.assertEqual(tree["class"], "prop")
        atlas = common.read_json(self.out / "yard.props.atlas.json")
        frame = next(f for f in atlas["frames"] if f["name"] == tree["id"])
        self.assertEqual(frame["pivot"], [2 + 5, 2 + 15])  # the cell has two pixels of padding, and the pivot is the sprite's bottom centre inside it

    def test_the_sprite_keeps_the_scene_pixels_of_its_region_and_the_key_colour_elsewhere(self):
        self.extract()
        atlas = common.read_json(self.out / "yard.props.atlas.json")
        sheet = Image.open(self.out / "yard.props.atlas.png").convert("RGBA")
        fence = next(f for f in atlas["frames"] if f["name"].startswith("fences"))
        x, y, w, h = fence["rect"]
        self.assertEqual(sheet.getpixel((x + 2 + 2, y + 2 + 1))[:3], GREY)  # two pixels of padding
        tree = next(f for f in atlas["frames"] if f["name"].startswith("trees"))
        tx, ty, tw, th = tree["rect"]
        self.assertEqual(sheet.getpixel((tx + 2, ty + 2 + 15)), (255, 0, 255, 255))  # beside the trunk, below the crown: not part of the region

    def test_a_footprint_follows_the_kind_a_tree_on_its_trunk_a_fence_along_its_length(self):
        self.extract()
        by_kind = {o["kind"]: o for o in common.read_json(self.out / "yard.objects.json")}
        self.assertLess(by_kind["tree"]["footprint_px"][0], 10)
        self.assertEqual(by_kind["fence"]["footprint_px"][0], 24)
        self.assertTrue(by_kind["fence"]["allow_overlap"])
        self.assertNotIn("allow_overlap", by_kind["tree"])

    def test_the_union_of_the_masks_is_written_for_the_ground_read(self):
        self.extract()
        union = Image.open(self.out / "yard.occlusion.png")
        self.assertEqual(union.size, (48, 32))
        self.assertEqual(union.getpixel((5, 5)), 255)
        self.assertEqual(union.getpixel((25, 21)), 255)
        self.assertEqual(union.getpixel((0, 0)), 0)

    def test_nothing_is_overwritten_and_a_refusal_writes_nothing(self):
        self.extract()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.extract()
        bad = dict(self.job, classes=self.job["classes"] + [{"id": "house", "kind": "building", "mask": "trees.png"}])
        with self.assertRaisesRegex(ValueError, "structures"):
            self.extract(job=bad, name="other")
        self.assertFalse((self.out / "other.objects.json").exists())

    def test_structures_characters_and_ground_are_refused_by_kind_with_the_reason(self):
        for kind, owner in (("building", "structures"), ("wall", "structures"), ("character", "characters"), ("person", "characters"), ("ground", "the terrain layers")):
            with self.subTest(kind=kind):
                job = dict(self.job, classes=[{"id": "x", "kind": kind, "mask": "trees.png"}])
                with self.assertRaisesRegex(ValueError, f"belongs to {owner}"):
                    self.extract(job=job, name="n" + kind)

    def test_an_unknown_kind_a_wrong_sized_mask_and_empty_masks_are_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown kind"):
            self.extract(job=dict(self.job, classes=[{"id": "x", "kind": "spaceship", "mask": "trees.png"}]), name="a")
        Image.new("L", (10, 10)).save(self.root / "small.png")
        with self.assertRaisesRegex(ValueError, "must be the same size"):
            self.extract(job=dict(self.job, classes=[{"id": "x", "kind": "tree", "mask": "small.png"}]), name="b")
        Image.new("L", (48, 32)).save(self.root / "empty.png")
        with self.assertRaisesRegex(ValueError, "no object was found"):
            self.extract(job=dict(self.job, classes=[{"id": "x", "kind": "tree", "mask": "empty.png"}]), name="c")

    def test_repeated_class_ids_and_an_unsafe_name_are_refused(self):
        twice = dict(self.job, classes=[self.job["classes"][0], self.job["classes"][0]])
        with self.assertRaisesRegex(ValueError, "class ids repeat"):
            self.extract(job=twice, name="dup")
        with self.assertRaisesRegex(ValueError, "letters, digits"):
            self.extract(name="../escape")

    def test_touching_regions_are_one_object_and_diagonal_contact_joins_them(self):
        mask = Image.new("L", (48, 32), 0)
        mask.paste(255, (2, 2, 6, 6))
        mask.paste(255, (6, 6, 10, 10))  # touches the first only at a corner
        mask.save(self.root / "pair.png")
        regions, dropped = props.components(mask, 1)
        self.assertEqual((len(regions), dropped), (1, 0))
        self.assertEqual(regions[0][0], (2, 2, 10, 10))

    def test_the_objects_feed_a_layered_map_whose_validation_finds_the_atlas_frames(self):
        self.extract()
        terrains = [{"id": "ground", "symbol": ".", "colours": ["#C8BE96"], "priority": 0, "walkable": True}]
        path, data = layered.build(self.root / "scene.png", terrains, (8, 8), "yard", self.out, objects=common.read_json(self.out / "yard.objects.json"),
                                   occlusion_mask=self.out / "yard.occlusion.png")
        self.assertEqual(len(data["objects"]), 3)
        self.assertEqual(layered.validate(path), [])
        grid = layered.gameplay_grid(data)
        self.assertIn("#", "".join(grid))  # the tree's trunk footprint and the fence block walking
        hidden = {tuple(c) for c in data["source"]["read"]["occluded_cells"]}
        self.assertIn((1, 1), hidden)  # the tree's cells are hidden from the ground read, then filled

    def test_the_command_runs_and_reports_what_it_did_not_assess(self):
        (self.root / "job.json").write_text(json.dumps({"classes": self.job["classes"]}), encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "extract", "--image", str(self.root / "scene.png"), "--job", str(self.root / "job.json"), "--name", "viacli",
                               "--output-dir", str(self.out)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(report["objects"], 3)
        self.assertTrue(any("engine" in item for item in report["not_assessed"]))


if __name__ == "__main__":
    unittest.main()
