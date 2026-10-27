"""End-to-end lifecycle operations on a real game folder: register-asset, restore, select reporting, concurrency, rollback."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from gamearts_testkit import make_mockup, make_sheet, write_settings

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import gamearts_asset_lifecycle as life  # noqa: E402
import gamearts_common as common  # noqa: E402
import gamearts_storyboard as board  # noqa: E402

OUT = ".gamearts/outputs"


class GameFolder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        write_settings(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def approved_mockup(self, mockup_id="test-scene", revision="v001", scope="world", scene=None):
        image, metadata = make_mockup(self.root, mockup_id, revision, scope, scene)
        life.register_mockup(self.root, metadata, image)
        life.approve_mockup(self.root, mockup_id, revision, "approved-in-test")
        return mockup_id, revision

    def generated_bundle(self, asset_id="workshop", revision="v001", damage=False):
        name = f"{asset_id}_{revision}"
        folder = self.root / OUT / "assets/generated" / name
        folder.mkdir(parents=True)
        files = make_sheet(folder, f"{name}_sheet", asset_id)
        if damage:
            sheet = folder / files[0]
            cell_w = common.read_json(folder / files[1])["cell_size"][0]
            image = Image.open(sheet).convert("RGBA")
            image.putpixel((cell_w + 1, 0), (1, 2, 3, 255))
            image.save(sheet)
        return name, f"{OUT}/assets/generated/{name}"

    def registered_asset(self, asset_id="workshop", revision="v001", source=("test-scene", "v001")):
        name, bundle = self.generated_bundle(asset_id, revision)
        life.register_asset(self.root, name, revision, bundle, [source])
        return name

    def manifest(self, kind):
        return common.read_json(self.root / OUT / "manifests" / f"{kind}.json")[kind]


class RegisterAssetTests(GameFolder):
    def test_register_links_the_approved_mockup_and_runs_the_technical_gate(self):
        source = self.approved_mockup()
        name, bundle = self.generated_bundle()
        result = life.register_asset(self.root, name, "v001", bundle, [source])
        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["technical_validation"], "passed")
        record = self.manifest("assets")[0]
        self.assertEqual(record["source_mockups"][0]["mockup_id"], "test-scene")
        self.assertEqual(record["engine_validation"], "not_tested")
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")
        common.validate_schema(common.read_json(self.root / OUT / "manifests/assets.json"), "gamearts-assets-manifest")

    def test_register_refuses_an_unapproved_source_mockup(self):
        image, metadata = make_mockup(self.root)
        life.register_mockup(self.root, metadata, image)  # generated, never approved
        name, bundle = self.generated_bundle()
        with self.assertRaisesRegex(ValueError, "not approved"):
            life.register_asset(self.root, name, "v001", bundle, [("test-scene", "v001")])

    def test_register_refuses_source_mockup_whose_bytes_changed(self):
        source = self.approved_mockup()
        approved = next((self.root / OUT / "mockups/approved").glob("*.png"))
        approved.write_bytes(approved.read_bytes() + b"x")
        name, bundle = self.generated_bundle()
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            life.register_asset(self.root, name, "v001", bundle, [source])

    def test_register_requires_a_source_and_a_new_revision(self):
        source = self.approved_mockup()
        name, bundle = self.generated_bundle()
        with self.assertRaisesRegex(ValueError, "at least one approved source"):
            life.register_asset(self.root, name, "v001", bundle, [])
        life.register_asset(self.root, name, "v001", bundle, [source])
        with self.assertRaisesRegex(ValueError, "already registered"):
            life.register_asset(self.root, name, "v001", bundle, [source])

    def test_register_rejects_a_bundle_outside_the_generated_store(self):
        source = self.approved_mockup()
        with self.assertRaisesRegex(ValueError, "directly inside"):
            life.register_asset(self.root, "x", "v001", ".gamearts", [source])
        with self.assertRaisesRegex(ValueError, "stay inside"):
            life.register_asset(self.root, "x", "v001", "../elsewhere", [source])

    def test_damaged_sheet_registers_as_generated_with_issues_and_cannot_be_approved(self):
        source = self.approved_mockup()
        name, bundle = self.generated_bundle(damage=True)
        result = life.register_asset(self.root, name, "v001", bundle, [source])
        self.assertEqual(result["technical_validation"], "failed")
        self.assertTrue(any("not exact #FF00FF" in issue for issue in result["technical_issues"]))
        with self.assertRaisesRegex(ValueError, "Technical artwork gate failed"):
            life.approve_asset(self.root, name, "approved-in-test")
        self.assertEqual(self.manifest("assets")[0]["status"], "generated")


class FullFlowTests(GameFolder):
    def test_register_approve_select_revoke_restore_reapprove(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        life.approve_asset(self.root, name, "approved-in-test")
        self.assertEqual(life.audit_asset(self.root, name), [])
        self.assertEqual([r["id"] for r in life.select(self.root, "assets", "approved")], [name])
        life.revoke(self.root, "assets", name, "art direction changed", replaced_by="workshop_v002")
        record = self.manifest("assets")[0]
        self.assertEqual((record["status"], record["replaced_by"]), ("revoked", "workshop_v002"))
        self.assertEqual(life.select(self.root, "assets", "approved"), [])
        # Restore returns it to generated (never straight to approved) and demands a fresh approval.
        life.restore(self.root, "assets", name, "v001", "owner asked for it back in chat")
        record = self.manifest("assets")[0]
        self.assertEqual((record["status"], record["approval"]), ("generated", "pending"))
        self.assertEqual(record["restored_from"], "revoked")
        self.assertNotIn("artifact_hashes", record)
        self.assertEqual(life.select(self.root, "assets", "approved"), [])
        life.approve_asset(self.root, name, "approved-again-in-test")
        self.assertEqual(life.audit_asset(self.root, name), [])

    def test_restore_needs_a_reference_and_a_revoked_record(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        with self.assertRaisesRegex(ValueError, "Only a revoked"):
            life.restore(self.root, "assets", name, "v001", "owner asked")
        life.revoke(self.root, "assets", name, "bad")
        with self.assertRaisesRegex(ValueError, "reference"):
            life.restore(self.root, "assets", name, "v001", " ")

    def test_restoring_a_mockup_returns_it_to_generated_with_its_companions(self):
        image, metadata = make_mockup(self.root)
        life.register_mockup(self.root, metadata, image)
        life.revoke(self.root, "mockups", "test-scene", "wrong direction", "v001")
        life.restore(self.root, "mockups", "test-scene", "v001", "owner asked for it back")
        generated = self.root / OUT / "mockups/generated"
        self.assertTrue((generated / image.name).is_file())
        self.assertTrue((generated / metadata.name).is_file())
        self.assertEqual(life.audit_mockup(self.root, "test-scene", "v001"), [])
        self.assertEqual(life.reconcile_mockups(self.root)["status"], "consistent")

    def test_revoking_a_mockup_names_the_assets_built_on_it(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        life.approve_asset(self.root, name, "approved-in-test")
        result = life.revoke(self.root, "mockups", "test-scene", "style rejected", "v001")
        self.assertEqual(result["dependents"], [{"asset_id": name, "status": "approved"}])
        self.assertTrue(life.audit_asset(self.root, name))  # the approved asset now fails its source check

    def test_list_filters_by_status(self):
        source = self.approved_mockup()
        self.registered_asset(source=source)
        self.assertEqual([r["id"] for r in life.list_records(self.root, "assets", "generated")], ["workshop_v001"])
        self.assertEqual(life.list_records(self.root, "assets", "approved"), [])
        self.assertEqual(life.list_records(self.root, "mockups", "approved")[0]["id"], "test-scene")

    def test_check_settings_reports_the_material_hash(self):
        result = life.check_settings(self.root)
        self.assertTrue(result["owner_confirmed"])
        settings, canonical, _ = common.load_project_settings(self.root)
        self.assertEqual(result["material_settings_sha256"], canonical)
        write_settings(self.root, settings_status="inferred")
        self.assertFalse(life.check_settings(self.root)["owner_confirmed"])


class BundleBuiltByTheBuilderTests(GameFolder):
    def bundle(self, composite):
        from test_component_bundle import ComponentTests
        scratch = self.root / "frames"
        scratch.mkdir()
        config = ComponentTests().fixture(scratch)
        if not composite:
            config["components"] = config["components"][:1]
            config["components"][0]["views"] = config["components"][0]["views"]
        folder = self.root / OUT / "assets/generated" / "machine_v001"
        import build_component_bundle
        build_component_bundle.build(config, folder, scratch)
        return "machine", f"{OUT}/assets/generated/machine_v001"

    def test_a_multi_part_bundle_without_cleanup_proof_cannot_be_approved(self):
        source = self.approved_mockup()
        name, bundle = self.bundle(composite=True)
        result = life.register_asset(self.root, name, "v001", bundle, [source])
        self.assertEqual(result["technical_validation"], "failed")
        self.assertTrue(any("missing mandatory parent-cleanup evidence" in i for i in result["technical_issues"]))
        with self.assertRaisesRegex(ValueError, "Technical artwork gate failed.*parent-cleanup"):
            life.approve_asset(self.root, name, "approved-in-test")
        self.assertEqual(self.manifest("assets")[0]["status"], "generated")
        self.assertEqual(self.manifest("assets")[0]["visual_review_protocol"], "review_packet")

    def test_a_single_component_bundle_has_nothing_detachable_and_passes_the_technical_gate(self):
        source = self.approved_mockup()
        name, bundle = self.bundle(composite=False)
        result = life.register_asset(self.root, name, "v001", bundle, [source])
        self.assertEqual(result["technical_validation"], "passed", result["technical_issues"])
        self.assertNotIn("visual_review_protocol", self.manifest("assets")[0])
        life.approve_asset(self.root, name, "approved-in-test")
        self.assertEqual(life.audit_asset(self.root, name), [])


class NestedBundleRevokeTests(GameFolder):
    def test_an_approved_bundle_with_nested_declared_files_can_be_revoked(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        life.approve_asset(self.root, name, "approved-in-test")
        folder = self.root / OUT / "assets/approved" / name
        (folder / "sub").mkdir()
        (folder / "sub" / "extra.txt").write_text("nested")
        manifest = self.root / OUT / "manifests/assets.json"
        data = common.read_json(manifest)
        data["assets"][0]["files"].append("sub/extra.txt")
        common.atomic_write_json(manifest, data)
        life.revoke(self.root, "assets", name, "superseded")
        self.assertTrue((self.root / OUT / "assets/revoked" / name / "sub" / "extra.txt").is_file())
        self.assertEqual(self.manifest("assets")[0]["status"], "revoked")


class FreshGameTests(GameFolder):
    """A game that has registered nothing has no manifests; asking about it is not an error."""

    def test_list_select_and_reconcile_on_a_game_with_nothing_registered(self):
        for kind in ("mockups", "assets"):
            self.assertEqual(life.list_records(self.root, kind), [])
            self.assertEqual(life.select(self.root, kind, "approved"), [])
            self.assertEqual(life.select(self.root, kind, "generated", report=True), {"eligible": [], "blocked": []})
        self.assertEqual(life.reconcile_mockups(self.root)["status"], "consistent")
        self.assertEqual(life.reconcile_assets(self.root)["status"], "consistent")
        self.assertFalse((self.root / OUT / "manifests").exists())  # asking created nothing

    def test_an_unregistered_image_on_a_fresh_game_is_still_reported(self):
        image, _ = make_mockup(self.root, "stray", "v001", "scene")
        report = life.reconcile_mockups(self.root)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("Unregistered mockup image" in issue for issue in report["issues"]))
        self.assertTrue(image.exists())

    def test_asking_for_one_record_that_does_not_exist_is_still_an_error(self):
        with self.assertRaisesRegex(ValueError, "Expected one exact"):
            life.select(self.root, "mockups", "approved", "ghost")
        with self.assertRaisesRegex(ValueError, "Missing assets lifecycle manifest"):
            life.audit_asset(self.root, "ghost")


class ImageGeneratorSettingTests(GameFolder):
    """The owner's chosen image generator is remembered in project.json and enforced when a mockup is registered."""

    def choose(self, **choice):
        write_settings(self.root, image_generation=choice)

    def mockup_from(self, tool_mode, tool_name=None, mockup_id="test-scene"):
        image, metadata = make_mockup(self.root, mockup_id)
        body = common.read_json(metadata)
        body["tool_mode"] = tool_mode
        if tool_name is not None:
            body["tool_name"] = tool_name
        common.atomic_write_json(metadata, body)
        return image, metadata

    def manifest_exists(self):
        return (self.root / OUT / "manifests" / "mockups.json").exists()

    def test_a_mockup_made_with_the_chosen_tool_registers_and_the_result_names_the_setting(self):
        self.choose(tool="built_in_image_gen")
        result = life.register_mockup(self.root, *reversed(self.mockup_from("built_in_image_gen")))
        self.assertEqual(result["image_generator_setting"], "built_in_image_gen")

    def test_a_mockup_made_with_another_tool_is_refused_and_nothing_is_registered(self):
        self.choose(tool="built_in_image_gen")
        image, metadata = self.mockup_from("cli_image_gen")
        with self.assertRaisesRegex(ValueError, "image generator is built_in_image_gen"):
            life.register_mockup(self.root, metadata, image)
        self.assertFalse(self.manifest_exists())

    def test_when_the_owner_supplies_the_pictures_a_generated_mockup_is_refused_but_an_import_is_accepted(self):
        self.choose(tool="user_supplied")
        image, metadata = self.mockup_from("built_in_image_gen")
        with self.assertRaisesRegex(ValueError, "owner makes the pictures.*import-mockup"):
            life.register_mockup(self.root, metadata, image)
        outside = self.root.parent / f"{self.root.name}_supplied.png"
        Image.new("RGB", (30, 20), (40, 90, 140)).save(outside)
        self.assertEqual(life.import_mockup(self.root, outside, "owner-art", "v001", "asset")["status"], "generated")

    def test_an_import_is_accepted_whichever_generator_is_chosen(self):
        self.choose(tool="cli_image_gen")
        outside = self.root.parent / f"{self.root.name}_painting.png"
        Image.new("RGB", (30, 20), (40, 90, 140)).save(outside)
        self.assertEqual(life.import_mockup(self.root, outside, "owner-art", "v001", "asset")["status"], "generated")

    def test_a_connected_tool_must_be_named_and_must_be_the_chosen_one(self):
        self.choose(tool="connected_tool", tool_name="Studio Painter")
        image, metadata = self.mockup_from("connected_tool")
        with self.assertRaisesRegex(ValueError, "tool_name"):
            life.register_mockup(self.root, metadata, image)
        image, metadata = self.mockup_from("connected_tool", "Other Painter", "second-scene")
        with self.assertRaisesRegex(ValueError, "Studio Painter"):
            life.register_mockup(self.root, metadata, image)
        self.assertFalse(self.manifest_exists())
        image, metadata = self.mockup_from("connected_tool", "STUDIO painter", "third-scene")
        life.register_mockup(self.root, metadata, image)
        record = common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"][0]
        self.assertEqual((record["tool_mode"], record["tool_name"]), ("connected_tool", "STUDIO painter"))

    def test_a_game_with_no_choice_registers_as_before_and_says_the_choice_is_missing(self):
        result = life.register_mockup(self.root, *reversed(self.mockup_from("built_in_image_gen")))
        self.assertEqual(result["image_generator_setting"], "not_set")

    def test_changing_the_generator_never_reopens_approved_art(self):
        self.choose(tool="built_in_image_gen")
        image, metadata = self.mockup_from("built_in_image_gen")
        life.register_mockup(self.root, metadata, image)
        life.approve_mockup(self.root, "test-scene", "v001", "approved in test")
        before = life.check_settings(self.root)["material_settings_sha256"]
        self.choose(tool="connected_tool", tool_name="Studio Painter")
        self.assertEqual(life.check_settings(self.root)["material_settings_sha256"], before)
        self.assertEqual(life.audit_mockup(self.root, "test-scene", "v001"), [])

    def test_check_settings_reports_the_choice_and_a_malformed_choice_is_refused(self):
        self.choose(tool="cli_image_gen", notes="medium quality")
        self.assertEqual(life.check_settings(self.root)["image_generation"], {"tool": "cli_image_gen", "notes": "medium quality"})
        self.choose(tool="magic_brush")
        with self.assertRaisesRegex(ValueError, "image_generation"):
            life.check_settings(self.root)


class RegisterGeneratedTests(GameFolder):
    """A picture an image tool just made: the agent hands over the file and the prompt, the framework does the rest."""
    PROMPT = "Use case: stylized-concept. A village pitch, warm afternoon light, elevated 3/4 view."

    def tool_output(self, name="exec-1234.png", fmt="PNG"):
        path = self.root.parent / f"{self.root.name}_tool" / name
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (60, 40), (80, 140, 60)).save(path, format=fmt)
        return path

    def test_a_tool_output_is_named_hashed_documented_and_registered_without_touching_the_original(self):
        write_settings(self.root, image_generation={"tool": "built_in_image_gen"})
        source = self.tool_output()
        before = source.read_bytes()
        result = life.register_generated_mockup(self.root, source, "market", "v001", "scene", self.PROMPT, model="gpt-image-test")
        self.assertEqual((result["status"], result["image_generator_setting"]), ("generated", "built_in_image_gen"))
        self.assertEqual(Path(result["path"]).name, "test-project_scene_market_mockup_v001.png")
        self.assertEqual(source.read_bytes(), before)
        record = common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"][0]
        self.assertEqual((record["tool_mode"], record["prompt"], record["prompt_origin"], record["imagegen_prompt_captured"]),
                         ("built_in_image_gen", self.PROMPT, "agent_brief", True))
        self.assertEqual(record["source_references"][0]["original_name"], "exec-1234.png")
        self.assertEqual(record["provenance"]["model"], "gpt-image-test")
        self.assertEqual(life.audit_mockup(self.root, "market", "v001"), [])
        self.assertFalse(result["pixel_facts"]["has_transparency"])

    def test_staging_never_leaves_the_game_folder(self):
        write_settings(self.root, image_generation={"tool": "built_in_image_gen"})
        outside = self.root.parent / f"{self.root.name}_painting.png"
        Image.new("RGB", (30, 20), (40, 90, 140)).save(outside)
        with mock.patch.object(tempfile, "tempdir", str(self.root.parent / "no-such-temp-folder")):
            life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT)
            life.import_mockup(self.root, outside, "owner-art", "v001", "asset")
        self.assertEqual(list((self.root / ".gamearts" / "system" / "tmp").iterdir()), [])

    def test_the_tool_and_its_name_default_to_the_saved_choice(self):
        write_settings(self.root, image_generation={"tool": "connected_tool", "tool_name": "Studio Painter"})
        life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT)
        record = common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"][0]
        self.assertEqual((record["tool_mode"], record["tool_name"]), ("connected_tool", "Studio Painter"))

    def test_with_no_saved_choice_the_tool_must_be_named(self):
        with self.assertRaisesRegex(ValueError, "No image generator is saved"):
            life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT)
        life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT, tool_mode="cli_image_gen")
        record = common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"][0]
        self.assertEqual(record["tool_mode"], "cli_image_gen")

    def test_another_tool_than_the_saved_choice_is_refused(self):
        write_settings(self.root, image_generation={"tool": "built_in_image_gen"})
        with self.assertRaisesRegex(ValueError, "image generator is built_in_image_gen"):
            life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT, tool_mode="cli_image_gen")
        self.assertFalse((self.root / OUT / "manifests" / "mockups.json").exists())

    def test_nothing_generated_is_registered_when_the_owner_supplies_the_pictures(self):
        write_settings(self.root, image_generation={"tool": "user_supplied"})
        for tool_mode in (None, "built_in_image_gen"):
            with self.subTest(tool_mode=tool_mode), self.assertRaisesRegex(ValueError, "owner makes the pictures.*import-mockup"):
                life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT, tool_mode=tool_mode)

    def test_an_import_cannot_be_claimed_as_generated(self):
        with self.assertRaisesRegex(ValueError, "import-mockup"):
            life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT, tool_mode="external_import")

    def test_only_a_png_with_the_real_prompt_is_accepted(self):
        write_settings(self.root, image_generation={"tool": "built_in_image_gen"})
        with self.assertRaisesRegex(ValueError, "must be a PNG"):
            life.register_generated_mockup(self.root, self.tool_output("shot.jpg", "JPEG"), "market", "v001", "scene", self.PROMPT)
        with self.assertRaisesRegex(ValueError, "prompt"):
            life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", "   ")
        self.assertFalse((self.root / OUT / "manifests" / "mockups.json").exists())

    def test_the_revision_cannot_be_registered_twice(self):
        write_settings(self.root, image_generation={"tool": "built_in_image_gen"})
        life.register_generated_mockup(self.root, self.tool_output(), "market", "v001", "scene", self.PROMPT)
        with self.assertRaisesRegex(ValueError, "already registered"):
            life.register_generated_mockup(self.root, self.tool_output("exec-5678.png"), "market", "v001", "scene", self.PROMPT)


class ImportMockupTests(GameFolder):
    """A mockup the user made elsewhere: copied in, never touched, never regenerated, approved only on the user's say-so."""

    def outside_png(self, name="my_mockup.png", size=(40, 30)):
        path = self.root.parent / f"{self.root.name}_outside" / name
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", size, (30, 120, 60)).save(path)
        return path

    def test_a_png_is_copied_byte_for_byte_and_left_generated_without_a_statement_of_approval(self):
        source = self.outside_png()
        before = source.read_bytes()
        result = life.import_mockup(self.root, source, "clubhouse", "v001", "asset")
        self.assertEqual(result["status"], "generated")
        self.assertEqual(source.read_bytes(), before)  # the original is untouched
        managed = next((self.root / OUT / "mockups/generated").glob("*.png"))
        self.assertEqual(managed.name, "test-project_asset_clubhouse_mockup_v001.png")
        self.assertEqual(managed.read_bytes(), before)  # a PNG is not re-encoded
        record = self.manifest("mockups")[0]
        self.assertEqual((record["tool_mode"], record["prompt_origin"], record["approval"]), ("external_import", "external_provider", "pending"))
        self.assertIn("No generation prompt exists", record["prompt"])
        self.assertEqual(record["rights"], {"status": "user_supplied", "notes": ""})
        self.assertEqual(result["import_checks"]["size"], [40, 30])
        self.assertFalse(result["import_checks"]["converted_to_png"])
        self.assertEqual(life.audit_mockup(self.root, "clubhouse", "v001"), [])

    def test_an_already_approved_mockup_is_registered_and_approved_with_the_users_own_words(self):
        source = self.outside_png()
        result = life.import_mockup(self.root, source, "clubhouse", "v001", "asset", approval_reference="user said: it's already approved")
        self.assertEqual(result["status"], "approved")
        record = self.manifest("mockups")[0]
        self.assertEqual((record["status"], record["approval_reference"]), ("approved", "user said: it's already approved"))
        self.assertTrue((self.root / OUT / "mockups/approved" / "test-project_asset_clubhouse_mockup_v001.png").is_file())
        self.assertEqual(life.audit_mockup(self.root, "clubhouse", "v001"), [])
        self.assertEqual(life.reconcile_mockups(self.root)["status"], "consistent")
        self.assertEqual([r["id"] for r in life.select(self.root, "mockups", "approved")], ["clubhouse"])
        self.assertTrue(Path(result["path"]).is_file() and Path(result["metadata"]).is_file(), "the result must name where the files are now")
        self.assertIn("approved", Path(result["metadata"]).parts)

    def test_a_jpeg_becomes_a_png_without_changing_a_decoded_pixel_and_the_original_is_recorded(self):
        from PIL import ImageChops
        jpeg = self.root.parent / f"{self.root.name}_outside" / "photo.jpg"
        jpeg.parent.mkdir(exist_ok=True)
        Image.new("RGB", (32, 24), (200, 90, 20)).save(jpeg, quality=90)
        result = life.import_mockup(self.root, jpeg, "photo-scene", "v001", "scene", rights="owned", rights_notes="the user painted it")
        self.assertTrue(result["import_checks"]["converted_to_png"])
        managed = next((self.root / OUT / "mockups/generated").glob("*.png"))
        with Image.open(managed) as imported, Image.open(jpeg) as original:
            self.assertEqual(imported.format, "PNG")
            self.assertIsNone(ImageChops.difference(imported.convert("RGB"), original.convert("RGB")).getbbox())
        record = self.manifest("mockups")[0]
        self.assertEqual(record["source_references"][0]["original_sha256"], result["import_checks"]["original_sha256"])
        self.assertEqual(record["rights"]["status"], "owned")
        self.assertIn("lossless re-encode", record["provenance"]["edit_mode"])

    def test_transparency_and_key_pixels_are_reported_not_hidden(self):
        path = self.root.parent / f"{self.root.name}_outside" / "alpha.png"
        path.parent.mkdir(exist_ok=True)
        Image.new("RGBA", (8, 8), (255, 0, 255, 0)).save(path)
        checks = life.import_mockup(self.root, path, "alpha-art", "v001", "asset")["import_checks"]
        self.assertTrue(checks["has_transparency"])

    def test_refusals(self):
        source = self.outside_png()
        life.import_mockup(self.root, source, "clubhouse", "v001", "asset")
        with self.assertRaisesRegex(ValueError, "already registered"):
            life.import_mockup(self.root, source, "clubhouse", "v001", "asset")
        with self.assertRaisesRegex(ValueError, "regular file"):
            life.import_mockup(self.root, self.root, "other", "v001", "asset")
        with self.assertRaisesRegex(ValueError, "mockup id"):
            life.import_mockup(self.root, source, "Bad Id", "v001", "asset")
        with self.assertRaisesRegex(ValueError, "scope must be"):
            life.import_mockup(self.root, source, "other", "v001", "everything")
        with self.assertRaisesRegex(ValueError, "rights must be"):
            life.import_mockup(self.root, source, "other", "v002", "asset", rights="mine")
        write_settings(self.root, settings_status="inferred")
        with self.assertRaisesRegex(ValueError, "owner_confirmed"):
            life.import_mockup(self.root, source, "other", "v003", "asset")

    def test_the_storyboard_gate_applies_to_an_imported_scene_mockup(self):
        board.write(self.root, {"title": "T", "origin": "agent_authored", "scenes": [{"id": "arrival", "title": "A", "summary": "s"}]}, "agent", "d")
        source = self.outside_png()
        with self.assertRaisesRegex(ValueError, "must name an approved storyboard scene"):
            life.import_mockup(self.root, source, "street", "v001", "scene")
        with self.assertRaisesRegex(ValueError, "not approved"):
            life.import_mockup(self.root, source, "street", "v001", "scene", scene_id="arrival")
        self.assertEqual(life.import_mockup(self.root, source, "clubhouse", "v001", "asset")["status"], "generated")  # not a scene: no gate
        board.approve(self.root, ["arrival"], "ok")
        self.assertEqual(life.import_mockup(self.root, source, "street", "v001", "scene", scene_id="arrival")["status"], "generated")

    def test_an_approval_that_fails_leaves_a_registered_generated_mockup_and_says_so(self):
        source = self.outside_png()
        with mock.patch.object(life, "approve_mockup", side_effect=ValueError("disk full")):
            with self.assertRaisesRegex(ValueError, "registered as generated, but approval failed: disk full"):
                life.import_mockup(self.root, source, "clubhouse", "v001", "asset", approval_reference="user approved it")
        self.assertEqual(self.manifest("mockups")[0]["status"], "generated")


class SelectReportTests(GameFolder):
    def test_listing_reports_blocked_records_instead_of_aborting(self):
        source = self.approved_mockup()
        good = self.registered_asset("good", "v001", source)
        bad = self.registered_asset("bad", "v001", source)
        life.approve_asset(self.root, good, "approved-in-test")
        life.approve_asset(self.root, bad, "approved-in-test")
        sheet = next((self.root / OUT / "assets/approved" / bad).glob("*.png"))
        sheet.write_bytes(b"tampered")
        report = life.select(self.root, "assets", "approved", report=True)
        self.assertEqual([r["id"] for r in report["eligible"]], [good])
        self.assertEqual([b["id"] for b in report["blocked"]], [bad])
        self.assertIn("audit failed", report["blocked"][0]["reason"])
        with self.assertRaisesRegex(ValueError, "audit failed"):
            life.select(self.root, "assets", "approved", bad)

    def test_manifest_without_a_matching_folder_is_blocked_not_fatal(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        path = self.root / OUT / "manifests/assets.json"
        data = common.read_json(path)
        data["assets"][0]["bundle_path"] = f"{OUT}/assets/approved/{name}"
        data["assets"][0]["status"] = "approved"
        common.atomic_write_json(path, data)
        report = life.select(self.root, "assets", "approved", report=True)
        self.assertEqual(report["eligible"], [])
        self.assertEqual(len(report["blocked"]), 1)


class FilesRuleTests(GameFolder):
    def test_nested_declared_files_are_accepted_and_traversal_is_refused(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        life.approve_asset(self.root, name, "approved-in-test")
        folder = self.root / OUT / "assets/approved" / name
        manifest = self.root / OUT / "manifests/assets.json"
        data = common.read_json(manifest)
        (folder / "notes").mkdir()
        (folder / "notes" / "readme.txt").write_text("nested")
        data["assets"][0]["files"].append("notes/readme.txt")
        common.atomic_write_json(manifest, data)
        self.assertEqual(life.audit_asset(self.root, name), [])
        data["assets"][0]["files"].append("../outside.txt")
        common.atomic_write_json(manifest, data)
        self.assertTrue(any("unsafe bundle file: ../outside.txt" in i for i in life.audit_asset(self.root, name)))


class ConcurrencyTests(GameFolder):
    CHILD = (
        "import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2])\n"
        "import gamearts_asset_lifecycle as life\n"
        "from gamearts_testkit import make_mockup\n"
        "root, ident = sys.argv[3], sys.argv[4]\n"
        "image, metadata = make_mockup(root, ident, 'v001')\n"
        "life.register_mockup(root, metadata, image)\n")

    def test_parallel_registrations_lose_nothing(self):
        tests = str(Path(__file__).resolve().parent)
        ids = [f"scene-{n}" for n in range(5)]
        children = [subprocess.Popen([sys.executable, "-c", self.CHILD, str(SCRIPTS), tests, str(self.root), ident],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for ident in ids]
        results = []
        for child in children:
            _, error = child.communicate(timeout=120)
            results.append((child.returncode, error))
        self.assertEqual([code for code, _ in results], [0] * len(ids), [err for _, err in results])
        self.assertEqual(sorted(r["mockup_id"] for r in self.manifest("mockups")), ids)
        self.assertEqual(life.reconcile_mockups(self.root)["status"], "consistent")


class RollbackTests(GameFolder):
    def test_failed_mockup_revoke_and_restore_put_metadata_content_back_too(self):
        image, metadata = make_mockup(self.root)
        life.register_mockup(self.root, metadata, image)
        generated_metadata = self.root / OUT / "mockups/generated" / metadata.name
        manifest = self.root / OUT / "manifests/mockups.json"
        before_manifest, before_metadata = manifest.read_bytes(), generated_metadata.read_bytes()
        with mock.patch.object(life, "_write_manifest", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                life.revoke(self.root, "mockups", "test-scene", "bad", "v001")
        self.assertEqual(manifest.read_bytes(), before_manifest)
        self.assertEqual(generated_metadata.read_bytes(), before_metadata)
        life.revoke(self.root, "mockups", "test-scene", "bad", "v001")
        revoked_metadata = self.root / OUT / "mockups/revoked" / metadata.name
        before_manifest, before_metadata = manifest.read_bytes(), revoked_metadata.read_bytes()
        with mock.patch.object(life, "_write_manifest", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                life.restore(self.root, "mockups", "test-scene", "v001", "owner asked")
        self.assertEqual(manifest.read_bytes(), before_manifest)
        self.assertEqual(revoked_metadata.read_bytes(), before_metadata)
        self.assertFalse((self.root / OUT / "mockups/generated" / image.name).exists())

    def test_failed_mockup_approval_puts_everything_back(self):
        image, metadata = make_mockup(self.root)
        life.register_mockup(self.root, metadata, image)
        manifest = self.root / OUT / "manifests/mockups.json"
        before = manifest.read_bytes()
        with mock.patch.object(life, "_write_manifest", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                life.approve_mockup(self.root, "test-scene", "v001", "approved-in-test")
        self.assertEqual(manifest.read_bytes(), before)
        generated = self.root / OUT / "mockups/generated"
        self.assertTrue((generated / image.name).is_file() and (generated / metadata.name).is_file())
        self.assertFalse(any((self.root / OUT / "mockups/approved").glob("*")))
        self.assertEqual(life.audit_mockup(self.root, "test-scene", "v001"), [])

    def test_a_rollback_that_itself_fails_is_reported_not_hidden(self):
        image, metadata = make_mockup(self.root)
        life.register_mockup(self.root, metadata, image)
        real_move = life.shutil.move
        calls = {"n": 0}

        def flaky(src, dst, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] > 2:  # forward moves succeed; every move back fails
                raise OSError("locked by another program")
            return real_move(src, dst, *args, **kwargs)

        with mock.patch.object(life, "_write_manifest", side_effect=OSError("disk full")), \
                mock.patch.object(life.shutil, "move", side_effect=flaky):
            with self.assertRaisesRegex(ValueError, "disk full; ROLLBACK INCOMPLETE.*locked by another program"):
                life.approve_mockup(self.root, "test-scene", "v001", "approved-in-test")

    def test_failed_revoke_restores_files_and_record(self):
        source = self.approved_mockup()
        name = self.registered_asset(source=source)
        manifest = self.root / OUT / "manifests/assets.json"
        before = manifest.read_bytes()
        with mock.patch.object(life, "_write_manifest", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                life.revoke(self.root, "assets", name, "bad")
        self.assertEqual(manifest.read_bytes(), before)
        self.assertTrue((self.root / OUT / "assets/generated" / name).is_dir())


class StoryboardGateTests(GameFolder):
    def storyboard(self, status_ids=()):
        draft = {"title": "Campaign", "origin": "agent_authored", "brief": "a small town football story",
                 "scenes": [{"id": "arrival", "title": "Arrival", "summary": "The coach arrives in town."},
                            {"id": "first-match", "title": "First match", "summary": "The team plays its first match."}]}
        board.write(self.root, draft, "agent", "initial storyboard")
        if status_ids:
            board.approve(self.root, list(status_ids), "approved-in-test")

    def test_without_a_storyboard_scene_mockups_still_register(self):
        image, metadata = make_mockup(self.root, scope="scene")
        self.assertEqual(life.register_mockup(self.root, metadata, image)["status"], "generated")

    def test_a_storyboard_forbids_scene_mockups_outside_the_approved_sequence(self):
        self.storyboard(["arrival"])
        image, metadata = make_mockup(self.root, "scene-a", scope="scene")
        with self.assertRaisesRegex(ValueError, "must name an approved storyboard scene"):
            life.register_mockup(self.root, metadata, image)
        image, metadata = make_mockup(self.root, "scene-b", scope="scene", scene="first-match")
        with self.assertRaisesRegex(ValueError, "not approved"):
            life.register_mockup(self.root, metadata, image)
        image, metadata = make_mockup(self.root, "scene-c", scope="scene", scene="unknown-scene")
        with self.assertRaisesRegex(ValueError, "Unknown storyboard scene"):
            life.register_mockup(self.root, metadata, image)
        image, metadata = make_mockup(self.root, "scene-d", scope="scene", scene="arrival")
        self.assertEqual(life.register_mockup(self.root, metadata, image)["status"], "generated")
        self.assertEqual(self.manifest("mockups")[0]["storyboard_scene_id"], "arrival")

    def test_a_scene_mockup_row_keeps_the_fields_other_tools_read(self):
        """The Storyboard framework draws each scene from these manifest fields; they change only with a notice."""
        self.storyboard(["arrival"])
        image, metadata = make_mockup(self.root, "scene-d", scope="scene", scene="arrival")
        life.register_mockup(self.root, metadata, image)
        row = self.manifest("mockups")[0]
        for field in ("mockup_id", "revision", "status", "file", "storyboard_scene_id"):
            self.assertIn(field, row, f"the mockup manifest row lost {field!r}")
        self.assertEqual((row["status"], row["storyboard_scene_id"]), ("generated", "arrival"))
        self.assertTrue((self.root / row["file"]).is_file())

    def test_editing_an_approved_scene_blocks_its_mockup_until_reapproved(self):
        self.storyboard(["arrival", "first-match"])
        image, metadata = make_mockup(self.root, "scene-a", scope="scene", scene="arrival")
        life.register_mockup(self.root, metadata, image)
        data = board.load(self.root)
        scenes = [dict(s) for s in data["scenes"]]
        scenes[0]["summary"] = "The coach arrives at night, in the rain."
        board.write(self.root, {"title": data["title"], "origin": data["origin"], "brief": data["brief"], "scenes": scenes},
                    "user", "weather change")
        with self.assertRaisesRegex(ValueError, "not approved in its current form|not approved"):
            life.approve_mockup(self.root, "scene-a", "v001", "approved-in-test")
        board.approve(self.root, ["arrival", "first-match"], "re-approved-in-test")
        self.assertEqual(life.approve_mockup(self.root, "scene-a", "v001", "approved-in-test")["status"], "approved")


if __name__ == "__main__":
    unittest.main()
