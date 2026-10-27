"""Runtime export (plan P12.7): engine-ready copies of delivered sheets, with the delivered art provably recoverable and provably untouched."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)
from gamearts_testkit import write_settings

import build_sheet_atlas as sheets  # noqa: E402
import gamearts_asset_lifecycle as life  # noqa: E402
import build_tileset as tilesets  # noqa: E402
import export_runtime as runtime  # noqa: E402
import gamearts_common as common  # noqa: E402
from test_atlas_depth import BLOCKS, PIVOT, source_frame  # noqa: E402
from test_lifecycle_operations import GameFolder  # noqa: E402
from test_tileset import ART, SIZE, TERRAINS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_runtime.py"
KEY = (255, 0, 255, 255)
OUT = ".gamearts/outputs"


class BundleCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.bundle = self.root / "bundle"
        self.out = self.root / "runtime_out"

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, name="hero", **overrides):
        items = []
        for index, (box, colour) in enumerate(BLOCKS):
            source_frame(box, colour).save(self.src / f"f{index}.png")
            items.append({"file": f"f{index}.png", "name": f"walk_{index}", "direction": "E", "action": "walk", "pivot": list(PIVOT), "duration_ms": 90 + index,
                          "anchors": {"hand": [12, 9]}})
        job = {"_input_dir": str(self.src), "name": name, "asset_id": name, "padding": 2, "frames": items,
               "tags": [{"name": "walk", "from": 0, "to": 3, "direction": "forward"}]}
        job.update(overrides)
        return sheets.build(job, self.bundle)

    def digests(self, folder):
        return {p.name: common.sha256_file(p) for p in sorted(Path(folder).iterdir()) if p.is_file()}


class ImageTests(unittest.TestCase):
    def test_key_pixels_become_transparent_black_and_art_pixels_are_unchanged(self):
        sheet = Image.new("RGBA", (6, 2), KEY)
        sheet.putpixel((1, 0), (10, 200, 30, 255))
        sheet.putpixel((4, 1), (255, 0, 254, 255))  # one step from the key is art, not key
        out = runtime.to_runtime_image(sheet)
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(out.getpixel((1, 0)), (10, 200, 30, 255))
        self.assertEqual(out.getpixel((4, 1)), (255, 0, 254, 255))
        self.assertEqual(sum(1 for y in range(2) for x in range(6) if out.getpixel((x, y))[3] == 0), 10)

    def test_laying_the_result_over_the_key_colour_gives_the_original_back_exactly(self):
        sheet = Image.new("RGBA", (32, 32), KEY)
        for i in range(0, 32, 3):
            sheet.putpixel((i, (i * 7) % 32), (i * 8, 255 - i * 8, (i * 5) % 256, 255))
        self.assertEqual(runtime.over_key(runtime.to_runtime_image(sheet)).tobytes(), sheet.tobytes())

    def test_a_full_bleed_picture_with_no_key_pixels_comes_out_opaque_and_unchanged(self):
        tile = Image.new("RGBA", (8, 8), (60, 160, 70, 255))
        out = runtime.to_runtime_image(tile)
        self.assertEqual(out.tobytes(), tile.tobytes())

    def test_a_picture_that_is_not_rgba_is_handled(self):
        out = runtime.to_runtime_image(Image.new("RGB", (4, 4), (255, 0, 255)))
        self.assertEqual(out.getpixel((0, 0)), (0, 0, 0, 0))


class ExportTests(BundleCase):
    def test_a_bundle_export_has_a_runtime_sheet_a_runtime_atlas_and_a_manifest(self):
        png, atlas = self.build()
        manifest = runtime.export_bundle(self.bundle, self.out)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["hero.atlas.json", "hero.png", "runtime.export.json"])
        self.assertEqual([(f["path"], f["role"]) for f in manifest["files"]], [("hero.atlas.json", "atlas"), ("hero.png", "sheet")])
        common.validate_schema(common.read_json(self.out / "runtime.export.json"), "gamearts-runtime-export")

    def test_the_runtime_sheet_has_the_same_size_and_real_transparency(self):
        png, _ = self.build()
        runtime.export_bundle(self.bundle, self.out)
        with Image.open(png) as delivered, Image.open(self.out / "hero.png") as derived:
            self.assertEqual((derived.mode, derived.size), ("RGBA", delivered.size))
            self.assertEqual(derived.getchannel("A").getextrema(), (0, 255))

    def test_the_delivered_art_is_recovered_exactly_and_never_touched(self):
        png, atlas = self.build()
        before = self.digests(self.bundle)
        runtime.export_bundle(self.bundle, self.out)
        with Image.open(self.out / "hero.png") as derived, Image.open(png) as delivered:
            self.assertEqual(runtime.over_key(derived).tobytes(), delivered.convert("RGBA").tobytes())
        self.assertEqual(self.digests(self.bundle), before)

    def test_the_runtime_atlas_keeps_every_frame_fact_and_says_where_it_came_from(self):
        png, atlas = self.build()
        runtime.export_bundle(self.bundle, self.out)
        derived, original = common.read_json(self.out / "hero.atlas.json"), common.read_json(atlas)
        block = derived.pop("runtime")
        self.assertEqual(derived.pop("background_alpha"), 0)
        original.pop("background_alpha")
        self.assertEqual(derived, original)  # rectangles, pivots, anchors, durations and tags are identical
        self.assertTrue(block["derived"])
        self.assertEqual((block["source_sheet"], block["source_sheet_sha256"], block["source_atlas_sha256"]),
                         ("hero.png", common.sha256_file(png), common.sha256_file(atlas)))

    def test_every_file_records_its_hash_and_its_sources_hash(self):
        png, atlas = self.build()
        manifest = runtime.export_bundle(self.bundle, self.out)
        by_path = {f["path"]: f for f in manifest["files"]}
        self.assertEqual(by_path["hero.png"]["source_sha256"], common.sha256_file(png))
        self.assertEqual(by_path["hero.png"]["sha256"], common.sha256_file(self.out / "hero.png"))
        self.assertNotEqual(by_path["hero.png"]["sha256"], by_path["hero.png"]["source_sha256"])

    def test_a_bundle_with_two_sheets_a_bundle_file_and_a_tileset_exports_all_of_them(self):
        self.build(name="body")
        (self.src / "x").mkdir()
        for index, (box, colour) in enumerate(BLOCKS[:2]):
            source_frame(box, colour).save(self.src / f"h{index}.png")
        sheets.build({"_input_dir": str(self.src), "name": "head", "frames": [{"file": f"h{i}.png", "name": f"h{i}", "pivot": list(PIVOT)} for i in range(2)]}, self.bundle)
        (self.bundle / "hero.bundle.json").write_text(json.dumps({"schema_version": "1.0", "asset_id": "hero"}), encoding="utf-8")
        manifest = runtime.export_bundle(self.bundle, self.out)
        self.assertEqual(sorted(f["path"] for f in manifest["files"]), ["body.atlas.json", "body.png", "head.atlas.json", "head.png", "hero.bundle.json"])
        self.assertEqual((self.out / "hero.bundle.json").read_bytes(), (self.bundle / "hero.bundle.json").read_bytes())

    def test_a_tileset_bundle_exports_opaque_sheets_and_copies_the_tileset_file(self):
        tiles = []
        from gamearts_tileset import layout_tiles
        for index, tile in enumerate(layout_tiles("wang_corner_16", TERRAINS)):
            ART["wang_corner_16"](tile["neighbours"]).save(self.src / f"t{index:02d}.png")
            tiles.append({"file": f"t{index:02d}.png", "neighbours": tile["neighbours"]})
        tilesets.build({"_input_dir": str(self.src), "name": "ground", "tile_size": [SIZE, SIZE], "layout": "wang_corner_16", "terrains": TERRAINS,
                        "tiles": tiles, "columns": 4}, self.bundle)
        runtime.export_bundle(self.bundle, self.out)
        with Image.open(self.out / "ground.png") as derived:
            self.assertEqual(derived.getchannel("A").getextrema(), (255, 255))
        self.assertEqual((self.out / "ground.tileset.json").read_bytes(), (self.bundle / "ground.tileset.json").read_bytes())

    def test_a_single_sheet_can_be_exported_on_its_own(self):
        png, atlas = self.build()
        manifest = runtime.export_sheet(png, atlas, self.out)
        self.assertEqual(sorted(f["path"] for f in manifest["files"]), ["hero.atlas.json", "hero.png"])

    def test_art_that_fails_its_own_checks_is_not_exported_and_nothing_is_left_behind(self):
        png, atlas = self.build()
        with Image.open(png) as opened:
            damaged = opened.convert("RGBA")
        damaged.putpixel((0, 0), (254, 1, 254, 255))  # one step from the key colour: contamination the sheet contract refuses
        damaged.save(png)
        with self.assertRaisesRegex(ValueError, "cannot export art that fails its own checks"):
            runtime.export_bundle(self.bundle, self.out)
        self.assertFalse(self.out.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".gamearts-runtime-")], [])

    def test_a_failure_after_the_work_has_started_leaves_no_half_built_folder_behind(self):
        self.build()
        real = common.validate_schema

        def fail_on_the_manifest(data, name, *args):
            if name == "gamearts-runtime-export":
                raise ValueError("the manifest did not validate")
            return real(data, name, *args)
        with mock.patch.object(runtime.common, "validate_schema", fail_on_the_manifest), self.assertRaisesRegex(ValueError, "manifest did not validate"):
            runtime.export_bundle(self.bundle, self.out)
        self.assertFalse(self.out.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".gamearts-runtime-")], [])

    def test_an_existing_export_is_never_overwritten(self):
        self.build()
        runtime.export_bundle(self.bundle, self.out)
        with self.assertRaisesRegex(ValueError, "never overwrites"):
            runtime.export_bundle(self.bundle, self.out)

    def test_an_empty_existing_folder_is_fine(self):
        self.build()
        self.out.mkdir()
        runtime.export_bundle(self.bundle, self.out)
        self.assertTrue((self.out / "runtime.export.json").is_file())

    def test_the_output_must_be_separate_from_the_art(self):
        self.build()
        with self.assertRaisesRegex(ValueError, "separate from the art"):
            runtime.export_bundle(self.bundle, self.bundle / "runtime")
        with self.assertRaisesRegex(ValueError, "separate from the art"):
            runtime.export_bundle(self.bundle, self.bundle)

    def test_a_folder_without_a_sheet_is_refused(self):
        self.bundle.mkdir()
        with self.assertRaisesRegex(ValueError, "no sheet to export"):
            runtime.export_bundle(self.bundle, self.out)

    def test_the_same_art_exports_to_the_same_bytes_every_time(self):
        self.build()
        runtime.export_bundle(self.bundle, self.out)
        first = self.digests(self.out)
        again = self.root / "again"
        runtime.export_bundle(self.bundle, again)
        self.assertEqual(self.digests(again), first)


class VerifyTests(BundleCase):
    def exported(self):
        self.build()
        runtime.export_bundle(self.bundle, self.out)

    def test_a_fresh_export_verifies_clean(self):
        self.exported()
        self.assertEqual(runtime.verify_export(self.out, self.bundle), [])

    def test_a_changed_source_sheet_makes_the_export_stale(self):
        self.exported()
        sheet = self.bundle / "hero.png"
        sheet.write_bytes(sheet.read_bytes() + b"x")
        issues = runtime.verify_export(self.out, self.bundle)
        self.assertTrue(any("hero.png" in i and "stale" in i and "source" in i for i in issues), issues)

    def test_a_source_that_changes_after_the_export_is_reported_as_stale(self):
        self.exported()
        atlas = self.bundle / "hero.atlas.json"
        data = common.read_json(atlas)
        data["frames"][0]["duration_ms"] += 1
        common.atomic_write_json(atlas, data)
        issues = runtime.verify_export(self.out, self.bundle)
        self.assertTrue(any("hero.atlas.json" in i and "stale" in i and "source" in i for i in issues), issues)

    def test_a_runtime_sheet_edited_afterwards_is_reported(self):
        self.exported()
        target = self.out / "hero.png"
        target.write_bytes(target.read_bytes() + b"x")
        self.assertTrue(any("hero.png" in i and "changed since it was exported" in i for i in runtime.verify_export(self.out, self.bundle)))

    def test_a_missing_file_and_an_unlisted_file_are_reported(self):
        self.exported()
        (self.out / "hero.atlas.json").unlink()
        (self.out / "extra.txt").write_text("x", encoding="utf-8")
        issues = runtime.verify_export(self.out, self.bundle)
        self.assertTrue(any("hero.atlas.json" in i and "missing" in i for i in issues), issues)
        self.assertTrue(any("extra.txt" in i and "not listed" in i for i in issues), issues)

    def rewrite_listed(self, name, change):
        """Change a runtime sheet the way a careless tool might, then fix the manifest hash so only the pixel checks can notice."""
        path = self.out / name
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        change(image)
        image.save(path)
        manifest = common.read_json(self.out / "runtime.export.json")
        for entry in manifest["files"]:
            if entry["path"] == name:
                entry["sha256"] = common.sha256_file(path)
        common.atomic_write_json(self.out / "runtime.export.json", manifest)

    def test_a_partly_transparent_pixel_is_reported(self):
        self.exported()
        self.rewrite_listed("hero.png", lambda image: image.putpixel((0, 0), (0, 0, 0, 128)))
        self.assertTrue(any("partly transparent" in i for i in runtime.verify_export(self.out, self.bundle)))

    def test_colour_left_under_a_transparent_pixel_is_reported(self):
        self.exported()
        self.rewrite_listed("hero.png", lambda image: image.putpixel((0, 0), (200, 0, 0, 0)))
        self.assertTrue(any("transparent pixels carry colour" in i for i in runtime.verify_export(self.out, self.bundle)))

    def test_an_art_pixel_whose_colour_was_changed_breaks_the_round_trip(self):
        self.exported()

        def alter(image):
            for y in range(image.height):
                for x in range(image.width):
                    if image.getpixel((x, y))[3] == 255:
                        image.putpixel((x, y), (1, 1, 1, 255))
                        return
        self.rewrite_listed("hero.png", alter)
        self.assertTrue(any("does not reproduce the delivered sheet" in i for i in runtime.verify_export(self.out, self.bundle)))

    def test_a_runtime_atlas_whose_frames_were_edited_is_reported(self):
        self.exported()
        path = self.out / "hero.atlas.json"
        data = common.read_json(path)
        data["frames"][1]["pivot"] = [0, 0]
        common.atomic_write_json(path, data)
        manifest = common.read_json(self.out / "runtime.export.json")
        for entry in manifest["files"]:
            if entry["path"] == "hero.atlas.json":
                entry["sha256"] = common.sha256_file(path)
        common.atomic_write_json(self.out / "runtime.export.json", manifest)
        self.assertTrue(any("frames, pivots, anchors, durations or tags differ" in i for i in runtime.verify_export(self.out, self.bundle)))

    def test_an_atlas_that_lost_its_runtime_block_is_reported(self):
        self.exported()
        path = self.out / "hero.atlas.json"
        data = common.read_json(path)
        del data["runtime"]
        common.atomic_write_json(path, data)
        manifest = common.read_json(self.out / "runtime.export.json")
        for entry in manifest["files"]:
            if entry["path"] == "hero.atlas.json":
                entry["sha256"] = common.sha256_file(path)
        common.atomic_write_json(self.out / "runtime.export.json", manifest)
        self.assertTrue(any("no runtime block" in i for i in runtime.verify_export(self.out, self.bundle)))

    def test_a_copied_file_that_differs_from_its_source_is_reported(self):
        self.exported()
        self.assertEqual(runtime.verify_export(self.out, self.bundle), [])
        (self.bundle / "hero.bundle.json").write_text("{}", encoding="utf-8")
        shutil.rmtree(self.out)
        runtime.export_bundle(self.bundle, self.out)
        (self.out / "hero.bundle.json").write_text("{\"x\": 1}", encoding="utf-8")
        manifest = common.read_json(self.out / "runtime.export.json")
        for entry in manifest["files"]:
            if entry["path"] == "hero.bundle.json":
                entry["sha256"] = common.sha256_file(self.out / "hero.bundle.json")
        common.atomic_write_json(self.out / "runtime.export.json", manifest)
        self.assertTrue(any("unchanged copy" in i for i in runtime.verify_export(self.out, self.bundle)))

    def test_a_folder_with_no_manifest_is_reported_not_crashed(self):
        self.exported()
        (self.out / "runtime.export.json").unlink()
        self.assertTrue(any("manifest" in i for i in runtime.verify_export(self.out, self.bundle)))


class CommandTests(BundleCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_bundle_export_then_verify_through_the_command_line(self):
        self.build()
        done = self.run_script("--bundle", str(self.bundle), "--output-dir", str(self.out))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("never approved", done.stdout)
        checked = self.run_script("--verify", str(self.out), "--source", str(self.bundle))
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["status"], "passed")

    def test_a_single_sheet_through_the_command_line(self):
        png, atlas = self.build()
        done = self.run_script("--sheet", str(png), "--atlas", str(atlas), "--output-dir", str(self.out))
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_verify_exits_one_and_lists_what_is_wrong(self):
        self.build()
        runtime.export_bundle(self.bundle, self.out)
        (self.out / "hero.png").write_bytes(b"x")
        checked = self.run_script("--verify", str(self.out), "--source", str(self.bundle))
        self.assertEqual(checked.returncode, 1)
        self.assertEqual(json.loads(checked.stdout)["status"], "failed")

    def test_missing_arguments_say_what_is_needed(self):
        for args, expected in (([], "--output-dir is required"), (["--output-dir", "x"], "give --bundle"), (["--verify", "x"], "--verify needs --source")):
            done = self.run_script(*args)
            self.assertEqual(done.returncode, 1)
            self.assertIn(expected, done.stderr)


class LifecycleTests(GameFolder):
    """The runtime export as a lifecycle operation: only for approved assets, recorded, checked, and removed with the asset."""

    def approved_asset(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        life.approve_asset(self.root, name, "approved-in-test")
        return name

    def bundle_digests(self, name):
        folder = self.root / OUT / "assets/approved" / name
        return {p.relative_to(folder).as_posix(): common.sha256_file(p) for p in sorted(folder.rglob("*")) if p.is_file()}

    @staticmethod
    def digest_folder(folder):
        return {p.name: common.sha256_file(p) for p in sorted(Path(folder).iterdir()) if p.is_file()}

    def test_an_approved_asset_gets_runtime_files_beside_not_inside_its_bundle(self):
        name = self.approved_asset()
        before = self.bundle_digests(name)
        result = life.export_runtime(self.root, name)
        self.assertEqual(result["path"], f"{OUT}/runtime/{name}/v001")
        self.assertTrue(result["derived"])
        folder = self.root / result["path"]
        self.assertTrue((folder / "runtime.export.json").is_file())
        self.assertEqual(self.bundle_digests(name), before)  # the approved art is untouched
        self.assertEqual(life.select(self.root, "assets", "approved")[0]["id"], name)

    def test_the_record_lists_the_derived_files_and_the_manifest_hash(self):
        name = self.approved_asset()
        result = life.export_runtime(self.root, name)
        record = self.manifest("assets")[0]
        entry = record["derived_exports"][0]
        self.assertEqual((entry["kind"], entry["status"], entry["path"]), ("runtime", "derived", result["path"]))
        self.assertEqual(entry["manifest_sha256"], common.sha256_file(self.root / result["path"] / "runtime.export.json"))
        self.assertEqual(record["status"], "approved")  # a derived copy never changes the asset's own state
        common.validate_schema(common.read_json(self.root / OUT / "manifests/assets.json"), "gamearts-assets-manifest")
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")

    def test_a_generated_asset_gets_nothing(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        with self.assertRaisesRegex(ValueError, "Only an approved asset"):
            life.export_runtime(self.root, name)
        self.assertFalse((self.root / OUT / "runtime").exists())

    def test_existing_runtime_files_are_kept_unless_replacement_is_asked_for(self):
        name = self.approved_asset()
        first = life.export_runtime(self.root, name)
        with self.assertRaisesRegex(ValueError, "already exist"):
            life.export_runtime(self.root, name)
        again = life.export_runtime(self.root, name, replace=True)
        self.assertEqual(again["path"], first["path"])
        self.assertEqual(len(self.manifest("assets")[0]["derived_exports"]), 1)
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")
        self.assertEqual([p.name for p in (self.root / OUT / "runtime" / name).iterdir()], ["v001"])

    def test_a_failed_replacement_puts_the_previous_files_back(self):
        name = self.approved_asset()
        first = life.export_runtime(self.root, name)
        before = self.digest_folder(self.root / first["path"])
        with mock.patch("export_runtime.export_bundle", side_effect=ValueError("disk said no")):
            with self.assertRaisesRegex(ValueError, "disk said no"):
                life.export_runtime(self.root, name, replace=True)
        self.assertEqual(self.digest_folder(self.root / first["path"]), before)
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")
        self.assertEqual([p.name for p in (self.root / OUT / "runtime" / name).iterdir()], ["v001"])

    def test_a_runtime_file_changed_afterwards_is_found_by_reconcile(self):
        name = self.approved_asset()
        result = life.export_runtime(self.root, name)
        sheet = next((self.root / result["path"]).glob("*.png"))
        sheet.write_bytes(sheet.read_bytes() + b"x")
        report = life.reconcile_assets(self.root)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any(name in i and "runtime export" in i and "changed since it was exported" in i for i in report["issues"]), report["issues"])

    def test_a_missing_runtime_folder_is_found_by_reconcile(self):
        name = self.approved_asset()
        result = life.export_runtime(self.root, name)
        shutil.rmtree(self.root / result["path"])
        self.assertTrue(any("missing or outside the runtime store" in i for i in life.reconcile_assets(self.root)["issues"]))

    def test_revoking_the_asset_removes_its_runtime_files_and_the_record_field(self):
        name = self.approved_asset()
        result = life.export_runtime(self.root, name)
        revoked = life.revoke(self.root, "assets", name, "art direction changed")
        self.assertEqual(revoked["derived_exports_removed"], [result["path"]])
        self.assertEqual(revoked["problems"], [])
        self.assertFalse((self.root / result["path"]).exists())
        self.assertNotIn("derived_exports", self.manifest("assets")[0])
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")

    def test_an_asset_revoked_without_runtime_files_reports_no_removal(self):
        name = self.approved_asset()
        self.assertNotIn("derived_exports_removed", life.revoke(self.root, "assets", name, "art direction changed"))

    def test_a_restored_asset_starts_without_runtime_files_and_needs_a_new_approval(self):
        name = self.approved_asset()
        life.export_runtime(self.root, name)
        life.revoke(self.root, "assets", name, "art direction changed")
        life.restore(self.root, "assets", name, "v001", "owner asked for it back")
        self.assertNotIn("derived_exports", self.manifest("assets")[0])
        with self.assertRaisesRegex(ValueError, "Only an approved asset"):
            life.export_runtime(self.root, name)

    def test_an_asset_that_fails_its_audit_gets_no_runtime_files(self):
        name = self.approved_asset()
        next((self.root / OUT / "assets/approved" / name).glob("*.png")).write_bytes(b"damaged")
        with self.assertRaisesRegex(ValueError, "fails its audit"):
            life.export_runtime(self.root, name)

    def test_the_profile_default_makes_runtime_files_when_an_engine_asks_for_them(self):
        write_settings(self.root, engine_target={"profile": "godot"})
        name = self.approved_asset()
        outcome = life.auto_exports(self.root, name)
        self.assertEqual(outcome["runtime"]["status"], "written")
        self.assertTrue((self.root / outcome["runtime"]["path"] / "runtime.export.json").is_file())

    def test_a_game_with_no_engine_or_the_generic_one_gets_nothing_automatically(self):
        name = self.approved_asset()
        self.assertEqual(life.auto_exports(self.root, name), {})
        write_settings(self.root, engine_target={"profile": "generic"})
        self.assertEqual(life.auto_exports(self.root, name), {})
        self.assertFalse((self.root / OUT / "runtime").exists())

    def test_a_failure_of_the_automatic_export_is_reported_and_the_approval_stands(self):
        write_settings(self.root, engine_target={"profile": "godot"})
        name = self.approved_asset()
        with mock.patch("export_runtime.export_bundle", side_effect=ValueError("disk said no")):
            outcome = life.auto_exports(self.root, name)
        self.assertEqual(outcome["runtime"], {"status": "failed", "reason": "disk said no"})
        self.assertEqual(self.manifest("assets")[0]["status"], "approved")

    def test_unreadable_settings_are_reported_not_hidden(self):
        name = self.approved_asset()
        (self.root / ".gamearts" / "project.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(life.auto_exports(self.root, name)["settings"]["status"], "unread")

    def test_the_next_step_after_approval_names_the_runtime_files_or_the_failure(self):
        written = life.next_step_for("approve", {"derived_exports": {"runtime": {"status": "written", "path": "p/q"}}})
        self.assertIn("engine-ready copies are in p/q", written)
        failed = life.next_step_for("approve", {"derived_exports": {"runtime": {"status": "failed", "reason": "disk said no"}}})
        self.assertIn("could not be made (disk said no)", failed)
        self.assertEqual(life.next_step_for("approve", {}), "The asset is approved. Tell the owner and ask what to make next.")


class LifecycleCommandTests(GameFolder):
    def run_op(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "gamearts_asset_lifecycle.py"), *args, "--game-root", str(self.root)], capture_output=True, text=True)

    def test_export_runtime_through_the_command_line_names_the_files_and_the_next_step(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        life.approve_asset(self.root, name, "approved-in-test")
        done = self.run_op("export-runtime", "--id", name)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertTrue(result["ok"])
        self.assertIn("derived files", result["next_step"])
        self.assertTrue((self.root / result["path"]).is_dir())

    def test_approving_through_the_command_line_makes_the_profile_default_files(self):
        write_settings(self.root, engine_target={"profile": "godot"})
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        done = self.run_op("approve", "--id", name, "--user-approval-ref", "approved-in-test")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result["derived_exports"]["runtime"]["status"], "written")
        self.assertIn("engine-ready copies", result["next_step"])
        self.assertEqual(self.run_op("reconcile-assets").returncode, 0)

    def test_approving_for_a_game_without_an_engine_makes_nothing_extra(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        result = json.loads(self.run_op("approve", "--id", name, "--user-approval-ref", "approved-in-test").stdout)
        self.assertNotIn("derived_exports", result)
        self.assertFalse((self.root / OUT / "runtime").exists())


if __name__ == "__main__":
    unittest.main()
