"""A palette variant and an animated tileset taken through the real command lines and the lifecycle, on synthetic art.

REHEARSAL, NOT ART: the frames are a few coloured pixels and every approval string is a stand-in. It proves the new tools hand their files to the
sheet builder, the registration gate, approval and the disclosure summary correctly, not that any variant looks good.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gamearts_testkit import PINK, key_image, make_mockup, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_disclosure as disclosure  # noqa: E402
import gamearts_report as report  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
OUT = ".gamearts/outputs"
CLOAK, SKIN, BOOT = (180, 30, 30, 255), (230, 190, 150, 255), (60, 40, 30, 255)
RECOLOURED = {"#B41E1E": "#1E3CB4", "#E6BE96": "#E6BE96", "#3C281E": "#503C64", "#463228": "#5A465A"}  # cloak, skin, both boots


def run(script, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True)
    assert result.returncode == 0, f"{script} {' '.join(map(str, args))}\nexit {result.returncode}\n{result.stdout}\n{result.stderr}"
    return result


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "game"
        self.root.mkdir()
        write_settings(self.root)
        image, metadata = make_mockup(self.root, "hero", "v001", "world")
        life.register_mockup(self.root, metadata, image)
        life.approve_mockup(self.root, "hero", "v001", "approved-in-test")

    def bundle(self, name):
        folder = self.root / OUT / "assets" / "generated" / name
        folder.mkdir(parents=True)
        return folder

    def register_and_approve(self, name, extra=None, source_assets=()):
        args = ["register-asset", "--game-root", self.root, "--id", name, "--revision", "v001", "--bundle", f"{OUT}/assets/generated/{name}",
                "--source-mockup", "hero:v001"]
        for source in source_assets:
            args += ["--source-asset", source]
        if extra is not None:
            extra_file = Path(self._tmp.name) / f"{name}.extra.json"
            extra_file.write_text(json.dumps(extra), encoding="utf-8")
            args += ["--extra", extra_file]
        registered = json.loads(run("gamearts_asset_lifecycle.py", *args).stdout)
        life.approve_asset(self.root, name, "approved-in-test")
        return registered


class SheetCase(Case):
    def frames(self, folder):
        folder.mkdir(parents=True)
        for index, boot in enumerate((BOOT, (70, 50, 40, 255))):
            key_image((12, 10), {(3, 2): CLOAK, (4, 2): SKIN, (3 + index, 8): boot}).save(folder / f"walk{index}.png")
        return folder

    def sheet_job(self, name, frames):
        job = {"name": name, "asset_id": name, "columns": 2, "padding": 2, "spacing": 3, "source_mockups": [{"mockup_id": "hero", "revision": "v001"}],
               "frames": [{"file": f"walk{i}.png", "name": f"S{i}", "direction": "S", "pivot": [4, 9], "duration_ms": 100} for i in range(2)]}
        path = frames / f"{name}.job.json"
        path.write_text(json.dumps(job), encoding="utf-8")
        return path

    def build(self, name, frames):
        run("build_sheet_atlas.py", self.sheet_job(name, frames), "--output-dir", self.bundle(f"{name}"))


class VariantTests(SheetCase):
    def test_an_approved_sheet_becomes_a_variant_that_passes_the_same_gates_and_is_traceable(self):
        original = self.frames(self.root / "work" / "hero_frames")
        self.build("hero_v001", original)
        base = self.register_and_approve("hero_v001")
        self.assertEqual(base["technical_validation"], "passed")

        colour_map = self.root / "work" / "blue_team.map.json"
        colour_map.write_text(json.dumps({"schema_version": "1.0", "colours": RECOLOURED}), encoding="utf-8")
        recoloured = self.root / "work" / "hero_blue_frames"
        run("gamearts_palette.py", "recolour", "--game-root", self.root, "--folder", original, "--output-folder", recoloured, "--map", colour_map)
        self.assertTrue((recoloured / "walk0.png").is_file())
        self.assertTrue((recoloured / "recolour.record.json").is_file())
        # the originals are untouched and the variant has the same key background
        with Image.open(original / "walk0.png") as before, Image.open(recoloured / "walk0.png") as after:
            self.assertEqual(before.convert("RGBA").getpixel((0, 0)), PINK)
            self.assertEqual(after.convert("RGBA").getpixel((0, 0)), PINK)
            self.assertNotEqual(before.convert("RGBA").getpixel((3, 2)), after.convert("RGBA").getpixel((3, 2)))

        self.build("hero_blue_v001", recoloured)
        variant = self.register_and_approve("hero_blue_v001", {"provenance": {"provider": "Game Arts recolour", "edit_mode": "palette_variant"}})
        self.assertEqual(variant["technical_validation"], "passed")

        record = common.read_json(recoloured / "recolour.record.json")
        self.assertEqual({f["source"] for f in record["files"]}, {"walk0.png", "walk1.png"})
        summary = {asset["id"]: asset for asset in disclosure.build(self.root)["assets"]}
        self.assertEqual(summary["hero_blue_v001"]["recorded_provenance"]["edit_mode"], "palette_variant")
        self.assertNotIn("recorded_provenance", summary["hero_v001"])

    def test_a_variant_with_a_colour_the_map_forgot_is_stopped_before_any_sheet_exists(self):
        original = self.frames(self.root / "work" / "hero_frames")
        colour_map = self.root / "work" / "partial.map.json"
        colour_map.write_text(json.dumps({"schema_version": "1.0", "colours": {"#B41E1E": "#1E3CB4"}}), encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPTS / "gamearts_palette.py"), "recolour", "--game-root", str(self.root), "--folder", str(original),
                               "--output-folder", str(self.root / "work" / "out"), "--map", str(colour_map)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("the map does not list", done.stderr)
        self.assertFalse((self.root / "work" / "out").exists())


class LineageTests(SheetCase):
    """A variant names the approved asset it was made from, so withdrawing the base reaches the variant."""

    def approved_base(self):
        self.build("hero_v001", self.frames(self.root / "work" / "hero_frames"))
        self.register_and_approve("hero_v001")

    def approved_variant(self):
        self.build("hero_blue_v001", self.frames(self.root / "work" / "hero_blue_frames"))
        return self.register_and_approve("hero_blue_v001", {"provenance": {"provider": "Game Arts recolour", "edit_mode": "palette_variant"}}, ["hero_v001:v001"])

    def manifest_row(self, name):
        rows = common.read_json(self.root / OUT / "manifests" / "assets.json")["assets"]
        return next(row for row in rows if row["asset_id"] == name)

    def test_the_variant_records_the_asset_it_was_made_from(self):
        self.approved_base()
        self.approved_variant()
        self.assertEqual(self.manifest_row("hero_blue_v001")["source_assets"], [{"asset_id": "hero_v001", "revision": "v001"}])
        self.assertNotIn("source_assets", self.manifest_row("hero_v001"))

    def test_withdrawing_the_base_names_the_variant_and_its_next_audit_fails(self):
        self.approved_base()
        self.approved_variant()
        result = life.revoke(self.root, "assets", "hero_v001", "the frames were flawed", revision="v001")
        self.assertEqual(result["dependents"], [{"asset_id": "hero_blue_v001", "status": "approved"}])
        self.assertIn("1 asset(s) were built on it", life.next_step_for("revoke", result))
        issues = life.audit_asset(self.root, "hero_blue_v001")
        self.assertTrue(any("hero_v001 v001, which is missing or no longer approved" in issue for issue in issues), issues)

    def test_withdrawing_a_variant_leaves_the_base_alone(self):
        self.approved_base()
        self.approved_variant()
        result = life.revoke(self.root, "assets", "hero_blue_v001", "wrong team colours", revision="v001")
        self.assertEqual(result["dependents"], [])
        self.assertEqual(life.audit_asset(self.root, "hero_v001"), [])

    def test_a_source_that_is_not_an_approved_asset_is_refused_by_name(self):
        self.build("hero_v001", self.frames(self.root / "work" / "hero_frames"))
        registered_only = life.register_asset(self.root, "hero_v001", "v001", f"{OUT}/assets/generated/hero_v001", [("hero", "v001")])
        self.assertEqual(registered_only["asset_id"], "hero_v001")  # generated, not yet approved
        self.build("blue_v001", self.frames(self.root / "work" / "blue_frames"))
        blue = f"{OUT}/assets/generated/blue_v001"
        for sources, message in (([("hero_v001", "v001")], "hero_v001 v001 is not an approved asset"),
                                 ([("nobody", "v001")], "nobody v001 is not an approved asset"),
                                 ([("blue_v001", "v001")], "cannot be made from itself")):
            with self.subTest(sources=sources), self.assertRaisesRegex(ValueError, message):
                life.register_asset(self.root, "blue_v001", "v001", blue, [("hero", "v001")], None, sources)

    def test_the_same_source_twice_is_refused(self):
        self.approved_base()
        self.build("blue_v001", self.frames(self.root / "work" / "blue_frames"))
        with self.assertRaisesRegex(ValueError, "named twice"):
            life.register_asset(self.root, "blue_v001", "v001", f"{OUT}/assets/generated/blue_v001", [("hero", "v001")], None,
                                [("hero_v001", "v001"), ("hero_v001", "v001")])

    def test_the_report_names_the_base_and_the_tool_or_says_it_is_not_recorded(self):
        self.approved_base()
        self.approved_variant()
        page = Path(report.build(self.root)["path"]).read_text(encoding="utf-8")
        self.assertIn("Made from the asset: hero_v001 v001", page)
        self.assertIn("Made with: Game Arts recolour", page)
        self.assertIn("The tool that made this is not recorded.", page)  # the base carries no provenance


class AnimatedTilesetTests(Case):
    def tiles(self, folder):
        folder.mkdir(parents=True)
        for name, mark in (("water0", (40, 90, 200)), ("water1", (60, 110, 220)), ("water2", (80, 130, 240))):
            image = Image.new("RGBA", (8, 8), (50, 100, 210, 255))
            image.putpixel((3, 3), (*mark, 255))
            image.save(folder / f"{name}.png")
        job = {"name": "water_v001", "asset_id": "water_v001", "tile_size": [8, 8], "layout": "variants", "terrains": ["water"],
               "source_mockups": [{"mockup_id": "hero", "revision": "v001"}],
               "tiles": [{"file": "water0.png"}, {"file": "water1.png"}, {"file": "water2.png"}],
               "animations": [{"tile": 0, "frames": [{"tile": 0, "duration_ms": 150}, {"tile": 1, "duration_ms": 150}, {"tile": 2, "duration_ms": 150}]}]}
        path = folder / "water.job.json"
        path.write_text(json.dumps(job), encoding="utf-8")
        return path

    def test_an_animated_tileset_is_built_registered_approved_and_exported_for_tiled(self):
        job = self.tiles(self.root / "work" / "water")
        folder = self.bundle("water_v001")
        run("build_tileset.py", job, "--output-dir", folder)
        registered = self.register_and_approve("water_v001")
        self.assertEqual(registered["technical_validation"], "passed")
        approved = self.root / OUT / "assets" / "approved" / "water_v001"  # approval moves the whole bundle
        tileset = approved / "water_v001.tileset.json"
        run("validate_tileset.py", tileset)
        run("export_exchange.py", "--tileset", tileset, "--format", "tiled")
        exported = json.loads((approved / "water_v001.tsj").read_text(encoding="utf-8"))
        self.assertEqual(exported["tiles"], [{"id": 0, "animation": [{"tileid": 0, "duration": 150}, {"tileid": 1, "duration": 150}, {"tileid": 2, "duration": 150}]}])

    def test_the_technical_gate_refuses_a_bundle_whose_tileset_animation_was_broken_afterwards(self):
        job = self.tiles(self.root / "work" / "water")
        folder = self.bundle("water_v001")
        run("build_tileset.py", job, "--output-dir", folder)
        tileset = folder / "water_v001.tileset.json"
        body = json.loads(tileset.read_text(encoding="utf-8"))
        body["animations"][0]["frames"][1]["tile"] = 9
        tileset.write_text(json.dumps(body), encoding="utf-8")
        registered = life.register_asset(self.root, "water_v001", "v001", f"{OUT}/assets/generated/water_v001", [("hero", "v001")])
        self.assertNotEqual(registered["technical_validation"], "passed")
        self.assertTrue(any("not in the tileset" in issue for issue in registered["technical_issues"]), registered["technical_issues"])


if __name__ == "__main__":
    unittest.main()
