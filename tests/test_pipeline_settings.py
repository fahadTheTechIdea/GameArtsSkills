"""The game's saved settings are used by every stage they belong to.

Three guards keep that true. Every script either reads the game's settings or says why it does not; every field of project.json names the stage
that reads it (or says why it is only a record); and each stage that was found ignoring a setting is driven here with a changed setting to show
the setting changes what it does.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import EIGHT, crop_game, crop_prepare, settings as base_settings, write_settings
from test_variant_lifecycle import OUT, SheetCase, run

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_plan_card as card  # noqa: E402
import gamearts_report as report  # noqa: E402
import gamearts_setup as wizard  # noqa: E402
import prepare_reference_crop as crop  # noqa: E402
import validate_settings_fit as fit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
READS_SETTINGS = re.compile(r"load_project_settings\(|settings_fit\.announce\(|def \w+\([^)]*\bsettings\b")

# Scripts that do not read the game's settings, and why. A script that starts reading them must leave this list (a test fails while it stays).
INDEPENDENT = {
    "gamearts_common": "the library that loads and validates the settings for every other script",
    "gamearts_setup": "the wizard that writes the settings",
    "gamearts_atlas": "frame and pivot geometry of one sheet; no fact of the game goes into it",
    "gamearts_matte": "the soft-edge coverage rules of one sheet; whether a look gets a matte is decided at the technical gate from the game's preset",
    "gamearts_pixelgrid": "measures the pixel grid of one picture; the density the game wants is checked by validate_style_conformance",
    "gamearts_tileset": "the layout rules of one tileset; its size is compared with the game's ground tile by validate_settings_fit",
    "validate_sheet_atlas": "checks one sheet against its own atlas and the exact-key rule; the game's facts are applied at the technical gate",
    "validate_component_bundle": "checks one bundle against its own contract; the game's facts are applied at the technical gate",
    "validate_tileset": "checks one tileset against its own labels; the game's facts are applied at the technical gate",
    "validate_parent_cleanup": "checks one cleaned parent picture against its removed parts",
    "visual_review_cleanup": "builds the review boards of one cleaned parent picture",
    "export_runtime": "derives engine-ready copies; which exports a game gets is decided from its engine profile by the lifecycle, which calls it",
    "export_exchange": "converts one sheet or tileset to the format the owner names with --format; no engine profile names one",
    "gamearts_disclosure": "summarises what the asset records say about AI use; the tool behind each picture is recorded on the asset",
    "gamearts_storyboard": "records the story before any scene mockup; the settings gate applies when its scenes are registered",
    "detect_scene_objects": "analyses one approved picture; the settings are not an input",
    "extract_scene_objects": "cuts out the objects of one approved picture; the settings are not an input",
    "evaluate_extraction": "scores a draft against a reviewed reference; the settings are not an input",
    "remove_scene_objects": "infers a clean parent from one approved picture; the settings are not an input",
    "validate_blueprint": "checks a scene blueprint against its own contract",
    "sync_local_agents": "installs the framework into a game; it never reads or writes the game's art settings",
    "slice_generated_strip": "cuts and measures one picture an image tool returned; the camera, the directions and the style were applied when its prompt was written by gamearts_direction_prompt",
    "gamearts_candidates": "keeps and measures what an image tool returned, with the prompt that made it; it needs the game's project.json to exist, and the settings were applied when the prompt was written by gamearts_direction_prompt",
    "gamearts_approval": "shows the owner the pictures of a request and takes their decision; the request file, not the settings, says what is asked",
    "gamearts_local_page": "the local page server the approval form and the settings page run on; it serves a page and reads no game fact",
    "gamearts_setup_form": "the settings wizard as a page; every question and answer goes through gamearts_setup, the one owner of the settings",
}

# Fields of project.json that no stage decides from, and why. The rest are in CONSUMERS.
RECORD_ONLY = {
    "schema_version": "the format marker the schema validates",
    "confirmed_at": "the owner's confirmation record, written by confirm-settings; the gate reads settings_status",
    "confirmed_by": "the owner's confirmation record, written by confirm-settings; the gate reads settings_status",
    "world.construction_snap_m": "the game's own placement grid in metres, kept for its engine side; no art stage places objects",
    "animation.animated_attachment_anchors": "fixed to true by the schema; the component gate always requires a named mount for a child part",
    "workflow.mockup_approval_required": "fixed to true by the schema; the lifecycle requires an approved mockup for every game",
    "workflow.detail_decomposition_required": "fixed to true by the schema; the lifecycle and the component gate apply for every game",
    "export.background_hex": "fixed by the schema to the framework's key colour, which common.KEY_HEX applies to every game",
    "export.background_alpha": "fixed by the schema; the exact-key pixel contract applies to every game",
    "export.atlas_per_sheet": "fixed to true by the schema; every sheet gets a measured atlas for every game",
    "export.no_zip": "fixed to true by the schema; deliveries are individual files for every game",
}

# Field -> (script that reads it, text that proves it does).
CONSUMERS = {
    "project_id": ("gamearts_asset_lifecycle.py", '"project_id"'),
    "settings_status": ("gamearts_common.py", "settings_status"),
    "art_style.id": ("gamearts_presets.py", 'settings["art_style"]["id"]'),
    "art_style.reference": ("prepare_reference_crop.py", '"id", "reference", "palette_reference"'),
    "art_style.palette_reference": ("gamearts_palette.py", "palette_reference"),
    "art_style.outline_policy": ("prepare_reference_crop.py", "outline_policy"),
    "art_style.shading_policy": ("prepare_reference_crop.py", "shading_policy"),
    "art_style.texture_policy": ("prepare_reference_crop.py", "texture_policy"),
    "art_style.pixel_density": ("prepare_reference_crop.py", "pixel_density"),
    "art_style.ui_camera": ("prepare_reference_crop.py", "ui_camera"),
    "art_style.preset": ("gamearts_presets.py", 'get("preset")'),
    "art_style.anchor.mockup_id": ("gamearts_common.py", "def resolve_style_anchor"),
    "art_style.anchor.revision": ("gamearts_common.py", "def resolve_style_anchor"),
    "world.grid": ("gamearts_asset_lifecycle.py", 'get("grid")'),
    "world.camera_profile": ("gamearts_report.py", "camera_profile"),
    "world.object_camera": ("prepare_reference_crop.py", "object_camera"),
    "world.ground_camera": ("prepare_reference_crop.py", "ground_camera"),
    "world.logical_tile_m": ("gamearts_asset_lifecycle.py", "logical_tile_m"),
    "world.ground_tile_px": ("validate_settings_fit.py", "ground_tile_px"),
    "world.pixels_per_meter": ("validate_settings_fit.py", "pixels_per_meter"),
    "world.layers": ("prepare_reference_crop.py", "world_layers"),
    "directions": ("validate_settings_fit.py", "resolve_directions"),
    "animation.preferred_method": ("gamearts_plan_card.py", "preferred_method"),
    "image_generation.tool": ("gamearts_plan_card.py", 'chosen["tool"]'),
    "image_generation.tool_name": ("gamearts_plan_card.py", "tool_name"),
    "image_generation.notes": ("gamearts_doctor.py", "generator['notes']"),
    "image_generation.fallback.tool": ("gamearts_doctor.py", "spare['tool']"),
    "image_generation.fallback.tool_name": ("gamearts_doctor.py", "spare['tool_name']"),
    "image_generation.fallback.notes": ("gamearts_doctor.py", "spare['notes']"),
    "prompting.reference_lock": ("prepare_reference_crop.py", 'prompting["reference_lock"]'),
    "prompting.strict_camera_lock": ("prepare_reference_crop.py", 'prompting["strict_camera_lock"]'),
    "prompting.single_master_first": ("prepare_reference_crop.py", 'prompting["single_master_first"]'),
    "prompting.additional_constraints": ("prepare_reference_crop.py", 'prompting["additional_constraints"]'),
    "world_kind": ("prepare_reference_crop.py", "world_kind"),
    "screen.base_resolution_px": ("prepare_reference_crop.py", "base_resolution_px"),
    "screen.scaling": ("render_preview.py", "scaling"),
    "engine_target.profile": ("gamearts_presets.py", "def resolve_engine_target"),
    "engine_target.version_note": ("gamearts_report.py", "version_note"),
}


PROJECT_SCHEMA = common.read_json(ROOT / "schemas" / "gamearts-project.schema.json")


def _shape(body):
    """The object shape of a field: a local $ref is followed, and a field that may be one object or a list of them (oneOf) is read by the object's own
    fields, so a setting kept in two shapes is still checked field by field."""
    while isinstance(body, dict) and "properties" not in body:
        if "$ref" in body:
            target = PROJECT_SCHEMA
            for step in body["$ref"].removeprefix("#/").split("/"):
                target = target[step]
            body = target
        elif "oneOf" in body:
            arms = [_shape(arm) for arm in body["oneOf"]]
            return next((arm for arm in arms if isinstance(arm, dict) and "properties" in arm), body)
        else:
            break
    return body


def schema_fields(properties=None, prefix=""):
    """Every leaf field of project.json that the schema declares, as a dotted path."""
    properties = PROJECT_SCHEMA["properties"] if properties is None else properties
    for name, body in properties.items():
        body = _shape(body)
        if isinstance(body, dict) and "properties" in body:
            yield from schema_fields(body["properties"], prefix + name + ".")
        else:
            yield prefix + name


class EveryScriptTests(unittest.TestCase):
    def test_every_script_reads_the_games_settings_or_says_why_it_does_not(self):
        names = sorted(path.stem for path in SCRIPTS.glob("*.py"))
        silent = [name for name in names if name not in INDEPENDENT and not READS_SETTINGS.search((SCRIPTS / f"{name}.py").read_text(encoding="utf-8"))]
        self.assertEqual(silent, [], "these scripts neither read the game's settings nor appear in INDEPENDENT with a reason")

    def test_an_excuse_is_removed_once_the_script_reads_the_settings(self):
        stale = [name for name, _ in INDEPENDENT.items()
                 if not (SCRIPTS / f"{name}.py").is_file() or READS_SETTINGS.search((SCRIPTS / f"{name}.py").read_text(encoding="utf-8"))
                 and name not in ("gamearts_common", "gamearts_setup")]
        self.assertEqual(stale, [], "these scripts are listed as independent but are missing or now read the settings")


class EveryFieldTests(unittest.TestCase):
    def test_every_field_of_project_json_is_read_by_a_stage_or_is_only_a_record(self):
        fields = set(schema_fields())
        self.assertEqual(sorted(fields - set(CONSUMERS) - set(RECORD_ONLY)), [],
                         "these fields are saved and read by nothing: name the stage that reads each in CONSUMERS, or say in RECORD_ONLY why none should")
        self.assertEqual(sorted((set(CONSUMERS) | set(RECORD_ONLY)) - fields), [], "these names are no longer fields of project.json")
        self.assertEqual(sorted(set(CONSUMERS) & set(RECORD_ONLY)), [])

    def test_each_named_reader_really_contains_the_reading(self):
        for field, (script, text) in CONSUMERS.items():
            with self.subTest(field=field):
                self.assertTrue(text in (SCRIPTS / script).read_text(encoding="utf-8"), f"{script} no longer reads {field} ({text!r} is gone)")

    def test_a_record_only_field_gives_its_reason(self):
        self.assertTrue(all(len(reason) > 20 for reason in RECORD_ONLY.values()))


class ReferencePromptTests(unittest.TestCase):
    """The reference stage puts the game's prompt preferences and its scrolling layer into the prompt, and the packet records what was used."""

    def prepare(self, asset_class="static_structure", job=None, **overrides):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        body = crop_game(root, asset_class, **overrides)
        body.update(job or {})
        packet_file = crop_prepare(crop, root, body)
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
        return (packet_file.parent / packet["prompt_path"]).read_text(encoding="utf-8"), packet

    def test_with_nothing_turned_off_the_wording_is_the_standard_wording(self):
        prompt, packet = self.prepare()
        self.assertIn("TASK: Produce exactly ONE static_structure master candidate for thing_v001; not a sprite sheet.", prompt)
        for line in ("Use the ATTACHED crop as the authority, not a generic style description.",
                     "Do not alter viewpoint, object identity, proportions or previously approved features.",
                     "Do not invent hidden wall details without design approval.",
                     "No multi-view contact sheets, alternate camera, labels, UI, frames, or printed JSON."):
            self.assertIn(line, prompt)
        self.assertNotIn("PROJECT CONSTRAINTS", prompt)
        self.assertEqual(packet["resolved_prompting"],
                         {"reference_lock": True, "strict_camera_lock": True, "single_master_first": True, "additional_constraints": []})

    def test_the_owners_constraints_reach_the_prompt_and_the_packet(self):
        rule = wizard.SOFT_EDGE_RULES["hard"]  # the very sentence the setup wizard saves for a look with hard edges
        prompt, packet = self.prepare(prompting={"additional_constraints": [rule, "No text on signs."]})
        self.assertIn(f"PROJECT CONSTRAINTS (from the saved game settings): {rule} No text on signs.", prompt)
        self.assertEqual(packet["resolved_prompting"]["additional_constraints"], [rule, "No text on signs."])

    def test_a_switch_the_owner_turned_off_removes_only_its_own_wording(self):
        prompt, packet = self.prepare(prompting={"reference_lock": False})
        self.assertNotIn("Use the ATTACHED crop as the authority", prompt)
        self.assertIn("Do not alter viewpoint, object identity", prompt)
        self.assertFalse(packet["resolved_prompting"]["reference_lock"])

        prompt, _ = self.prepare(prompting={"strict_camera_lock": False})
        self.assertIn("Do not alter object identity, proportions or previously approved features.", prompt)
        self.assertNotIn("Do not alter viewpoint", prompt)
        self.assertIn("No multi-view contact sheets, labels, UI, frames, or printed JSON.", prompt)

        prompt, _ = self.prepare(prompting={"single_master_first": False})
        self.assertIn("TASK: Produce the static_structure candidate for thing_v001.", prompt)
        self.assertIn("No alternate camera, labels, UI, frames, or printed JSON.", prompt)


class ScrollingLayerTests(unittest.TestCase):
    LAYERS = [{"id": "sky", "scroll_scale": [0.1, 0]},
              {"id": "hills", "scroll_scale": [0.4, 0], "repeat_px": [1024, 0], "autoscroll_px_per_s": [4, 0]},
              {"id": "ground", "scroll_scale": [1, 1]}]
    WORLD = {"camera_profile": "side", "object_camera": "side view orthographic", "pixels_per_meter": 32, "layers": LAYERS}

    def prepare(self, asset_class="parallax_layer", job=None, world=WORLD, **overrides):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        body = crop_game(root, asset_class, world_kind="layered_scene", world=world, **overrides)
        body.update(job or {})
        packet_file = crop_prepare(crop, root, body)
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
        return (packet_file.parent / packet["prompt_path"]).read_text(encoding="utf-8"), packet

    def test_a_game_with_layers_must_be_told_which_layer_the_picture_is(self):
        with self.assertRaisesRegex(ValueError, r"sky, hills, ground\): name this picture's layer"):
            self.prepare()

    def test_a_layer_the_game_does_not_have_is_refused(self):
        with self.assertRaisesRegex(ValueError, "'clouds' is not one of the game's layers"):
            self.prepare(job={"layer_id": "clouds"})

    def test_the_layers_scroll_and_repeat_go_into_the_prompt_and_the_packet(self):
        prompt, packet = self.prepare(job={"layer_id": "hills"})
        self.assertIn("SCROLLING LAYER FROM SAVED GAME SETTINGS: hills; it moves 0.4 across and 0 down for each unit the camera moves (below 1 is farther away).", prompt)
        self.assertIn("It repeats every 1024 px across and 0 px down", prompt)
        self.assertEqual(packet["resolved_layer"]["id"], "hills")
        prompt, _ = self.prepare(job={"layer_id": "sky"})
        self.assertNotIn("It repeats", prompt)  # a layer that does not repeat is not asked to

    def test_a_layer_is_named_only_for_a_parallax_picture_in_a_game_that_has_layers(self):
        with self.assertRaisesRegex(ValueError, "applies only to a parallax_layer"):
            self.prepare("prop", job={"layer_id": "sky"})
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        body = crop_game(Path(tmp.name), "parallax_layer")  # an ordinary game: no layers to name
        body["layer_id"] = "sky"
        with self.assertRaisesRegex(ValueError, "applies only to a parallax_layer"):
            crop_prepare(crop, Path(tmp.name), body)


class PlanCardMethodTests(unittest.TestCase):
    def plan(self, method, **work):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_settings(Path(tmp.name), animation={"preferred_method": method, "animated_attachment_anchors": True})
        return card.plan(tmp.name, "mobile_directional", **work)

    def test_the_card_states_the_saved_method_and_says_when_the_plan_goes_against_it(self):
        frames = self.plan("frame_based", actions=1, frames_per_action=4, detachable_parts=2, rig_by_transform=True)
        self.assertEqual(frames["animation_method"], "frame_based")
        self.assertIn("saved animation method is frame-based", frames["message"])
        transform = self.plan("transform_based", actions=1, frames_per_action=4, detachable_parts=2)
        self.assertIn("saved animation method is transform-based", transform["message"])
        self.assertIn("--rig-by-transform", transform["message"])

    def test_a_plan_that_agrees_with_the_method_has_nothing_to_add(self):
        for method, work in (("frame_based", dict(actions=1, frames_per_action=4)),
                             ("transform_based", dict(actions=1, frames_per_action=4, detachable_parts=2, rig_by_transform=True)),
                             ("hybrid", dict(actions=1, frames_per_action=4, detachable_parts=2)),
                             ("hybrid", dict(actions=1, frames_per_action=4, detachable_parts=2, rig_by_transform=True))):
            with self.subTest(method=method, work=work):
                self.assertNotIn("saved animation method", self.plan(method, **work)["message"])


class SettingsFitTests(unittest.TestCase):
    def folder(self, **files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, body in files.items():
            (Path(tmp.name) / name).write_text(json.dumps(body), encoding="utf-8")
        return Path(tmp.name)

    def checks(self, folder, **overrides):
        return fit.fit_report(folder, base_settings(**overrides))

    def test_a_bundle_must_face_the_games_directions_unless_it_has_one_view(self):
        same = self.checks(self.folder(**{"hero.bundle.json": {"directions": list(reversed(EIGHT))}}))
        self.assertEqual((same["status"], same["checks"][0]["name"]), ("passed", "directions"))
        four = self.checks(self.folder(**{"hero.bundle.json": {"directions": EIGHT[:4]}}))
        self.assertEqual(four["status"], "mismatch")
        self.assertIn("limited profile", four["checks"][0]["detail"])
        one = self.checks(self.folder(**{"door.bundle.json": {"directions": ["fixed"]}}))
        self.assertEqual(one["status"], "not_applicable")
        none = self.checks(self.folder(**{"hero.bundle.json": {"directions": EIGHT}}), drop=("directions",))
        self.assertEqual(none["status"], "mismatch")
        self.assertIn("declares no facing directions", none["checks"][0]["detail"])

    def test_a_ground_tileset_must_use_the_games_ground_tile(self):
        self.assertEqual(self.checks(self.folder(**{"grass.tileset.json": {"tile_size": [256, 256]}}))["status"], "passed")
        wrong = self.checks(self.folder(**{"grass.tileset.json": {"tile_size": [128, 128]}}))
        self.assertEqual(wrong["status"], "mismatch")
        self.assertIn("tiles are 128x128, but the game's ground tile is 256x256", wrong["checks"][0]["detail"])
        objects = self.checks(self.folder(**{"props.tileset.json": {"tile_size": [64, 64], "full_bleed": False}}))
        self.assertEqual(objects["status"], "not_applicable")
        world = {k: v for k, v in base_settings()["world"].items() if k != "ground_tile_px"}
        self.assertEqual(self.checks(self.folder(**{"grass.tileset.json": {"tile_size": [128, 128]}}), world=world)["status"], "not_applicable")

    def test_a_sheet_that_records_its_scale_must_match_the_games(self):
        self.assertEqual(self.checks(self.folder(**{"a.atlas.json": {"pixels_per_meter": 16}}))["status"], "passed")
        wrong = self.checks(self.folder(**{"a.atlas.json": {"pixels_per_meter": 32}}))
        self.assertEqual(wrong["status"], "mismatch")
        self.assertIn("records 32 pixels per metre, but the game's scale is 16", wrong["checks"][0]["detail"])
        unrecorded = self.checks(self.folder(**{"a.atlas.json": {"pixels_per_meter": None}}))
        self.assertEqual((unrecorded["status"], unrecorded["checks"]), ("not_applicable", []))  # nothing to compare, nothing claimed

    def test_settings_that_could_not_be_read_are_reported_as_untested_with_the_reason(self):
        result = fit.fit_report(self.folder(), None, "project.json is damaged")
        self.assertEqual((result["status"], result["reason"]), ("untested", "project.json is damaged"))

    def test_the_command_line_exits_with_status_one_on_a_mismatch(self):
        game = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(game, ignore_errors=True))
        write_settings(game)
        for body, code in (({"pixels_per_meter": 32}, 1), ({"pixels_per_meter": 16}, 0)):
            folder = self.folder(**{"a.atlas.json": body})
            done = subprocess.run([sys.executable, str(SCRIPTS / "validate_settings_fit.py"), "--game-root", str(game), "--folder", str(folder)],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, code, done.stdout + done.stderr)


class BuilderAndGateTests(SheetCase):
    """A sheet built for a game of another scale is reported by the builder and by the technical gate, and never blocks."""

    def sheet(self, scale):
        self.built = getattr(self, "built", 0) + 1
        frames = self.frames(self.root / "work" / f"frames_{self.built}")
        job_file = self.sheet_job("hero_v001", frames)
        job = json.loads(job_file.read_text(encoding="utf-8"))
        job["pixels_per_meter"] = scale
        job_file.write_text(json.dumps(job), encoding="utf-8")
        return job_file

    def test_the_builder_says_whether_the_new_sheet_fits_the_game(self):
        wrong = run("build_sheet_atlas.py", self.sheet(32), "--output-dir", self.bundle("hero_v001"), "--game-root", self.root).stdout
        self.assertIn("SETTINGS FIT mismatch", wrong)
        self.assertIn("MISMATCH (scale)", wrong)
        right = run("build_sheet_atlas.py", self.sheet(16), "--output-dir", self.bundle("hero_v002"), "--game-root", self.root).stdout
        self.assertIn("SETTINGS FIT passed", right)
        silent = run("build_sheet_atlas.py", self.sheet(16), "--output-dir", self.bundle("hero_v003")).stdout
        self.assertNotIn("SETTINGS FIT", silent)  # without a game there is nothing to compare with

    def test_a_builder_whose_game_has_unreadable_settings_says_so_and_still_succeeds(self):
        (self.root / ".gamearts" / "project.json").write_text("{ not json", encoding="utf-8")
        said = run("build_sheet_atlas.py", self.sheet(16), "--output-dir", self.bundle("hero_v001"), "--game-root", self.root).stdout
        self.assertIn("SETTINGS FIT untested", said)
        self.assertIn("BUILT", said)

    def test_the_gate_records_the_fit_without_blocking_and_the_report_shows_the_mismatch(self):
        run("build_sheet_atlas.py", self.sheet(32), "--output-dir", self.bundle("hero_v001"))
        registered = self.register_and_approve("hero_v001")
        self.assertEqual(registered["technical_validation"], "passed")  # a mismatch never blocks
        record = common.read_json(self.root / ".gamearts" / "outputs" / "manifests" / "assets.json")["assets"][0]
        self.assertEqual(record["status"], "approved")
        fit_record = record["technical_validation"]["settings_fit"]
        self.assertEqual(fit_record["status"], "mismatch")
        self.assertIn("records 32 pixels per metre", fit_record["checks"][0]["detail"])
        page = Path(report.build(self.root)["path"]).read_text(encoding="utf-8")
        self.assertIn("Does not match the saved settings of this game", page)

    def test_a_square_tile_that_disagrees_with_the_scale_is_warned_about(self):
        write_settings(self.root, world={**base_settings()["world"], "ground_tile_px": [64, 64]})  # 16 m tile x 16 px per metre is 256 px, not 64
        warnings = life.check_settings(self.root)["warnings"]
        self.assertTrue(any("makes a tile 256 x 256" in text for text in warnings), warnings)


class OtherBuilderTests(unittest.TestCase):
    """The bundle and tileset builders say, like the sheet builder, whether what they built fits the game."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)
        self.game = self.work / "game"
        self.game.mkdir()
        write_settings(self.game)

    def test_the_bundle_builder_says_whether_the_bundle_faces_the_games_directions(self):
        from test_component_bundle import ComponentTests
        job = self.work / "component_job.json"
        job.write_text(json.dumps(ComponentTests().fixture(self.work)), encoding="utf-8")  # a bundle that faces S and E
        said = run("build_component_bundle.py", job, "--output-dir", self.work / "bundle", "--game-root", self.game).stdout
        self.assertIn("SETTINGS FIT mismatch", said)
        self.assertIn("MISMATCH (directions)", said)
        write_settings(self.game, directions=["S", "E"])
        said = run("build_component_bundle.py", job, "--output-dir", self.work / "bundle_two", "--game-root", self.game).stdout
        self.assertIn("SETTINGS FIT passed", said)

    def test_the_tileset_builder_says_whether_the_tiles_are_the_games_ground_tile(self):
        from test_tileset import BuildCase
        case = BuildCase()
        case.setUp()
        self.addCleanup(case.tearDown)
        body = case.job()
        body.pop("_input_dir")
        job = case.src / "tile.job.json"
        job.write_text(json.dumps(body), encoding="utf-8")  # 8x8 tiles
        said = run("build_tileset.py", job, "--output-dir", self.work / "tiles", "--game-root", self.game).stdout
        self.assertIn("MISMATCH (tile size)", said)
        self.assertIn("tiles are 8x8, but the game's ground tile is 256x256", said)
        write_settings(self.game, world={**base_settings()["world"], "ground_tile_px": [8, 8]})
        said = run("build_tileset.py", job, "--output-dir", self.work / "tiles_two", "--game-root", self.game).stdout
        self.assertIn("SETTINGS FIT passed", said)


class LimitedProfileTests(SheetCase):
    """A bundle that faces only some of the game's directions passes the settings-fit check when the owner's words approving that are recorded."""

    OWNER = "the owner said this machine only ever faces south and east"

    def fit_folder(self, faces):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        (folder / "machine.bundle.json").write_text(json.dumps({"directions": faces}), encoding="utf-8")
        return folder

    def test_the_owners_approval_lets_a_proper_subset_of_the_games_directions_pass(self):
        limited = {"approval_ref": self.OWNER}
        folder = self.fit_folder(["S", "E"])
        result = fit.fit_report(folder, base_settings(), None, limited)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["checks"][0]["limited_profile"])
        self.assertIn(self.OWNER, result["checks"][0]["detail"])
        self.assertEqual(fit.fit_report(folder, base_settings())["status"], "mismatch")  # without the approval it is still reported

    def test_the_approval_does_not_cover_directions_the_game_does_not_have_or_a_repeated_one(self):
        limited = {"approval_ref": self.OWNER}
        for faces in (["S", "UP"], ["S", "S"]):
            with self.subTest(faces=faces):
                self.assertEqual(fit.fit_report(self.fit_folder(faces), base_settings(), None, limited)["status"], "mismatch")

    def test_a_bundle_that_faces_the_whole_set_does_not_use_the_approval(self):
        result = fit.fit_report(self.fit_folder(list(EIGHT)), base_settings(), None, {"approval_ref": self.OWNER})
        self.assertEqual(result["status"], "passed")
        self.assertNotIn("limited_profile", result["checks"][0])

    def register(self, ref, name="machine_v001"):
        from test_component_bundle import ComponentTests
        work = self.root / "work"
        work.mkdir(exist_ok=True)
        job = work / f"{name}.job.json"
        job.write_text(json.dumps(ComponentTests().fixture(work)), encoding="utf-8")  # a bundle that faces S and E
        run("build_component_bundle.py", job, "--output-dir", self.root / OUT / "assets" / "generated" / name)
        return life.register_asset(self.root, name, "v001", f"{OUT}/assets/generated/{name}", [("hero", "v001")], None, None, ref)

    def records(self):
        return common.read_json(self.root / ".gamearts" / "outputs" / "manifests" / "assets.json")["assets"]

    def test_registering_records_the_owners_words_and_the_report_shows_them(self):
        self.register(self.OWNER)
        record = self.records()[0]
        self.assertEqual(record["limited_profile"], {"approval_ref": self.OWNER})
        self.assertEqual(record["technical_validation"]["settings_fit"]["status"], "passed")
        page = Path(report.build(self.root)["path"]).read_text(encoding="utf-8")
        self.assertIn("Faces only some of the directions of this game; the owner approved that: " + self.OWNER, page)

    def test_without_the_approval_the_same_bundle_is_reported_as_a_mismatch(self):
        self.register(None)
        record = self.records()[0]
        self.assertNotIn("limited_profile", record)
        self.assertEqual(record["technical_validation"]["settings_fit"]["status"], "mismatch")

    def test_an_empty_approval_is_refused(self):
        with self.assertRaisesRegex(ValueError, "owner's own words"):
            self.register("   ")
        self.assertEqual(self.records() if (self.root / ".gamearts" / "outputs" / "manifests" / "assets.json").is_file() else [], [])

    def test_an_approval_is_refused_where_there_is_nothing_to_approve(self):
        write_settings(self.root, directions=["S", "E"])  # the bundle now faces the game's whole set
        with self.assertRaisesRegex(ValueError, "nothing to approve"):
            self.register(self.OWNER)
        sheet = self.frames(self.root / "work" / "sheet_frames")  # and a plain sheet has no facings at all
        run("build_sheet_atlas.py", self.sheet_job("sheet_v001", sheet), "--output-dir", self.bundle("sheet_v001"))
        with self.assertRaisesRegex(ValueError, "nothing to approve"):
            life.register_asset(self.root, "sheet_v001", "v001", f"{OUT}/assets/generated/sheet_v001", [("hero", "v001")], None, None, self.OWNER)
        self.assertEqual(self.records() if (self.root / ".gamearts" / "outputs" / "manifests" / "assets.json").is_file() else [], [])

    def test_approving_and_restoring_audit_with_the_recorded_approval(self):
        from unittest import mock
        self.register(self.OWNER)
        spy = mock.patch.object(life, "technical_check_bundle", wraps=life.technical_check_bundle)
        with spy as gate:
            with self.assertRaises(ValueError):  # the fixture has no parent-cleanup evidence, so it cannot be approved; the gate is still run first
                life.approve_asset(self.root, "machine_v001", "approved-in-test")
            self.assertEqual(gate.call_args.kwargs["limited_profile"], {"approval_ref": self.OWNER})
            life.revoke(self.root, "assets", "machine_v001", "testing the restore", "v001", "revoked-in-test")
            gate.reset_mock()
            with self.assertRaisesRegex(ValueError, "fails the technical gate"):  # refused for the same missing evidence, after the gate ran
                life.restore(self.root, "assets", "machine_v001", "v001", "restored-in-test")
            self.assertEqual(gate.call_args.kwargs["limited_profile"], {"approval_ref": self.OWNER})

    def test_the_command_line_takes_the_approval(self):
        from test_component_bundle import ComponentTests
        work = self.root / "work"
        work.mkdir(exist_ok=True)
        job = work / "cli.job.json"
        job.write_text(json.dumps(ComponentTests().fixture(work)), encoding="utf-8")
        run("build_component_bundle.py", job, "--output-dir", self.root / OUT / "assets" / "generated" / "machine_v002")
        run("gamearts_asset_lifecycle.py", "register-asset", "--game-root", self.root, "--id", "machine_v002", "--revision", "v001",
            "--bundle", f"{OUT}/assets/generated/machine_v002", "--source-mockup", "hero:v001", "--limited-profile-ref", self.OWNER)
        self.assertEqual(self.records()[0]["limited_profile"]["approval_ref"], self.OWNER)


if __name__ == "__main__":
    unittest.main()
