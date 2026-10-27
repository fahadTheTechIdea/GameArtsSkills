"""World kinds, named direction sets, hex grids and the asset classes of games that have no ground world (plan P9)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

import gamearts_testkit as kit
from gamearts_testkit import settings

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "gamearts-project.schema.json").read_text(encoding="utf-8"))
JOB_SCHEMA = json.loads((ROOT / "schemas" / "gamearts-reference-job.schema.json").read_text(encoding="utf-8"))
PACKET_SCHEMA = json.loads((ROOT / "schemas" / "gamearts-reference-packet.schema.json").read_text(encoding="utf-8"))

spec = importlib.util.spec_from_file_location("prepare_reference_crop", ROOT / "scripts" / "prepare_reference_crop.py")
crop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crop)
import gamearts_common as common  # noqa: E402  (the testkit puts scripts/ on the path)

# Hashes recorded from the code BEFORE world kinds existed: adding optional fields must never move them (plan D-13).
FROZEN_DEFAULT_HASH = "f96d00998cc0d8ea945564a850d1e70997529085628ff4591d13b088c31166bc"
FROZEN_ISOMETRIC_HASH = "b537664330fad87f3f1001ac99fa43fc5cb5978e2cb06b095036b66750163400"
ISOMETRIC = {"grid": "isometric", "camera_profile": "isometric_3_4", "object_camera": "iso", "logical_tile_m": [16, 16],
             "ground_tile_px": [256, 128], "pixels_per_meter": 16, "construction_snap_m": 1}


def valid(body):
    jsonschema.validate(body, SCHEMA)


def invalid(test, body, fragment=None):
    with test.assertRaises(jsonschema.ValidationError) as caught:
        jsonschema.validate(body, SCHEMA)
    if fragment:
        test.assertIn(fragment, caught.exception.message)


class FrozenHashTests(unittest.TestCase):
    def test_existing_projects_keep_their_material_settings_hash(self):
        self.assertEqual(common.canonical_settings_hash(settings()), FROZEN_DEFAULT_HASH)
        self.assertEqual(common.canonical_settings_hash(settings(world=ISOMETRIC, directions=["S"])), FROZEN_ISOMETRIC_HASH)

    def test_a_new_optional_field_enters_the_hash_only_when_it_is_present(self):
        base = common.canonical_settings_hash(settings())
        self.assertNotEqual(base, common.canonical_settings_hash(settings(world_kind="free_world")))
        self.assertNotEqual(base, common.canonical_settings_hash(settings(screen={"base_resolution_px": [1280, 720]})))

    def test_the_image_generator_and_the_engine_target_are_not_material(self):
        base = common.canonical_settings_hash(settings())
        self.assertEqual(base, common.canonical_settings_hash(settings(image_generation={"tool": "user_supplied"})))
        self.assertEqual(base, common.canonical_settings_hash(settings(engine_target={"profile": "generic"})))


class WorldKindSchemaTests(unittest.TestCase):
    def test_a_project_without_world_kind_still_needs_the_full_grid_geometry(self):
        valid(settings())
        body = settings()
        del body["world"]["construction_snap_m"]
        invalid(self, body, "construction_snap_m")
        body = settings(drop=("world",))
        invalid(self, body, "world")

    def test_grid_world_named_explicitly_behaves_the_same(self):
        valid(settings(world_kind="grid_world"))
        body = settings(world_kind="grid_world")
        del body["world"]["ground_tile_px"]
        invalid(self, body, "ground_tile_px")

    def test_free_world_needs_a_camera_and_a_scale_but_no_tile_grid(self):
        world = {"camera_profile": "side", "object_camera": "side view orthographic", "pixels_per_meter": 32}
        valid(settings(world_kind="free_world", world=world))
        for missing in world:
            body = settings(world_kind="free_world", world={k: v for k, v in world.items() if k != missing})
            with self.subTest(missing=missing):
                invalid(self, body, missing)

    def test_layered_scene_needs_ordered_layers_with_a_scroll_scale(self):
        world = {"camera_profile": "side", "object_camera": "side view orthographic", "pixels_per_meter": 32,
                 "layers": [{"id": "sky", "scroll_scale": [0.1, 0]},
                            {"id": "hills", "scroll_scale": [0.4, 0], "repeat_px": [1024, 0], "autoscroll_px_per_s": [4, 0]},
                            {"id": "ground", "scroll_scale": [1, 1]}]}
        valid(settings(world_kind="layered_scene", world=world))
        invalid(self, settings(world_kind="layered_scene", world={k: v for k, v in world.items() if k != "layers"}), "layers")
        broken = dict(world, layers=[{"id": "sky"}])
        invalid(self, settings(world_kind="layered_scene", world=broken), "scroll_scale")
        empty = dict(world, layers=[])
        invalid(self, settings(world_kind="layered_scene", world=empty))

    def test_screen_space_needs_a_base_resolution_and_no_world_or_directions(self):
        body = settings(world_kind="screen_space", screen={"base_resolution_px": [1280, 720], "scaling": "integer"}, drop=("world", "directions"))
        valid(body)
        invalid(self, settings(world_kind="screen_space", drop=("world", "directions")), "screen")
        bad = settings(world_kind="screen_space", screen={"base_resolution_px": [0, 720]}, drop=("world", "directions"))
        invalid(self, bad)
        bad = settings(world_kind="screen_space", screen={"base_resolution_px": [1280, 720], "scaling": "wobble"}, drop=("world", "directions"))
        invalid(self, bad)

    def test_unknown_world_kinds_are_rejected(self):
        invalid(self, settings(world_kind="open_ocean"))

    def test_hex_grids_validate_for_the_oblique_and_top_down_cameras(self):
        for grid in ("hex_pointy", "hex_flat"):
            for camera in ("orthogonal_3_4_oblique", "top_down"):
                with self.subTest(grid=grid, camera=camera):
                    world = dict(settings()["world"], grid=grid, camera_profile=camera, ground_tile_px=[64, 56])
                    valid(settings(world=world))

    def test_a_game_may_name_its_engine_by_a_slug_only(self):
        valid(settings(engine_target={"profile": "godot", "version_note": "4.7"}))
        valid(settings(engine_target={"profile": "generic"}))
        for bad in ({}, {"profile": ""}, {"profile": "Not A Slug"}, {"profile": "godot", "unknown": 1}):
            with self.subTest(bad=bad):
                invalid(self, settings(engine_target=bad))


class DirectionSetTests(unittest.TestCase):
    def test_named_sets_resolve_to_their_lists(self):
        self.assertEqual(common.resolve_directions(settings()), kit.EIGHT)
        self.assertEqual(common.resolve_directions(settings(directions="dirs_8")), kit.EIGHT)
        self.assertEqual(common.resolve_directions(settings(directions="dirs_4")), ["S", "W", "N", "E"])
        self.assertEqual(common.resolve_directions(settings(directions="dirs_2_side")), ["E", "W"])
        self.assertEqual(common.resolve_directions(settings(directions="dirs_1_side")), ["E"])
        self.assertEqual(common.resolve_directions(settings(directions="dirs_1_front")), ["S"])
        self.assertEqual(common.resolve_directions(settings(drop=("directions",))), [])

    def test_an_unknown_set_name_fails_instead_of_getting_a_default(self):
        with self.assertRaisesRegex(ValueError, "Unknown direction set 'dirs_16'"):
            common.resolve_directions(settings(directions="dirs_16"))

    def test_the_schema_lists_exactly_the_sets_the_code_knows(self):
        options = SCHEMA["properties"]["directions"]["oneOf"]
        names = next(option["enum"] for option in options if "enum" in option)
        self.assertEqual(sorted(names), sorted(common.DIRECTION_SETS))

    def test_a_set_name_or_an_explicit_list_validates_and_nothing_else_does(self):
        for good in ("dirs_4", ["S"], list(kit.EIGHT)):
            with self.subTest(good=good):
                valid(settings(directions=good))
        for bad in ("dirs_16", [], ["S", "S"], 8, None):
            with self.subTest(bad=bad):
                invalid(self, settings(directions=bad))

    def test_changing_the_direction_set_is_a_material_change(self):
        self.assertNotEqual(common.canonical_settings_hash(settings(directions="dirs_4")),
                            common.canonical_settings_hash(settings(directions="dirs_8")))


class ReferenceCropForOtherGamesTests(unittest.TestCase):
    def game(self, root, asset_class="mobile_directional", **overrides):
        return kit.crop_game(root, asset_class, **overrides)

    def run_job(self, root, job, out="out"):
        return kit.crop_prepare(crop, root, job, out)

    SCREEN = {"world_kind": "screen_space", "screen": {"base_resolution_px": [1280, 720]}, "drop": ("world", "directions")}

    def test_a_four_direction_project_needs_no_per_asset_exception(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = self.game(root, directions="dirs_4")
            packet = json.loads(self.run_job(root, job).read_text())
            self.assertEqual(packet["resolved_directions"], ["S", "W", "N", "E"])

    def test_a_job_with_another_direction_count_is_refused_with_the_project_set(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = self.game(root, directions="dirs_4")
            job["directions"] = list(kit.EIGHT)
            with self.assertRaisesRegex(ValueError, "require 4 directions"):
                self.run_job(root, job)
            job["rotation_policy"] = "explicit_limited"
            self.assertTrue(self.run_job(root, job, "limited").is_file())

    def test_the_eight_direction_default_is_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = self.game(root)
            self.assertEqual(json.loads(self.run_job(root, job).read_text())["resolved_directions"], kit.EIGHT)
            job["directions"] = ["S", "N"]
            with self.assertRaisesRegex(ValueError, "require 8 directions"):
                self.run_job(root, job, "other")

    def test_screen_space_games_prepare_screen_classes_with_the_ui_camera(self):
        for asset_class in ("ui_presentation", "icon_set", "card_layer_set", "portrait_set"):
            with self.subTest(asset_class=asset_class), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                job = self.game(root, asset_class, art_style={"id": "vector", "ui_camera": "flat front-on screen view"}, **self.SCREEN)
                packet_file = self.run_job(root, job)
                packet = json.loads(packet_file.read_text())
                self.assertEqual(packet["resolved_camera"], "flat front-on screen view")
                self.assertEqual(packet["resolved_directions"], ["ui"])
                prompt = (packet_file.parent / packet["prompt_path"]).read_text()
                self.assertIn("1280x720", prompt)
                jsonschema.validate(packet, PACKET_SCHEMA)

    def test_screen_space_games_refuse_world_classes_and_say_why(self):
        for asset_class in ("static_structure", "fixed_machinery", "mobile_directional", "terrain", "tileset", "parallax_layer"):
            with self.subTest(asset_class=asset_class), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                job = self.game(root, asset_class, **self.SCREEN)
                with self.assertRaisesRegex(ValueError, "screen_space"):
                    self.run_job(root, job)

    def test_an_effect_in_a_screen_space_game_uses_the_ui_camera(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = self.game(root, "effect", art_style={"id": "vector", "ui_camera": "screen view"}, **self.SCREEN)
            self.assertEqual(json.loads(self.run_job(root, job).read_text())["resolved_camera"], "screen view")

    def test_new_world_classes_follow_the_ground_or_object_camera_and_their_export_rule(self):
        world = dict(settings()["world"], ground_camera="straight-down ground")
        expectations = {"tileset": ("straight-down ground", ["tile"], "full_bleed"),
                        "terrain": ("straight-down ground", ["tile"], "full_bleed"),
                        "parallax_layer": ("elevated orthographic oblique", ["layer"], "full_bleed")}
        for asset_class, (camera, directions, rule) in expectations.items():
            with self.subTest(asset_class=asset_class), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                job = self.game(root, asset_class, world=world)
                packet = json.loads(self.run_job(root, job).read_text())
                self.assertEqual((packet["resolved_camera"], packet["resolved_directions"], packet["export_rule"]), (camera, directions, rule))

    def test_the_job_and_packet_contracts_list_exactly_the_classes_the_script_knows(self):
        classes = {"tileset", "parallax_layer", "portrait_set", "icon_set", "card_layer_set"}
        self.assertLessEqual(classes, crop.CLASSES)
        self.assertEqual(set(JOB_SCHEMA["properties"]["asset_class"]["enum"]), crop.CLASSES)
        self.assertEqual(set(PACKET_SCHEMA["properties"]["asset_class"]["enum"]), crop.CLASSES)

    def test_the_schema_lists_exactly_the_world_kinds_the_code_knows(self):
        self.assertEqual(SCHEMA["properties"]["world_kind"]["enum"], list(common.WORLD_KINDS))
        self.assertIn(common.DEFAULT_WORLD_KIND, common.WORLD_KINDS)

    def test_a_tileset_needs_a_tile_grid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            world = {"camera_profile": "side", "object_camera": "side view", "pixels_per_meter": 32}
            job = self.game(root, "tileset", world_kind="free_world", world=world)
            with self.assertRaisesRegex(ValueError, "tileset needs a tile grid"):
                self.run_job(root, job)

    def test_a_free_world_game_prepares_world_classes_with_its_object_camera(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            world = {"camera_profile": "side", "object_camera": "side view orthographic", "pixels_per_meter": 32}
            job = self.game(root, "prop", world_kind="free_world", world=world)
            packet_file = self.run_job(root, job)
            self.assertEqual(json.loads(packet_file.read_text())["resolved_camera"], "side view orthographic")
            self.assertIn("32 world pixels/meter", (packet_file.parent / "reference.prompt.txt").read_text())


if __name__ == "__main__":
    unittest.main()
