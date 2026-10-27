"""Exchange export (plan P12.3): the same sheet written in the JSON shapes other tools read (Aseprite-style array and hash, a Tiled tileset)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import gamearts_testkit  # noqa: F401  (puts scripts/ on sys.path)

import build_sheet_atlas as sheets  # noqa: E402
import build_tileset as tilesets  # noqa: E402
import export_exchange as exchange  # noqa: E402
import gamearts_atlas as atlas_rules  # noqa: E402
import gamearts_tileset as tile_rules  # noqa: E402
from test_atlas_depth import BLOCKS, PIVOT, source_frame  # noqa: E402
from test_tileset import ART, SIZE, TERRAINS, flat_art  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_exchange.py"
KEY = (255, 0, 255, 255)


class SheetCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.out = self.root / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, **overrides):
        items = []
        for index, (box, colour) in enumerate(BLOCKS):
            source_frame(box, colour).save(self.src / f"f{index}.png")
            items.append({"file": f"f{index}.png", "name": f"walk_{index}", "direction": "E", "action": "walk", "pivot": list(PIVOT), "duration_ms": 80 + 20 * index})
        job = {"_input_dir": str(self.src), "name": "hero", "asset_id": "hero", "padding": 2, "frames": items}
        job.update(overrides)
        png, atlas = sheets.build(job, self.out)
        return png, atlas

    def export(self, atlas, kind="aseprite-array", **kwargs):
        written = exchange.export_atlas(atlas, kind, **kwargs)
        return json.loads(Path(written).read_text(encoding="utf-8")), Path(written)


class GeometryHelperTests(SheetCase):
    def test_the_picture_rectangle_excludes_the_padding_on_a_grid_sheet(self):
        png, atlas = self.build()
        data = json.loads(atlas.read_text(encoding="utf-8"))
        with Image.open(png) as sheet:
            sheet = sheet.convert("RGBA")
            for index, frame in enumerate(data["frames"]):
                x, y, w, h = atlas_rules.image_rect(frame)
                source = Image.open(self.src / f"f{index}.png").convert("RGBA")
                self.assertEqual((w, h), source.size)
                self.assertEqual(sheet.crop((x, y, x + w, y + h)).tobytes(), source.tobytes(), frame["name"])

    def test_the_picture_rectangle_of_a_trimmed_frame_is_the_kept_part(self):
        png, atlas = self.build(trim=True, pack="shelf")
        data = json.loads(atlas.read_text(encoding="utf-8"))
        with Image.open(png) as sheet:
            sheet = sheet.convert("RGBA")
            for index, frame in enumerate(data["frames"]):
                x, y, w, h = atlas_rules.image_rect(frame)
                kept = frame["trim"]
                source = Image.open(self.src / f"f{index}.png").convert("RGBA").crop((kept[0], kept[1], kept[0] + kept[2], kept[1] + kept[3]))
                self.assertEqual(sheet.crop((x, y, x + w, y + h)).tobytes(), source.tobytes(), frame["name"])

    def test_a_hand_made_atlas_without_source_fields_uses_the_whole_cell(self):
        frame = {"index": 0, "rect": [10, 20, 30, 40], "pivot": [0, 0], "anchors": {}, "duration_ms": 100}
        self.assertEqual(atlas_rules.image_rect(frame), (10, 20, 30, 40))
        self.assertEqual(atlas_rules.source_box(frame), (0, 0, 30, 40))


class AsepriteTests(SheetCase):
    def test_the_array_form_lists_frames_in_order_with_the_documented_fields(self):
        png, atlas = self.build()
        data, _ = self.export(atlas)
        self.assertEqual(set(data), {"frames", "meta"})
        self.assertIsInstance(data["frames"], list)
        self.assertEqual([f["filename"] for f in data["frames"]], [f"walk_{i}" for i in range(4)])
        first = data["frames"][0]
        for key in ("filename", "frame", "rotated", "trimmed", "spriteSourceSize", "sourceSize", "duration"):
            self.assertIn(key, first)
        self.assertEqual(set(first["frame"]), {"x", "y", "w", "h"})
        self.assertFalse(first["rotated"])
        self.assertEqual([f["duration"] for f in data["frames"]], [80, 100, 120, 140])

    def test_the_frame_rectangles_cut_the_source_pictures_back_out_of_the_sheet(self):
        png, atlas = self.build()
        data, _ = self.export(atlas)
        with Image.open(png) as sheet:
            sheet = sheet.convert("RGBA")
            for index, frame in enumerate(data["frames"]):
                r = frame["frame"]
                source = Image.open(self.src / f"f{index}.png").convert("RGBA")
                self.assertEqual(sheet.crop((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])).tobytes(), source.tobytes())

    def test_an_untrimmed_frame_says_so_and_its_source_is_its_own_size(self):
        _, atlas = self.build()
        frame = self.export(atlas)[0]["frames"][0]
        self.assertFalse(frame["trimmed"])
        self.assertEqual(frame["spriteSourceSize"], {"x": 0, "y": 0, "w": 20, "h": 20})
        self.assertEqual(frame["sourceSize"], {"w": 20, "h": 20})

    def test_a_trimmed_frame_says_where_its_kept_part_sat_in_the_source(self):
        _, atlas = self.build(trim=True, pack="shelf")
        data = json.loads(atlas.read_text(encoding="utf-8"))
        frames = self.export(atlas)[0]["frames"]
        for source_entry, shown in zip(data["frames"], frames):
            x, y, w, h = source_entry["trim"]
            self.assertEqual(shown["spriteSourceSize"], {"x": x, "y": y, "w": w, "h": h})
            self.assertEqual(shown["sourceSize"], {"w": 20, "h": 20})
            self.assertEqual(shown["trimmed"], source_entry["trimmed"])
        self.assertTrue(any(f["trimmed"] for f in frames))

    def test_the_hash_form_has_the_same_fields_keyed_by_name(self):
        _, atlas = self.build()
        array = self.export(atlas, "aseprite-array")[0]
        by_name, _ = self.export(atlas, "aseprite-hash")
        self.assertIsInstance(by_name["frames"], dict)
        self.assertEqual(list(by_name["frames"]), [f["filename"] for f in array["frames"]])
        for entry in array["frames"]:
            expected = {key: value for key, value in entry.items() if key != "filename"}
            self.assertEqual(by_name["frames"][entry["filename"]], expected)
        self.assertEqual(by_name["meta"], array["meta"])

    def test_meta_names_the_sheet_its_size_and_the_key_colour(self):
        png, atlas = self.build()
        meta = self.export(atlas)[0]["meta"]
        with Image.open(png) as sheet:
            self.assertEqual(meta["size"], {"w": sheet.width, "h": sheet.height})
        self.assertEqual((meta["image"], meta["format"], meta["scale"], meta["key_colour"]), ("hero.png", "RGBA8888", "1", "#FF00FF"))
        self.assertIn("Game Arts", meta["app"])
        self.assertEqual(meta["version"], "1.0")

    def test_pivots_are_normalised_to_the_source_frame(self):
        _, atlas = self.build(trim=True, pack="shelf")
        for frame in self.export(atlas)[0]["frames"]:
            self.assertEqual(frame["pivot"], {"x": PIVOT[0] / 20, "y": PIVOT[1] / 20})

    def test_tags_become_frame_tags_and_repeat_is_a_string_only_when_above_zero(self):
        tags = [{"name": "walk", "from": 0, "to": 3, "direction": "forward"}, {"name": "hit", "from": 1, "to": 2, "direction": "pingpong_reverse", "repeat": 3}]
        _, atlas = self.build(tags=tags)
        shown = self.export(atlas)[0]["meta"]["frameTags"]
        self.assertEqual(shown[0], {"name": "walk", "from": 0, "to": 3, "direction": "forward"})
        self.assertEqual(shown[1], {"name": "hit", "from": 1, "to": 2, "direction": "pingpong_reverse", "repeat": "3"})

    def test_a_sheet_without_tags_gets_no_frame_tags_rather_than_invented_ones(self):
        _, atlas = self.build()
        self.assertNotIn("frameTags", self.export(atlas)[0]["meta"])

    def test_frames_can_be_named_by_their_frame_number_for_loaders_that_find_a_tags_frames_by_number(self):
        tags = [{"name": "walk", "from": 1, "to": 3, "direction": "forward"}]
        _, atlas = self.build(tags=tags)
        array = self.export(atlas, "aseprite-array", names="index")[0]
        self.assertEqual([f["filename"] for f in array["frames"]], ["0", "1", "2", "3"])
        by_number, _ = self.export(atlas, "aseprite-hash", output=self.root / "numbered.hash.json", names="index")
        self.assertEqual(list(by_number["frames"]), ["0", "1", "2", "3"])
        self.assertEqual(array["meta"]["frameTags"], [{"name": "walk", "from": 1, "to": 3, "direction": "forward"}])
        for tag in array["meta"]["frameTags"]:
            self.assertTrue(all(str(i) in by_number["frames"] for i in range(tag["from"], tag["to"] + 1)))  # every frame a tag names can be found by number

    def test_an_unknown_frame_naming_names_the_choices(self):
        _, atlas = self.build()
        with self.assertRaisesRegex(ValueError, "name or index"):
            exchange.export_atlas(atlas, "aseprite-array", names="letters")

    def test_the_output_sits_beside_the_atlas_by_default_and_is_never_overwritten(self):
        _, atlas = self.build()
        _, written = self.export(atlas)
        self.assertEqual(written, atlas.with_name("hero.array.json"))
        with self.assertRaisesRegex(ValueError, "already exists"):
            exchange.export_atlas(atlas, "aseprite-array")
        _, hash_form = self.export(atlas, "aseprite-hash")
        self.assertEqual(hash_form, atlas.with_name("hero.hash.json"))

    def test_an_explicit_output_path_is_used(self):
        _, atlas = self.build()
        target = self.root / "elsewhere" / "sheet.json"
        _, written = self.export(atlas, output=target)
        self.assertEqual(written, target)

    def test_an_atlas_that_breaks_its_own_contract_is_not_exported(self):
        _, atlas = self.build(tags=[{"name": "walk", "from": 0, "to": 3, "direction": "forward"}])
        data = json.loads(atlas.read_text(encoding="utf-8"))
        data["tags"][0]["to"] = 40
        atlas.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "frame 40"):
            exchange.export_atlas(atlas, "aseprite-array")
        self.assertFalse(atlas.with_name("hero.array.json").exists())

    def test_an_unknown_format_names_the_choices(self):
        _, atlas = self.build()
        with self.assertRaisesRegex(ValueError, "aseprite-array, aseprite-hash"):
            exchange.export_atlas(atlas, "photoshop")


class TiledTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.out = self.root / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, layout="wang_corner_16", art=None, **overrides):
        terrains = TERRAINS[:tile_rules.TERRAIN_COUNT[layout]]
        draw = art or ART.get(layout, flat_art)
        tiles = []
        for index, tile in enumerate(tile_rules.layout_tiles(layout, terrains)):
            draw(tile["neighbours"]).save(self.src / f"t{index:03d}.png")
            item = {"file": f"t{index:03d}.png"}
            if layout not in ("single", "variants"):
                item["neighbours"] = tile["neighbours"]
            tiles.append(item)
        job = {"_input_dir": str(self.src), "name": layout, "tile_size": [SIZE, SIZE], "layout": layout, "terrains": terrains, "tiles": tiles, "columns": 4}
        job.update(overrides)
        self.out = self.root / f"out_{layout}"
        return tilesets.build(job, self.out)

    def export(self, tileset):
        written = exchange.export_tileset(tileset)
        return json.loads(Path(written).read_text(encoding="utf-8")), Path(written)

    def test_a_sheet_wider_than_it_is_tall_keeps_its_width_and_height_apart(self):
        png, _, tileset = self.build(columns=8)
        data, _ = self.export(tileset)
        with Image.open(png) as sheet:
            self.assertGreater(sheet.width, sheet.height)
            self.assertEqual((data["imagewidth"], data["imageheight"]), sheet.size)
        self.assertEqual((data["columns"], data["tilecount"]), (8, 16))

    def test_the_image_grid_fields_describe_the_sheet_exactly(self):
        png, _, tileset = self.build()
        data, written = self.export(tileset)
        with Image.open(png) as sheet:
            self.assertEqual((data["imagewidth"], data["imageheight"]), sheet.size)
        self.assertEqual((data["type"], data["name"], data["image"], data["tilewidth"], data["tileheight"]), ("tileset", "wang_corner_16", "wang_corner_16.png", SIZE, SIZE))
        self.assertEqual((data["tilecount"], data["columns"], data["margin"], data["spacing"]), (16, 4, 0, 0))
        self.assertEqual(written.name, "wang_corner_16.tsj")
        self.assertIsInstance(data["version"], str)
        self.assertIsInstance(data["tiledversion"], str)

    def test_tile_n_sits_where_a_tiled_grid_puts_tile_n(self):
        png, atlas, tileset = self.build()
        data, _ = self.export(tileset)
        with Image.open(png) as sheet:
            sheet = sheet.convert("RGBA")
            for index in range(data["tilecount"]):
                x, y = (index % data["columns"]) * data["tilewidth"], (index // data["columns"]) * data["tileheight"]
                original = Image.open(self.src / f"t{index:03d}.png").convert("RGBA")
                self.assertEqual(sheet.crop((x, y, x + SIZE, y + SIZE)).tobytes(), original.tobytes())

    def test_wang_sets_exist_for_the_layouts_that_have_neighbour_rules(self):
        expected = {"wang_corner_16": ("corner", 16), "dual_grid_16": ("corner", 16), "wang_edge_16": ("edge", 16), "blob_47": ("mixed", 47)}
        for layout, (kind, count) in expected.items():
            with self.subTest(layout):
                _, _, tileset = self.build(layout)
                data, _ = self.export(tileset)
                self.assertEqual(len(data["wangsets"]), 1)
                wangset = data["wangsets"][0]
                self.assertEqual((wangset["type"], len(wangset["wangtiles"])), (kind, count))
                self.assertEqual([c["name"] for c in wangset["colors"]], TERRAINS)
                self.assertTrue(all(len(w["wangid"]) == 8 for w in wangset["wangtiles"]))

    def test_single_and_variant_layouts_have_no_wang_sets(self):
        for layout in ("single", "variants"):
            with self.subTest(layout):
                _, _, tileset = self.build(layout)
                self.assertEqual(self.export(tileset)[0]["wangsets"], [])

    def test_wang_ids_use_the_documented_order_and_colour_indexes(self):
        _, _, tileset = self.build("wang_corner_16")
        data, _ = self.export(tileset)
        meta = json.loads(tileset.read_text(encoding="utf-8"))
        for wangtile in data["wangsets"][0]["wangtiles"]:
            tile = meta["tiles"][wangtile["tileid"]]
            self.assertEqual(wangtile["wangid"], tile_rules.wang_id("wang_corner_16", tile["neighbours"], TERRAINS))
            self.assertEqual([wangtile["wangid"][i] for i in (0, 2, 4, 6)], [0, 0, 0, 0])  # sides are not used by a corner set
        everything = next(w for w in data["wangsets"][0]["wangtiles"] if w["wangid"] == [0, 1, 0, 1, 0, 1, 0, 1])
        self.assertEqual(data["wangsets"][0]["colors"][0]["tile"], everything["tileid"])

    def test_the_representative_tiles_are_the_all_inside_and_all_outside_tiles(self):
        _, _, tileset = self.build("wang_corner_16")
        wangset = self.export(tileset)[0]["wangsets"][0]
        meta = json.loads(tileset.read_text(encoding="utf-8"))
        inside, outside = (meta["tiles"][c["tile"]]["neighbours"] for c in wangset["colors"])
        self.assertEqual(set(inside.values()), {"grass"})
        self.assertEqual(set(outside.values()), {"water"})

    def test_ground_tiles_declare_no_transparent_colour_and_keyed_tiles_declare_the_key(self):
        _, _, tileset = self.build("single")
        self.assertNotIn("transparentcolor", self.export(tileset)[0])

        def keyed(_neighbours=None):
            image = Image.new("RGBA", (SIZE, SIZE), KEY)
            image.putpixel((3, 3), (40, 90, 160, 255))
            return image
        _, _, tileset = self.build("single", art=keyed, full_bleed=False, name="props")
        self.assertEqual(self.export(tileset)[0]["transparentcolor"], "#ff00ff")

    def test_the_layout_and_terrains_travel_as_tileset_properties(self):
        _, _, tileset = self.build("blob_47", columns=8)
        properties = {p["name"]: p for p in self.export(tileset)[0]["properties"]}
        self.assertEqual((properties["layout"]["type"], properties["layout"]["value"]), ("string", "blob_47"))
        self.assertEqual(properties["terrains"]["value"], "grass, water")

    def test_a_tileset_that_fails_its_own_checks_is_not_exported(self):
        _, _, tileset = self.build()
        data = json.loads(tileset.read_text(encoding="utf-8"))
        data["tiles"].pop()
        tileset.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot export"):
            exchange.export_tileset(tileset)
        self.assertFalse(tileset.with_name("wang_corner_16.tsj").exists())

    def test_an_existing_export_is_never_overwritten(self):
        _, _, tileset = self.build()
        self.export(tileset)
        with self.assertRaisesRegex(ValueError, "already exists"):
            exchange.export_tileset(tileset)


class CommandTests(SheetCase):
    def test_the_command_can_name_frames_by_number(self):
        _, atlas = self.build()
        done = subprocess.run([sys.executable, str(SCRIPT), "--atlas", str(atlas), "--format", "aseprite-array", "--frame-names", "index"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        written = json.loads(done.stdout)["written"]
        self.assertEqual(json.loads(Path(written).read_text(encoding="utf-8"))["frames"][2]["filename"], "2")

    def test_the_command_writes_the_export_and_names_the_file(self):
        _, atlas = self.build()
        done = subprocess.run([sys.executable, str(SCRIPT), "--atlas", str(atlas), "--format", "aseprite-hash"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("hero.hash.json", done.stdout)
        self.assertIn("best effort", done.stdout.lower())

    def test_a_refusal_says_why_and_exits_one(self):
        _, atlas = self.build()
        done = subprocess.run([sys.executable, str(SCRIPT), "--atlas", str(atlas), "--format", "photoshop"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)

    def test_exactly_one_of_atlas_or_tileset_is_required(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "--format", "tiled"], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)


if __name__ == "__main__":
    unittest.main()
