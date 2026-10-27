"""Style presets and engine profiles: shipped data, one loader, and the settings that point at them (plan P10)."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

import gamearts_testkit as kit
from gamearts_testkit import settings, write_settings

import gamearts_asset_lifecycle as lifecycle  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_presets as presets  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_presets.py"
PROJECT_SCHEMA = json.loads((ROOT / "schemas" / "gamearts-project.schema.json").read_text(encoding="utf-8"))
STYLE_SCHEMA = json.loads((ROOT / "schemas" / "gamearts-style-preset.schema.json").read_text(encoding="utf-8"))
# Names a preset must never carry: image vendors, products and engines (a preset is tool-neutral guidance, D-9).
BANNED = ("godot", "unity", "unreal", "gamemaker", "phaser", "defold", "construct", "midjourney", "scenario", "spritecook", "pixellab",
          "retro diffusion", "layer.ai", "openai", "dall-e", "dalle", "stable diffusion", "firefly", "aseprite")


def write_profile(folder, **changes):
    profile = {"id": "sample", "title": "Sample", "summary": "A sample profile.",
               "import_guidance": [{"topic": "Filtering", "applies_to": "all", "text": "Use the plain setting.", "source": "page"}],
               "concept_map": [{"concept": "key_colour_removal", "engine_term": "a colour key", "support": "native", "source": "page"}],
               "sources": [{"id": "page", "url": "https://example.test/docs", "basis": "documented", "retrieved": "2026-10-24"}]}
    profile.update(changes)
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / f"{profile['id']}.json").write_text(json.dumps(profile), encoding="utf-8")
    return profile


class StylePresetTests(unittest.TestCase):
    def setUp(self):
        self.all = presets.style_presets()

    def test_at_least_ten_presets_ship_and_each_matches_its_file_name(self):
        self.assertGreaterEqual(len(self.all), 10)
        for name, preset in self.all.items():
            self.assertTrue((ROOT / "presets" / "styles" / f"{name}.json").is_file())
            self.assertEqual(preset["id"], name)

    def test_descriptions_are_short_and_avoid_lists_are_instructions_not_to_do_something(self):
        for name, preset in self.all.items():
            with self.subTest(preset=name):
                self.assertLessEqual(len(preset["description"].split()), 40)
                self.assertLessEqual(len(preset["avoid"]), 6)
                for line in preset["avoid"]:
                    self.assertTrue(line.startswith("Do not"), f"{name}: {line}")

    def test_no_preset_names_a_vendor_a_product_or_an_engine(self):
        for path in (ROOT / "presets" / "styles").glob("*.json"):
            text = path.read_text(encoding="utf-8").lower()
            for word in BANNED:
                self.assertNotIn(word, text, f"{path.name} names {word!r}")

    def test_the_preset_contract_uses_the_same_choices_as_the_project_contract(self):
        art_ids = PROJECT_SCHEMA["properties"]["art_style"]["properties"]["id"]["enum"]
        self.assertEqual(STYLE_SCHEMA["properties"]["art_style"]["properties"]["id"]["enum"], art_ids)
        cameras = PROJECT_SCHEMA["properties"]["world"]["properties"]["camera_profile"]["enum"]
        self.assertEqual(STYLE_SCHEMA["properties"]["cameras"]["items"]["enum"], cameras)
        self.assertEqual(STYLE_SCHEMA["properties"]["world_kinds"]["items"]["enum"], list(common.WORLD_KINDS))

    def test_a_project_built_from_any_preset_validates(self):
        for name, preset in self.all.items():
            with self.subTest(preset=name):
                art_style = dict(preset["art_style"], preset=name)
                jsonschema.validate(settings(art_style=art_style), PROJECT_SCHEMA)

    def test_pixel_presets_are_held_to_the_pixel_checks_and_never_ask_for_soft_edges(self):
        pixel = {name: p for name, p in self.all.items() if p["art_style"]["id"] == "pixel_art"}
        self.assertGreaterEqual(len(pixel), 3)
        for name, preset in pixel.items():
            with self.subTest(preset=name):
                self.assertFalse(preset["soft_edges"])
                self.assertLessEqual({"palette_exact", "pixel_grid", "integer_scale", "colour_count_max"}, set(preset["required_checks"]))
                self.assertLessEqual(preset["tile_px"][0], preset["tile_px"][1])

    def test_check_parameters_belong_to_checks_the_preset_requires(self):
        for name, preset in self.all.items():
            with self.subTest(preset=name):
                self.assertLessEqual(set(preset.get("check_parameters", {})), set(preset["required_checks"]))

    def test_every_check_a_preset_requires_belongs_to_the_checks_the_framework_can_measure(self):
        measurable = set(STYLE_SCHEMA["properties"]["required_checks"]["items"]["enum"])
        for name, preset in self.all.items():
            self.assertLessEqual(set(preset["required_checks"]), measurable, name)


class EngineProfileLoaderTests(unittest.TestCase):
    def test_the_generic_profile_ships_and_claims_nothing_about_any_engine(self):
        generic = presets.engine_profiles()[presets.GENERIC]
        self.assertEqual(generic["concept_map"], [])
        self.assertEqual(generic["sources"], [])
        self.assertGreaterEqual(len(generic["import_guidance"]), 4)

    def test_every_shipped_profile_loads_and_is_internally_consistent(self):
        profiles = presets.engine_profiles()
        self.assertIn(presets.GENERIC, profiles)
        for name, profile in profiles.items():
            self.assertEqual(profile["id"], name)

    def test_a_damaged_profile_is_refused_by_name_and_reason(self):
        cases = {
            "an unknown concept": dict(concept_map=[{"concept": "teleport", "engine_term": "x", "support": "native", "source": "page"}]),
            "a concept mapped twice": dict(concept_map=[{"concept": "key_colour_removal", "engine_term": "x", "support": "native", "source": "page"}] * 2),
            "a native claim with only a claimed source": dict(sources=[{"id": "page", "url": "https://example.test", "basis": "claimed", "retrieved": "2026-10-24"}]),
            "an unknown source": dict(concept_map=[{"concept": "key_colour_removal", "engine_term": "x", "support": "needs_custom", "source": "nowhere"}]),
            "a repeated source id": dict(sources=[{"id": "page", "url": "https://example.test", "basis": "documented", "retrieved": "2026-10-24"}] * 2),
            "a documented source without a url": dict(sources=[{"id": "page", "basis": "documented", "retrieved": "2026-10-24"}]),
            "an observed source without evidence": dict(sources=[{"id": "page", "basis": "observed", "retrieved": "2026-10-24"}]),
            "guidance citing an unknown source": dict(import_guidance=[{"topic": "t", "applies_to": "all", "text": "x", "source": "nowhere"}]),
        }
        for label, changes in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as td:
                write_profile(td, **changes)
                with self.assertRaisesRegex(ValueError, r"sample\.json"):
                    presets.engine_profiles(td)

    def test_an_observed_native_claim_is_accepted_and_a_file_must_match_its_id(self):
        with tempfile.TemporaryDirectory() as td:
            write_profile(td, sources=[{"id": "page", "basis": "observed", "retrieved": "2026-10-24", "evidence": "ran X, printed Y"}])
            self.assertIn("sample", presets.engine_profiles(td))
            (Path(td) / "other.json").write_text((Path(td) / "sample.json").read_text(), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must equal the file name"):
                presets.engine_profiles(td)

    def test_invalid_json_and_contract_violations_are_refused(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "broken.json").write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "broken.json"):
                presets.engine_profiles(td)
        with tempfile.TemporaryDirectory() as td:
            write_profile(td, extra_field=1)
            with self.assertRaisesRegex(ValueError, "sample.json"):
                presets.engine_profiles(td)

    def test_a_missing_folder_is_an_empty_set_not_an_error(self):
        self.assertEqual(presets.engine_profiles(Path(tempfile.gettempdir()) / "gamearts-no-such-folder"), {})


class GodotProfileTests(unittest.TestCase):
    """The first complete profile. Its claims stay tied to the headless run recorded under plans/enhancements/evidence."""

    OUTPUT = ROOT / "plans" / "enhancements" / "evidence" / "godot_profile_verification" / "output.json"

    def setUp(self):
        self.profile = presets.engine_profiles()["godot"]
        self.concepts = {item["concept"]: item for item in self.profile["concept_map"]}
        self.observed = json.loads(self.OUTPUT.read_text(encoding="utf-8"))

    def test_the_profile_states_what_it_was_written_against(self):
        self.assertEqual(self.profile["documented_against"]["engine_version"], "4.7")
        self.assertTrue(self.observed["godot"].startswith("4.7"))
        observed = next(s for s in self.profile["sources"] if s["basis"] == "observed")
        self.assertIn("4.7.2", observed["evidence"])

    def test_every_concept_the_framework_has_for_a_grid_layer_or_screen_is_mapped(self):
        for concept in ("atlas_frame_rect", "frame_pivot", "frame_duration", "texture_filter_pixel", "texture_filter_smooth",
                        "grid_hex_pointy", "grid_hex_flat", "grid_isometric", "parallax_layer", "screen_base_resolution", "key_colour_removal"):
            self.assertIn(concept, self.concepts)

    def test_pointy_hexagons_stagger_their_rows_and_flat_hexagons_their_columns(self):
        horizontal, vertical = self.observed["hex_offset_horizontal"], self.observed["hex_offset_vertical"]
        self.assertIn("Horizontal", self.concepts["grid_hex_pointy"]["engine_term"])
        self.assertEqual(horizontal["y+1"][0] - horizontal["origin"][0], 32)  # the next row is half a 64 px tile to the right
        self.assertEqual(horizontal["y+2"][0], horizontal["origin"][0])  # and the row after is back in line
        self.assertIn("Vertical", self.concepts["grid_hex_flat"]["engine_term"])
        self.assertEqual(vertical["x+1"][1] - vertical["origin"][1], 28)  # the next column is half a 56 px tile lower
        self.assertEqual(vertical["y+1"][0], vertical["origin"][0])

    def test_the_isometric_diamond_matches_the_framework_two_to_one_grid(self):
        iso = self.observed["iso_diamond_down"]
        self.assertEqual([iso["x+1"][0] - iso["origin"][0], iso["x+1"][1] - iso["origin"][1]], [32, 16])  # half a 64 x 32 tile across and half down
        self.assertEqual([iso["y+1"][0] - iso["origin"][0], iso["y+1"][1] - iso["origin"][1]], [-32, 16])
        self.assertIn("Diamond Down", self.concepts["grid_isometric"]["engine_term"])

    def test_durations_filter_and_parallax_claims_match_the_observation(self):
        self.assertEqual(self.observed["spriteframes"]["durations"], [1.0, 2.0])
        self.assertEqual(self.observed["atlas_region_size"], [20, 10])
        options = self.observed["settings"]["rendering/textures/canvas_textures/default_texture_filter"]
        self.assertTrue(options["hint_string"].startswith("Nearest,Linear"))
        self.assertEqual(options["default"], "1")  # Linear, which is why pixel art must change it
        self.assertIn("integer", self.observed["settings"]["display/window/stretch/scale_mode"]["hint_string"])
        self.assertEqual(set(self.observed["parallax2d"]), {"scroll_scale", "repeat_size", "autoscroll"})

    def test_a_concept_the_engine_cannot_do_by_itself_is_not_marked_native(self):
        for concept in ("frame_anchor", "direction_set", "key_colour_removal"):
            self.assertEqual(self.concepts[concept]["support"], "needs_custom", concept)

    def test_pixel_and_smooth_guidance_differ(self):
        notes = lambda family: {n["text"] for n in presets.integration_notes(settings(art_style={"id": family}, engine_target={"profile": "godot"}))}
        self.assertTrue(any("Nearest" in text for text in notes("pixel_art")))
        self.assertFalse(any("Nearest" in text for text in notes("vector")))
        self.assertTrue(any("Fix Alpha Border" in text for text in notes("vector")))

    def test_every_concept_added_for_tags_ui_curves_blends_and_tiles_is_mapped(self):
        for concept in ("animation_tag_range", "animation_tag_loop", "animation_tag_repeat_count", "animation_tag_reverse", "animation_tag_pingpong",
                        "nine_slice", "ui_state_set", "interpolation_nearest", "interpolation_linear", "interpolation_cubic", "easing_named_curves",
                        "blend_normal", "blend_additive", "blend_subtractive", "blend_multiply", "blend_screen", "blend_premultiplied",
                        "tileset_wang_corner", "tileset_wang_edge", "tileset_blob", "tileset_dual_grid", "tile_neighbour_labels", "runtime_transparency"):
            self.assertIn(concept, self.concepts)
        self.assertEqual(set(self.concepts), set(presets.CONCEPTS), "the first complete profile maps every concept the framework has")

    def test_the_named_easing_curves_are_the_engines_transitions_exactly(self):
        import build_component_bundle as bundle
        samples = self.observed["animation_key_transition_samples_at_u_0.25_0.5_0.75_of_0_to_100"]
        for name, transition in (("ease_in", "2.0"), ("ease_out", "0.5"), ("ease_in_out", "-2.0")):
            ours = [round(100 * bundle.EASINGS[name](u), 4) for u in (0.25, 0.5, 0.75)]
            self.assertEqual(ours, samples[transition], f"{name} against transition {transition}")
        self.assertEqual(self.concepts["easing_named_curves"]["support"], "native")
        self.assertEqual(samples["1.0"], [25.0, 50.0, 75.0])  # the engine's default transition is linear

    def test_nearest_and_linear_are_the_frameworks_curves_and_cubic_is_not(self):
        import build_component_bundle as bundle
        label = "animation_value_samples_at_0.1_0.25_0.4_0.5_0.75_for_keys_0_10_0_at_0_0.5_1"
        observed = self.observed[label]
        times = (0.1, 0.25, 0.4, 0.5, 0.75)

        def ours(interpolation):
            track = [{"time": 0, "position": [0, 0], "interpolation": interpolation}, {"time": 0.5, "position": [10, 0], "interpolation": interpolation}, {"time": 1, "position": [0, 0]}]
            return [round(bundle.animate(track, t, "probe")["position"][0], 4) for t in times]
        self.assertEqual(ours("linear"), observed["LINEAR"])
        self.assertEqual(ours("nearest"), observed["NEAREST"])
        self.assertNotEqual(ours("cubic"), observed["CUBIC"])
        self.assertEqual((ours("cubic")[1], observed["CUBIC"][1]), (6.25, 5.0))
        self.assertEqual([self.concepts[c]["support"] for c in ("interpolation_nearest", "interpolation_linear", "interpolation_cubic")], ["native", "native", "needs_custom"])

    def test_the_blend_modes_the_engine_lists_are_the_native_ones_and_screen_is_not_among_them(self):
        modes = self.observed["canvas_item_blend_modes"]
        self.assertEqual(set(modes), {"MIX", "ADD", "SUB", "MUL", "PREMULT_ALPHA"})
        self.assertEqual(self.observed["canvas_item_material_blend_mode_hint"], ["Mix,Add,Subtract,Multiply,Premultiplied Alpha"])
        self.assertEqual(self.observed["canvas_item_material_blend_mode_set"], modes["ADD"])
        native = {"blend_normal", "blend_additive", "blend_subtractive", "blend_multiply", "blend_premultiplied"}
        self.assertEqual({c for c, item in self.concepts.items() if c.startswith("blend_") and item["support"] == "native"}, native)
        self.assertEqual(self.concepts["blend_screen"]["support"], "needs_custom")

    def test_the_ui_states_and_nine_slice_margins_are_the_engines_names_in_the_frameworks_order(self):
        import gamearts_atlas as atlas
        self.assertEqual(self.observed["button_stylebox_names"], sorted(atlas.UI_STATES))
        self.assertEqual(self.observed["nine_patch_margins_left_top_right_bottom"], [6, 5, 4, 3])
        self.assertEqual([p for p in self.observed["nine_patch_properties"] if p.startswith("patch_margin")],
                         ["patch_margin_left", "patch_margin_top", "patch_margin_right", "patch_margin_bottom"])

    def test_each_tile_layout_exposes_exactly_the_places_a_tile_of_that_layout_labels(self):
        import gamearts_tileset as tileset
        neutral = {"top": "TOP_SIDE", "top_right": "TOP_RIGHT_CORNER", "right": "RIGHT_SIDE", "bottom_right": "BOTTOM_RIGHT_CORNER",
                   "bottom": "BOTTOM_SIDE", "bottom_left": "BOTTOM_LEFT_CORNER", "left": "LEFT_SIDE", "top_left": "TOP_LEFT_CORNER"}
        self.assertEqual(set(neutral.values()), set(self.observed["tileset_cell_neighbours"]))
        exposed = self.observed["tile_data_valid_peering_bits_by_terrain_mode"]
        for layout, mode in (("wang_corner_16", "MATCH_CORNERS"), ("wang_edge_16", "MATCH_SIDES"), ("blob_47", "MATCH_CORNERS_AND_SIDES")):
            self.assertEqual({neutral[place] for place in tileset.USED[layout]}, set(exposed[mode]), layout)
        self.assertEqual(set(self.observed["tileset_terrain_modes"]), {"MATCH_CORNERS_AND_SIDES", "MATCH_CORNERS", "MATCH_SIDES"})
        self.assertEqual([self.concepts[c]["support"] for c in ("tileset_wang_corner", "tileset_wang_edge", "tileset_blob", "tileset_dual_grid")],
                         ["native", "native", "native", "needs_custom"])

    def test_tag_playback_claims_match_the_observation(self):
        self.assertEqual(self.observed["spriteframes_walk"], {"loop": False, "speed": 12.0})
        self.assertIn("play_backwards", self.observed["animated_sprite_2d_playback_methods"])
        self.assertFalse(self.observed["animated_sprite_2d_has_pingpong_property"])
        self.assertIn("PINGPONG", self.observed["animation_loop_modes"])
        self.assertEqual([self.concepts[c]["support"] for c in ("animation_tag_loop", "animation_tag_reverse", "animation_tag_pingpong", "animation_tag_repeat_count")],
                         ["native", "native", "needs_custom", "needs_custom"])

    def test_the_profile_asks_for_runtime_copies_by_default_and_the_generic_one_for_none(self):
        self.assertEqual(self.profile["default_exports"], ["runtime"])
        self.assertNotIn("default_exports", presets.engine_profiles()["generic"])
        found = presets.resolve_engine_target(settings(engine_target={"profile": "godot"}))
        self.assertEqual(found["default_exports"], ["runtime"])
        self.assertEqual(presets.resolve_engine_target(settings(engine_target={"profile": "generic"}))["default_exports"], [])


def phaser_quad_in(v):  # src/math/easing/quadratic/In.js
    return v * v


def phaser_quad_out(v):  # src/math/easing/quadratic/Out.js
    return v * (2 - v)


def phaser_quad_inout(v):  # src/math/easing/quadratic/InOut.js, transcribed with its pre-decrement: `--v * (v - 2)` uses the decremented v
    v *= 2
    if v < 1:
        return 0.5 * v * v
    v -= 1
    return -0.5 * (v * (v - 2) - 1)


class PhaserProfileTests(unittest.TestCase):
    """A second complete profile, written from documentation and source files only (nothing was run), so every claim is `documented`."""

    def setUp(self):
        self.profile = presets.engine_profiles()["phaser"]
        self.concepts = {item["concept"]: item for item in self.profile["concept_map"]}
        self.sources = {s["id"]: s for s in self.profile["sources"]}

    def test_every_source_is_a_documented_page_or_source_file_with_an_address(self):
        for source in self.sources.values():
            self.assertEqual(source["basis"], "documented", source["id"])
            self.assertTrue(source["url"].startswith("https://"), source["id"])
        self.assertNotIn("observed", {s["basis"] for s in self.profile["sources"]})
        self.assertIn("nothing was run", self.profile["summary"])

    def test_every_mapped_concept_is_one_the_framework_has_and_every_claim_names_its_source(self):
        for concept, item in self.concepts.items():
            self.assertIn(concept, presets.CONCEPTS)
            self.assertIn(item["source"], self.sources)

    def test_the_quadratic_easings_in_phaser_s_source_are_the_frameworks_three_curves(self):
        import build_component_bundle as bundle
        for name, phaser in (("ease_in", phaser_quad_in), ("ease_out", phaser_quad_out), ("ease_in_out", phaser_quad_inout)):
            for u in (0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1):
                self.assertAlmostEqual(bundle.EASINGS[name](u), phaser(u), places=12, msg=f"{name} at {u}")
        self.assertEqual(self.concepts["easing_named_curves"]["support"], "native")

    def test_tag_direction_and_repeat_claims_follow_what_the_importer_reads(self):
        support = {c: self.concepts[c]["support"] for c in ("animation_tag_range", "animation_tag_reverse", "animation_tag_pingpong", "animation_tag_loop", "animation_tag_repeat_count")}
        self.assertEqual(support, {"animation_tag_range": "native", "animation_tag_reverse": "native", "animation_tag_pingpong": "native",
                                   "animation_tag_loop": "needs_custom", "animation_tag_repeat_count": "needs_custom"})
        self.assertIn("pingpong_reverse", self.concepts["animation_tag_pingpong"]["note"])

    def test_the_exchange_export_names_frames_the_way_the_importer_looks_them_up(self):
        import export_exchange
        import build_sheet_atlas
        from test_atlas_depth import BLOCKS, PIVOT, source_frame
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "src").mkdir()
            items = []
            for index, (box, colour) in enumerate(BLOCKS):
                source_frame(box, colour).save(root / "src" / f"f{index}.png")
                items.append({"file": f"f{index}.png", "name": f"walk_{index}", "pivot": list(PIVOT), "duration_ms": 100})
            _, atlas = build_sheet_atlas.build({"_input_dir": str(root / "src"), "name": "hero", "frames": items,
                                                "tags": [{"name": "walk", "from": 0, "to": 3, "direction": "forward"}]}, root / "out")
            written = export_exchange.export_atlas(atlas, "aseprite-hash", names="index")
            data = json.loads(Path(written).read_text(encoding="utf-8"))
        tag = data["meta"]["frameTags"][0]
        found = [data["frames"].get(str(number)) for number in range(tag["from"], tag["to"] + 1)]  # the importer's `frames[i.toString()]`
        self.assertTrue(all(found))
        self.assertTrue(all(frame["duration"] == 100 for frame in found))

    def test_nine_slice_order_differs_from_the_frameworks_and_the_profile_says_so(self):
        self.assertIn("order differs", self.concepts["nine_slice"]["note"])
        self.assertIn("leftWidth, rightWidth, topHeight, bottomHeight", self.concepts["nine_slice"]["engine_term"])

    def test_blend_modes_listed_by_the_engine_are_native_and_the_others_are_not(self):
        supported = {c: item["support"] for c, item in self.concepts.items() if c.startswith("blend_")}
        self.assertEqual(supported, {"blend_normal": "native", "blend_additive": "native", "blend_multiply": "native", "blend_screen": "native",
                                     "blend_subtractive": "needs_custom", "blend_premultiplied": "needs_custom"})

    def test_pixel_and_smooth_guidance_differ_and_runtime_copies_are_the_default(self):
        notes = lambda family: {n["text"] for n in presets.integration_notes(settings(art_style={"id": family}, engine_target={"profile": "phaser"}))}
        self.assertTrue(any("pixelArt" in text for text in notes("pixel_art")))
        self.assertFalse(any("pixelArt" in text for text in notes("vector")))
        self.assertEqual(self.profile["default_exports"], ["runtime"])


class DocumentedEngineProfileTests(unittest.TestCase):
    """Defold, GameMaker and Unity: written only from manual pages that were read, so each claim is `documented` and the profile says nothing was run."""

    ENGINES = ("defold", "gamemaker", "unity")

    def profile(self, name):
        return presets.engine_profiles()[name]

    def concepts(self, name):
        return {item["concept"]: item for item in self.profile(name)["concept_map"]}

    def test_all_three_profiles_are_installed_beside_the_others(self):
        self.assertTrue({"generic", "godot", "phaser", *self.ENGINES} <= set(presets.engine_profiles()))

    def test_every_source_is_a_documented_page_with_an_address_and_nothing_is_claimed_as_run(self):
        for name in self.ENGINES:
            profile = self.profile(name)
            self.assertTrue(profile["sources"], name)
            for source in profile["sources"]:
                self.assertEqual(source["basis"], "documented", (name, source["id"]))
                self.assertTrue(source["url"].startswith("https://"), (name, source["id"]))
            self.assertIn("nothing was run", profile["summary"], name)

    def test_every_mapped_concept_exists_in_the_framework_and_cites_a_source_of_its_profile(self):
        for name in self.ENGINES:
            sources = {s["id"] for s in self.profile(name)["sources"]}
            for concept, item in self.concepts(name).items():
                self.assertIn(concept, presets.CONCEPTS, (name, concept))
                self.assertIn(item["source"], sources, (name, concept))

    def test_defold_flipbook_modes_cover_forward_backward_ping_pong_and_once_or_loop_but_not_a_count(self):
        support = {c: item["support"] for c, item in self.concepts("defold").items()}
        for concept in ("animation_tag_range", "animation_tag_loop", "animation_tag_reverse", "animation_tag_pingpong"):
            self.assertEqual(support[concept], "native", concept)
        self.assertEqual(support["animation_tag_repeat_count"], "needs_custom")
        self.assertEqual(support["frame_duration"], "needs_custom")  # one Fps per animation
        self.assertIn("pingpong_reverse", self.concepts("defold")["animation_tag_pingpong"]["note"])
        self.assertIn("1 added", self.concepts("defold")["animation_tag_range"]["note"])  # tiles are numbered from 1, frames from 0

    def test_defold_slice_nine_uses_the_frameworks_own_margin_order(self):
        self.assertIn("left, top, right, bottom", self.concepts("defold")["nine_slice"]["engine_term"])
        self.assertIn("The order is the framework's", self.concepts("defold")["nine_slice"]["note"])

    def test_defold_blend_modes_are_the_four_the_sprite_manual_lists(self):
        support = {c: item["support"] for c, item in self.concepts("defold").items() if c.startswith("blend_")}
        self.assertEqual(support, {"blend_normal": "native", "blend_additive": "native", "blend_multiply": "native", "blend_screen": "native",
                                   "blend_subtractive": "needs_custom", "blend_premultiplied": "needs_custom"})

    def test_gamemaker_maps_only_what_its_pages_state(self):
        concepts = self.concepts("gamemaker")
        self.assertEqual({c for c in concepts}, {"frame_pivot", "frame_duration", "nine_slice", "blend_normal", "blend_additive", "blend_subtractive", "tileset_blob"})
        self.assertEqual(concepts["frame_duration"]["support"], "needs_custom")
        self.assertIn("does not state an order", concepts["nine_slice"]["note"])
        self.assertIn("by hand", concepts["tileset_blob"]["note"])

    def test_unity_maps_grid_slicing_filters_borders_and_the_alpha_option(self):
        concepts = self.concepts("unity")
        self.assertEqual({c: item["support"] for c, item in concepts.items()},
                         {"atlas_frame_rect": "native", "frame_pivot": "native", "nine_slice": "native", "texture_filter_pixel": "native",
                          "texture_filter_smooth": "native", "runtime_transparency": "native"})
        self.assertIn("Grid By Cell Size", concepts["atlas_frame_rect"]["engine_term"])
        self.assertIn("differs from the framework", concepts["nine_slice"]["note"])
        self.assertIn("Full Rect", concepts["nine_slice"]["note"])

    def test_pixel_and_smooth_guidance_reach_a_game_that_names_the_engine(self):
        notes = lambda engine, family: {n["text"] for n in presets.integration_notes(settings(art_style={"id": family}, engine_target={"profile": engine}))}
        self.assertTrue(any("Point (no filter)" in text for text in notes("unity", "pixel_art")))
        self.assertFalse(any("Point (no filter)" in text for text in notes("unity", "vector")))
        for engine in self.ENGINES:
            self.assertEqual(self.profile(engine)["default_exports"], ["runtime"], engine)
            self.assertTrue(notes(engine, "pixel_art"), engine)


class EngineTargetResolutionTests(unittest.TestCase):
    def test_a_project_that_names_no_engine_gets_the_generic_profile(self):
        result = presets.resolve_engine_target(settings())
        self.assertEqual((result["profile"], result["defaulted"], result["found"]), (presets.GENERIC, True, True))

    def test_a_named_profile_that_is_installed_is_found(self):
        with tempfile.TemporaryDirectory() as td:
            write_profile(td, id="sample", documented_against={"engine_version": "1.2", "retrieved": "2026-10-24"})
            result = presets.resolve_engine_target(settings(engine_target={"profile": "sample", "version_note": "1.2"}), td)
            self.assertEqual((result["profile"], result["found"], result["defaulted"], result["version_note"]), ("sample", True, False, "1.2"))
            self.assertEqual(result["documented_against"]["engine_version"], "1.2")

    def test_a_named_profile_that_is_not_installed_is_reported_and_never_an_error(self):
        result = presets.resolve_engine_target(settings(engine_target={"profile": "some-other-engine"}))
        self.assertFalse(result["found"])
        self.assertIn("engine-neutral", result["message"])

    def test_a_damaged_profile_folder_is_reported_in_the_result(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "broken.json").write_text("{not json", encoding="utf-8")
            result = presets.resolve_engine_target(settings(), td)
            self.assertFalse(result["found"])
            self.assertIn("broken.json", result["problem"])

    def test_integration_notes_follow_the_art_style_family(self):
        pixel = {note["text"] for note in presets.integration_notes(settings(art_style={"id": "pixel_art"}))}
        smooth = {note["text"] for note in presets.integration_notes(settings(art_style={"id": "vector"}))}
        self.assertTrue(any("nearest-neighbour" in text for text in pixel))
        self.assertFalse(any("linear filtering" in text for text in pixel))
        self.assertTrue(any("linear filtering" in text for text in smooth))
        self.assertFalse(any("nearest-neighbour" in text for text in smooth))
        self.assertTrue(any("#FF00FF" in text for text in pixel & smooth))

    def test_a_style_preset_is_resolved_or_reported_missing(self):
        self.assertIsNone(presets.resolve_style_preset(settings()))
        found = presets.resolve_style_preset(settings(art_style={"id": "pixel_art", "preset": "pixel_mid"}))
        self.assertTrue(found["found"])
        self.assertIn("pixel_grid", found["required_checks"])
        missing = presets.resolve_style_preset(settings(art_style={"id": "pixel_art", "preset": "not-installed"}))
        self.assertFalse(missing["found"])
        self.assertIn("keeps the policy values", missing["message"])

    def test_a_damaged_style_preset_folder_is_reported_in_the_result(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "broken.json").write_text("{not json", encoding="utf-8")
            result = presets.resolve_style_preset(settings(art_style={"id": "pixel_art", "preset": "x"}), td)
            self.assertFalse(result["found"])
            self.assertIn("broken.json", result["problem"])


class CheckSettingsTests(unittest.TestCase):
    def test_check_settings_reports_the_world_kind_directions_engine_and_preset(self):
        with tempfile.TemporaryDirectory() as td:
            write_settings(td, directions="dirs_4", engine_target={"profile": "generic"}, art_style={"id": "pixel_art", "preset": "pixel_low"})
            result = lifecycle.check_settings(td)
            self.assertEqual(result["world_kind"], "grid_world")
            self.assertEqual(result["directions"], ["S", "W", "N", "E"])
            self.assertEqual((result["engine_target"]["profile"], result["engine_target"]["found"]), ("generic", True))
            self.assertEqual(result["style_preset"]["preset"], "pixel_low")
            self.assertTrue(any("nearest-neighbour" in note["text"] for note in result["integration_notes"]))

    def test_changing_the_engine_target_changes_the_guidance_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as td:
            write_settings(td)
            before = lifecycle.check_settings(td)
            write_settings(td, engine_target={"profile": "an-engine-with-no-profile"})
            after = lifecycle.check_settings(td)
            self.assertEqual(before["material_settings_sha256"], after["material_settings_sha256"])
            self.assertEqual(before["owner_confirmed"], after["owner_confirmed"])
            self.assertTrue(before["engine_target"]["found"])
            self.assertFalse(after["engine_target"]["found"])

    def test_an_engine_target_change_flags_no_approved_art(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_settings(root)
            image, metadata = kit.make_mockup(root)
            lifecycle.register_mockup(root, metadata)
            lifecycle.approve_mockup(root, "test-scene", "v001", "approved in test")
            write_settings(root, engine_target={"profile": "generic", "version_note": "anything"})
            notes = []
            self.assertEqual(lifecycle.audit_mockup(root, "test-scene", "v001", notes), [])
            self.assertEqual(notes, [])

    def test_a_screen_space_game_reports_its_screen(self):
        with tempfile.TemporaryDirectory() as td:
            write_settings(td, world_kind="screen_space", screen={"base_resolution_px": [1280, 720]}, drop=("world", "directions"))
            result = lifecycle.check_settings(td)
            self.assertEqual((result["world_kind"], result["directions"], result["screen"]["base_resolution_px"]), ("screen_space", [], [1280, 720]))


class CropPromptTests(unittest.TestCase):
    """The preset's `avoid` lines reach the prompt the image tool actually receives."""

    def crop(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("prepare_reference_crop", ROOT / "scripts" / "prepare_reference_crop.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def prompt_for(self, **overrides):
        crop = self.crop()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = kit.crop_game(root, "prop", **overrides)
            packet_file = kit.crop_prepare(crop, root, job)
            return (packet_file.parent / "reference.prompt.txt").read_text(encoding="utf-8")

    def test_the_avoid_lines_of_the_saved_preset_are_in_the_prompt(self):
        preset = presets.style_presets()["pixel_mid"]
        prompt = self.prompt_for(art_style=dict(preset["art_style"], preset="pixel_mid"))
        self.assertIn("AVOID (from the saved style preset pixel_mid)", prompt)
        for line in preset["avoid"]:
            self.assertIn(line, prompt)

    def test_a_project_without_a_preset_gets_no_avoid_line(self):
        self.assertNotIn("AVOID", self.prompt_for())

    def test_a_preset_that_is_not_installed_adds_nothing_and_blocks_nothing(self):
        prompt = self.prompt_for(art_style={"id": "pixel_art", "preset": "not-installed"})
        self.assertNotIn("AVOID", prompt)

    def test_a_damaged_preset_blocks_the_prompt_instead_of_dropping_its_rules(self):
        crop = self.crop()
        damaged = {"preset": "x", "found": False, "problem": "styles/broken.json: not json"}
        original = crop.presets.resolve_style_preset
        crop.presets.resolve_style_preset = lambda settings, folder=None: damaged
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                job = kit.crop_game(root, "prop", art_style={"id": "pixel_art", "preset": "x"})
                with self.assertRaisesRegex(ValueError, "style preset cannot be read"):
                    kit.crop_prepare(crop, root, job)
        finally:
            crop.presets.resolve_style_preset = original


class GenreRecipeTests(unittest.TestCase):
    """docs/GENRE_RECIPES.md is guidance; every name it uses must still be something the framework has."""

    def setUp(self):
        self.text = (ROOT / "docs" / "GENRE_RECIPES.md").read_text(encoding="utf-8")
        import importlib.util
        spec = importlib.util.spec_from_file_location("prepare_reference_crop", ROOT / "scripts" / "prepare_reference_crop.py")
        crop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(crop)
        self.known = set(presets.style_presets()) | set(common.DIRECTION_SETS) | set(common.WORLD_KINDS) | crop.CLASSES

    def test_every_code_name_in_the_recipes_is_a_real_preset_direction_set_world_kind_or_asset_class(self):
        for token in set(re.findall(r"`([a-z0-9_]+)`", self.text)):
            self.assertIn(token, self.known, f"GENRE_RECIPES.md names `{token}`, which the framework does not have")

    def test_there_are_twelve_recipes_and_each_row_names_a_world_a_look_and_something_to_make(self):
        rows = [line for line in self.text.splitlines() if line.startswith("| ") and not line.startswith(("| Genre", "|---"))]
        self.assertEqual(len(rows), 12)
        for row in rows:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            self.assertEqual(len(cells), 6, row)
            self.assertTrue(re.search(r"`(grid_world|free_world|layered_scene|screen_space)`", cells[1]), row)
            self.assertTrue(re.search(r"`(\w+)`", cells[2]), row)

    def test_every_world_kind_is_served_by_at_least_one_recipe(self):
        for kind in common.WORLD_KINDS:
            self.assertIn(f"`{kind}`", self.text)

    def test_every_style_preset_is_suggested_by_at_least_one_recipe(self):
        for name in presets.style_presets():
            self.assertIn(f"`{name}`", self.text, f"no recipe suggests the preset {name}")


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_list_names_every_installed_entry(self):
        for kind, expected in (("styles", presets.style_presets()), ("engines", presets.engine_profiles())):
            result = self.run_cli("list", "--kind", kind)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({item["id"] for item in json.loads(result.stdout)}, set(expected))

    def test_the_style_list_can_be_filtered_by_world_kind_and_camera(self):
        everything = {item["id"] for item in json.loads(self.run_cli("list", "--kind", "styles").stdout)}
        custom = {item["id"] for item in json.loads(self.run_cli("list", "--kind", "styles", "--camera", "custom").stdout)}
        self.assertLess(custom, everything)
        self.assertIn("cel_shaded", custom)
        self.assertNotIn("pixel_mid", custom)
        self.assertEqual(custom, {name for name, p in presets.style_presets().items() if "custom" in p["cameras"]})
        screen = {item["id"] for item in json.loads(self.run_cli("list", "--kind", "styles", "--world-kind", "screen_space").stdout)}
        self.assertEqual(screen, {name for name, p in presets.style_presets().items() if "screen_space" in p["world_kinds"]})

    def test_a_filter_on_engine_profiles_is_refused_not_ignored(self):
        result = self.run_cli("list", "--kind", "engines", "--camera", "side")
        self.assertEqual(result.returncode, 1)
        self.assertIn("style presets only", result.stderr)

    def test_show_prints_one_entry_and_an_unknown_id_is_blocked(self):
        shown = self.run_cli("show", "--kind", "styles", "--id", "pixel_mid")
        self.assertEqual(json.loads(shown.stdout)["id"], "pixel_mid")
        missing = self.run_cli("show", "--kind", "engines", "--id", "nothing")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("BLOCKED", missing.stderr)
        self.assertIn("generic", missing.stderr)


if __name__ == "__main__":
    unittest.main()
