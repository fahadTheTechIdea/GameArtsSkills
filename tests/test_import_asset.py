"""Adopting art the owner already has (plan P13.6): a supplied sheet becomes a measured, registered asset, and optionally the game's style anchor."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import gamearts_testkit  # noqa: F401  (puts scripts/ on sys.path)
from gamearts_testkit import write_settings

import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_import_asset as importer  # noqa: E402
from test_lifecycle_operations import GameFolder, OUT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_asset_lifecycle.py"
KEY = (255, 0, 255, 255)
REF = "owner said: this is my art and it is approved as the reference"


def cell_art(index, size=16):
    """A 6x6 block of a colour of its own, placed differently in each cell."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x, y = 2 + 3 * (index % 3), 2 + 2 * (index // 2)
    for yy in range(y, y + 6):
        for xx in range(x, x + 6):
            image.putpixel((xx, yy), (40 + 50 * index, 90, 200 - 30 * index, 255))
    return image


def write_sheet(path, cells=4, columns=2, alpha=True, size=16):
    rows = -(-cells // columns)
    sheet = Image.new("RGBA", (columns * size, rows * size), (0, 0, 0, 0) if alpha else KEY)
    for index in range(cells):
        art = cell_art(index, size)
        if not alpha:
            flat = Image.new("RGBA", art.size, KEY)
            flat.alpha_composite(art)
            art = flat
        sheet.paste(art, ((index % columns) * size, (index // columns) * size))
    sheet.save(path)
    return path


class AdoptCase(GameFolder):
    def setUp(self):
        super().setUp()
        self.supplied = self.root / "supplied"
        self.supplied.mkdir()
        self.sheet = write_sheet(self.supplied / "hero.png")
        self.before = common.sha256_file(self.sheet)

    def adopt(self, asset_id="hero", revision="v001", **kwargs):
        options = dict(layout={"grid": (2, 2)}, rights="owned", rights_notes="I drew this", approval_reference=REF)
        options.update(kwargs)
        return importer.import_asset(self.root, self.sheet, asset_id, revision, **options)

    def atlas(self, name="hero_v001"):
        return common.read_json(next((self.root / OUT / "assets/generated" / name).glob("*.atlas.json")))

    def records(self, kind):
        return self.manifest(kind)


class GridTests(AdoptCase):
    def test_a_stated_grid_becomes_a_registered_generated_asset_with_a_measured_atlas(self):
        result = self.adopt()
        self.assertEqual((result["asset"]["status"], result["asset"]["technical_validation"]), ("generated", "passed"))
        self.assertEqual(len(self.atlas()["frames"]), 4)
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")
        self.assertEqual(life.reconcile_mockups(self.root)["status"], "consistent")

    def test_each_frame_is_the_matching_cell_of_the_supplied_sheet_with_transparency_turned_into_the_key(self):
        self.adopt()
        folder = self.root / OUT / "assets/generated" / "hero_v001"
        atlas, source = self.atlas(), Image.open(self.sheet).convert("RGBA")
        sheet = Image.open(next(folder.glob("*.png"))).convert("RGBA")
        for frame in atlas["frames"]:
            x, y, w, h = frame["rect"]
            kept = sheet.crop((x + frame["source_offset_in_cell"][0], y + frame["source_offset_in_cell"][1],
                               x + frame["source_offset_in_cell"][0] + 16, y + frame["source_offset_in_cell"][1] + 16))
            cell_x, cell_y = (frame["index"] % 2) * 16, (frame["index"] // 2) * 16
            original = source.crop((cell_x, cell_y, cell_x + 16, cell_y + 16))
            expected = Image.new("RGBA", (16, 16), KEY)
            expected.paste(original, mask=original.getchannel("A").point(lambda v: 255 if v else 0))
            self.assertEqual(kept.tobytes(), expected.tobytes(), frame["name"])

    def test_a_cell_size_gives_the_same_frames_as_the_matching_grid(self):
        self.adopt(layout={"cell": (16, 16)})
        self.assertEqual([f["name"] for f in self.atlas()["frames"]], [f"hero_{i:03d}" for i in range(4)])

    def test_the_original_file_is_never_changed(self):
        self.adopt()
        self.assertEqual(common.sha256_file(self.sheet), self.before)

    def test_a_sheet_that_does_not_divide_into_the_stated_grid_is_refused_with_its_size(self):
        with self.assertRaisesRegex(ValueError, "32 x 32.*3 columns"):
            self.adopt(layout={"grid": (3, 2)})
        self.assertEqual(self.records("assets") if (self.root / OUT / "manifests/assets.json").exists() else [], [])

    def test_a_cell_size_that_does_not_divide_the_sheet_is_refused_with_its_size(self):
        with self.assertRaisesRegex(ValueError, "32 x 32.*cells of 15 x 16"):
            self.adopt(layout={"cell": (15, 16)})

    def test_a_blank_cell_is_kept_as_a_blank_frame_and_counted(self):
        sheet = Image.open(self.sheet).convert("RGBA")
        sheet.paste(Image.new("RGBA", (16, 16), (0, 0, 0, 0)), (16, 16))
        sheet.save(self.sheet)
        result = self.adopt()
        self.assertEqual(result["blank_frames"], 1)
        self.assertIsNone(self.atlas()["frames"][3]["source_ink_bounds"])

    def test_durations_and_the_pivot_can_be_stated(self):
        self.adopt(duration_ms=90, pivot=(8, 15))
        frames = self.atlas()["frames"]
        self.assertEqual({f["duration_ms"] for f in frames}, {90})
        self.assertEqual({tuple(f["source_offset_in_cell"]) for f in frames}, {(frames[0]["pivot"][0] - 8, frames[0]["pivot"][1] - 15)})

    def test_a_stated_pivot_that_is_not_the_default_is_the_pivot_of_every_frame(self):
        self.adopt(pivot=(3, 5))
        for frame in self.atlas()["frames"]:
            self.assertEqual([frame["pivot"][0] - frame["source_offset_in_cell"][0], frame["pivot"][1] - frame["source_offset_in_cell"][1]], [3, 5])

    def test_the_default_pivot_is_the_bottom_centre_of_each_frame(self):
        self.adopt()
        frame = self.atlas()["frames"][0]
        self.assertEqual([frame["pivot"][0] - frame["source_offset_in_cell"][0], frame["pivot"][1] - frame["source_offset_in_cell"][1]], [8, 15])


class AlphaTests(AdoptCase):
    def soften(self, alpha=100):
        sheet = Image.open(self.sheet).convert("RGBA")
        sheet.putpixel((3, 3), (40, 90, 200, alpha))  # one pixel of a block is partly transparent
        sheet.putpixel((4, 3), (40, 90, 200, 200))
        sheet.save(self.sheet)

    def test_soft_edges_are_refused_with_the_count_and_the_choice(self):
        self.soften()
        with self.assertRaisesRegex(ValueError, "2 pixel.*partly transparent.*alpha threshold"):
            self.adopt()
        self.assertFalse((self.root / OUT / "assets/generated").exists() and any((self.root / OUT / "assets/generated").iterdir()))

    def test_a_threshold_turns_each_soft_pixel_into_art_or_empty_and_is_recorded(self):
        self.soften(100)
        result = self.adopt(alpha_threshold=128)
        self.assertEqual(result["alpha"], {"transparent_pixels_keyed": 4 * 16 * 16 - 4 * 36, "soft_pixels_made_art": 1, "soft_pixels_made_empty": 1, "alpha_threshold": 128})
        record = [r for r in self.records("assets") if r["asset_id"] == "hero"][0]
        self.assertIn("128", json.dumps(record["provenance"]))

    def test_the_threshold_decides_each_soft_pixel_in_the_picture_that_is_kept(self):
        self.soften(100)
        self.adopt(alpha_threshold=128)
        folder = self.root / OUT / "assets/generated" / "hero_v001"
        sheet = Image.open(next(folder.glob("*.png"))).convert("RGBA")
        frame = self.atlas()["frames"][0]
        ox, oy = frame["rect"][0] + frame["source_offset_in_cell"][0], frame["rect"][1] + frame["source_offset_in_cell"][1]
        self.assertEqual(sheet.getpixel((ox + 3, oy + 3)), KEY)  # alpha 100 is below 128: empty
        self.assertEqual(sheet.getpixel((ox + 4, oy + 3)), (40, 90, 200, 255))  # alpha 200 is above it: art, with its colour

    def test_a_sheet_that_already_uses_the_key_colour_needs_no_conversion(self):
        write_sheet(self.sheet, alpha=False)
        result = self.adopt()
        self.assertEqual(result["alpha"], {"transparent_pixels_keyed": 0, "soft_pixels_made_art": 0, "soft_pixels_made_empty": 0, "alpha_threshold": None})

    def test_a_threshold_outside_one_to_255_is_refused(self):
        for bad in (0, 256, -1):
            with self.subTest(bad), self.assertRaisesRegex(ValueError, "threshold"):
                self.adopt(alpha_threshold=bad)


class StyleCheckTests(AdoptCase):
    def test_art_that_breaks_the_games_own_style_checks_is_registered_but_reported_as_not_ok(self):
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_mid"})
        sheet = Image.open(self.sheet).convert("RGBA")
        for i in range(36):  # far more colours than the preset allows, all inside the first block
            sheet.putpixel((2 + i % 6, 2 + i // 6), (i * 7, 255 - i * 7, (i * 13) % 256, 255))
        for i in range(36, 300):
            sheet.putpixel((20 + i % 12, 2 + i // 12), (i % 256, (i * 3) % 256, (i * 5) % 256, 255))
        sheet.save(self.sheet)
        result = self.adopt()
        self.assertEqual(result["asset"]["technical_validation"], "failed")
        self.assertFalse(result["ok"])
        self.assertIn("mechanical checks failed", life.next_step_for("import-asset", result))
        self.assertEqual([r for r in self.records("assets") if r["asset_id"] == "hero"][0]["status"], "generated")


class DataFileTests(AdoptCase):
    def frames(self, trimmed=False):
        entries = []
        for index in range(4):
            x, y = (index % 2) * 16, (index // 2) * 16
            entry = {"filename": f"walk {index}", "frame": {"x": x, "y": y, "w": 16, "h": 16}, "rotated": False, "trimmed": False,
                     "spriteSourceSize": {"x": 0, "y": 0, "w": 16, "h": 16}, "sourceSize": {"w": 16, "h": 16}, "duration": 80 + 20 * index}
            entries.append(entry)
        return entries

    def write_data(self, frames=None, tags=None, hash_form=False):
        frames = frames or self.frames()
        body = {"frames": {f["filename"]: {k: v for k, v in f.items() if k != "filename"} for f in frames} if hash_form else frames,
                "meta": {"app": "x", "image": "hero.png", "size": {"w": 32, "h": 32}, "scale": "1"}}
        if tags is not None:
            body["meta"]["frameTags"] = tags
        path = self.supplied / "hero.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        return path

    def test_an_array_data_file_gives_the_frames_their_times_and_the_tags(self):
        data = self.write_data(tags=[{"name": "walk", "from": 0, "to": 3, "direction": "pingpong", "repeat": "2"}])
        self.adopt(layout={"data": data})
        atlas = self.atlas()
        self.assertEqual([f["duration_ms"] for f in atlas["frames"]], [80, 100, 120, 140])
        self.assertEqual(atlas["tags"], [{"name": "walk", "from": 0, "to": 3, "direction": "pingpong", "repeat": 2}])

    def test_a_hash_data_file_gives_the_same_result(self):
        data = self.write_data(hash_form=True, tags=[{"name": "walk", "from": 0, "to": 3, "direction": "forward"}])
        self.adopt(layout={"data": data})
        self.assertEqual([f["name"] for f in self.atlas()["frames"]], ["walk 0", "walk 1", "walk 2", "walk 3"])

    def test_a_trimmed_frame_is_put_back_on_a_canvas_of_its_source_size(self):
        frames = self.frames()
        frames[0].update(trimmed=True, frame={"x": 2, "y": 2, "w": 10, "h": 10}, spriteSourceSize={"x": 3, "y": 4, "w": 10, "h": 10}, sourceSize={"w": 16, "h": 16})
        self.adopt(layout={"data": self.write_data(frames)})
        first = self.atlas()["frames"][0]
        self.assertEqual(first["source_size"], [16, 16])

    def test_a_rotated_frame_is_refused(self):
        frames = self.frames()
        frames[1]["rotated"] = True
        with self.assertRaisesRegex(ValueError, "rotated"):
            self.adopt(layout={"data": self.write_data(frames)})

    def test_a_frame_outside_the_sheet_is_refused(self):
        frames = self.frames()
        frames[2]["frame"] = {"x": 30, "y": 0, "w": 16, "h": 16}
        with self.assertRaisesRegex(ValueError, "outside the sheet"):
            self.adopt(layout={"data": self.write_data(frames)})

    def test_names_that_repeat_are_refused(self):
        frames = self.frames()
        frames[1]["filename"] = frames[0]["filename"]
        with self.assertRaisesRegex(ValueError, "more than once"):
            self.adopt(layout={"data": self.write_data(frames)})

    def test_a_tag_that_names_a_frame_that_does_not_exist_is_refused_with_the_atlas_rule(self):
        with self.assertRaisesRegex(ValueError, "frame 9"):
            self.adopt(layout={"data": self.write_data(tags=[{"name": "walk", "from": 0, "to": 9, "direction": "forward"}])})

    def test_a_data_file_that_is_not_json_or_has_no_frames_is_refused(self):
        bad = self.supplied / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "data file"):
            self.adopt(layout={"data": bad})
        bad.write_text(json.dumps({"meta": {}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no frames"):
            self.adopt(layout={"data": bad})


class RecordTests(AdoptCase):
    def test_the_picture_is_imported_as_an_approved_reference_on_the_owners_words(self):
        result = self.adopt()
        mockup = [m for m in self.records("mockups") if m["mockup_id"] == "hero-supplied"][0]
        self.assertEqual((mockup["status"], mockup["scope"], mockup["approval_reference"]), ("approved", "asset", REF))
        self.assertEqual(result["mockup"]["mockup_id"], "hero-supplied")
        self.assertEqual(mockup["rights"], {"status": "owned", "notes": "I drew this"})

    def test_the_asset_records_where_it_came_from_and_the_owners_rights(self):
        self.adopt()
        record = [r for r in self.records("assets") if r["asset_id"] == "hero"][0]
        self.assertEqual(record["provenance"]["provider"], "supplied by the user")
        self.assertEqual(record["rights"], {"status": "owned", "notes": "I drew this"})
        self.assertEqual(record["source_mockups"][0]["mockup_id"], "hero-supplied")
        self.assertEqual(record["status"], "generated")  # the production asset still needs its own approval
        self.assertEqual(record["approval"], "pending")

    def test_the_asset_can_then_go_through_the_ordinary_approval(self):
        self.adopt()
        life.approve_asset(self.root, "hero", "owner approved the sheet")
        self.assertEqual(life.audit_asset(self.root, "hero"), [])

    def test_a_missing_approval_reference_is_refused_before_anything_is_written(self):
        with self.assertRaisesRegex(ValueError, "approval"):
            self.adopt(approval_reference="  ")
        self.assertFalse((self.root / OUT / "manifests").exists() and any((self.root / OUT / "manifests").glob("*.json")))

    def test_rights_must_be_one_of_the_known_values(self):
        with self.assertRaisesRegex(ValueError, "^rights must be owned, licensed, user_supplied or unknown$"):
            self.adopt(rights="found on the internet")

    def test_an_unknown_rights_value_is_refused_before_anything_is_written(self):
        with self.assertRaises(ValueError):
            self.adopt(rights="found on the internet")
        self.assertFalse((self.root / OUT / "manifests").exists() and any((self.root / OUT / "manifests").glob("*.json")))
        self.assertFalse((self.root / OUT / "assets/generated").exists() and any((self.root / OUT / "assets/generated").iterdir()))

    def test_an_id_that_is_already_used_is_refused_before_anything_is_written(self):
        self.adopt()
        with self.assertRaisesRegex(ValueError, "already"):
            self.adopt()
        self.assertEqual(len([m for m in self.records("mockups") if m["mockup_id"] == "hero-supplied"]), 1)

    def test_settings_that_are_not_confirmed_stop_the_import_before_it_writes(self):
        write_settings(self.root, drop=("confirmed_by",), settings_status="inferred")
        with self.assertRaises(ValueError):
            self.adopt()
        self.assertFalse((self.root / OUT / "assets/generated").exists() and any((self.root / OUT / "assets/generated").iterdir()))

    def test_a_failure_while_registering_removes_the_new_bundle_and_says_the_reference_stays(self):
        with mock.patch.object(life, "register_asset", side_effect=ValueError("the manifest is locked")):
            with self.assertRaisesRegex(ValueError, "the manifest is locked.*hero-supplied.*stays"):
                self.adopt()
        generated = self.root / OUT / "assets/generated"
        self.assertEqual(list(generated.iterdir()) if generated.exists() else [], [])
        self.assertTrue(any(m["mockup_id"] == "hero-supplied" for m in self.records("mockups")))


class AnchorAndPaletteTests(AdoptCase):
    def test_the_art_can_be_offered_as_the_style_anchor_without_saving_it(self):
        before = (self.root / ".gamearts" / "project.json").read_bytes()
        result = self.adopt(anchor=True)
        offer = result["anchor_offer"]
        self.assertEqual((offer["mockup_id"], offer["revision"], offer["scope"]), ("hero-style", "v001", "style"))
        style = [m for m in self.records("mockups") if m["mockup_id"] == "hero-style"][0]
        self.assertEqual((style["status"], style["scope"]), ("approved", "style"))
        self.assertIn("art_style.anchor", offer["next_step"])
        self.assertEqual((self.root / ".gamearts" / "project.json").read_bytes(), before)  # the owner confirms a change to the look; it is not made here

    def test_art_outside_the_games_palette_is_reported_at_import(self):
        self.assertNotIn("palette_check", self.adopt())  # no palette chosen: nothing to compare with
        self.adopt(asset_id="hero2", palette_name="mine")
        settings = common.read_json(self.root / ".gamearts" / "project.json")
        settings["art_style"]["palette_reference"] = ".gamearts/palette/mine.palette.json"
        (self.root / ".gamearts" / "project.json").write_text(json.dumps(settings), encoding="utf-8")
        self.assertEqual(self.adopt(asset_id="hero3")["palette_check"]["status"], "passed")
        palette_file = self.root / ".gamearts" / "palette" / "mine.palette.json"
        data = common.read_json(palette_file)
        data["colours"] = data["colours"][1:]
        palette_file.write_text(json.dumps(data), encoding="utf-8")
        check = self.adopt(asset_id="hero4")["palette_check"]
        self.assertEqual(check["status"], "failed")
        self.assertGreater(check["off_palette_pixels"], 0)

    def test_no_anchor_is_offered_unless_asked_for(self):
        self.assertNotIn("anchor_offer", self.adopt())
        self.assertFalse(any(m["mockup_id"] == "hero-style" for m in self.records("mockups")))

    def test_a_palette_can_be_taken_from_the_art(self):
        result = self.adopt(palette_name="hero")
        self.assertEqual(result["palette"]["palette_reference"], ".gamearts/palette/hero.palette.json")
        self.assertTrue((self.root / ".gamearts" / "palette" / "hero.palette.json").is_file())
        self.assertIn("art_style.palette_reference", result["palette"]["next_step"])
        palette = common.read_json(self.root / ".gamearts" / "palette" / "hero.palette.json")
        self.assertNotIn("#FF00FF", json.dumps(palette).upper())  # the key colour is never part of a palette


class CommandTests(AdoptCase):
    def run_op(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "import-asset", "--game-root", str(self.root), *args], capture_output=True, text=True)

    def test_the_command_imports_and_names_the_next_step(self):
        done = self.run_op("--source", str(self.sheet), "--id", "hero", "--revision", "v001", "--grid", "2x2", "--rights", "owned", "--rights-notes", "I drew this",
                           "--user-approval-ref", REF, "--anchor", "--extract-palette", "hero")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["asset"]["technical_validation"], "passed")
        self.assertIn("anchor_offer", result)
        self.assertIn("approve", result["next_step"].lower())
        self.assertTrue(result["report"]["updated"])

    def test_a_data_file_and_a_cell_size_are_accepted_on_the_command_line(self):
        done = self.run_op("--source", str(self.sheet), "--id", "hero", "--revision", "v001", "--cell", "16x16", "--user-approval-ref", REF)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_exactly_one_way_to_say_how_the_sheet_is_laid_out_is_required(self):
        done = self.run_op("--source", str(self.sheet), "--id", "hero", "--revision", "v001", "--user-approval-ref", REF)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("grid", done.stderr)

    def test_a_refusal_says_why_and_exits_one(self):
        done = self.run_op("--source", str(self.sheet), "--id", "hero", "--revision", "v001", "--grid", "3x2", "--user-approval-ref", REF)
        self.assertEqual(done.returncode, 1)
        self.assertIn("BLOCKED", done.stderr)


if __name__ == "__main__":
    unittest.main()
