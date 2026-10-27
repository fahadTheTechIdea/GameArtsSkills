"""The style anchor (plan P11.1): an approved `style` mockup the project points at and every reference packet carries."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import jsonschema
from PIL import Image

import gamearts_testkit as kit
from gamearts_testkit import settings, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_reference_crop", ROOT / "scripts" / "prepare_reference_crop.py")
crop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crop)
SCHEMAS = ROOT / "schemas"


def schema(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


class AnchorGame(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def style_board(self, mockup_id="look", revision="v001", approve=True, scope="style"):
        """Register (and approve) a style board; returns the image path of the stored mockup."""
        if not (self.root / ".gamearts" / "project.json").is_file():
            write_settings(self.root)
        board = Image.new("RGB", (64, 40), (30, 60, 90))
        image, metadata = kit.make_mockup(self.root, mockup_id, revision, scope, picture_image=board)
        life.register_mockup(self.root, metadata, image)
        if approve:
            life.approve_mockup(self.root, mockup_id, revision, "that is the look")
        return next((self.root / ".gamearts/outputs/mockups").rglob(f"*{mockup_id.replace('-', '_')}_mockup_{revision}.png"))

    def prepare(self, asset_class="prop", **overrides):
        job = kit.crop_game(self.root, asset_class, **overrides)
        return kit.crop_prepare(crop, self.root, job)


class ScopeAndSettingsTests(unittest.TestCase):
    def test_style_is_a_scope_in_every_place_a_scope_is_listed(self):
        self.assertIn("style", life.SCOPES)
        for name, path in (("gamearts-mockup-metadata", ("properties", "scope")), ("gamearts-mockups-manifest", ("properties", "mockups", "items", "properties", "scope")),
                           ("mockup-blueprint", None)):
            text = json.dumps(schema(name))
            self.assertIn('"style"', text, name)

    def test_the_scope_lists_of_the_lifecycle_and_the_mockup_contracts_are_equal(self):
        self.assertEqual(schema("gamearts-mockup-metadata")["properties"]["scope"]["enum"], list(life.SCOPES))
        self.assertEqual(schema("gamearts-mockups-manifest")["properties"]["mockups"]["items"]["properties"]["scope"]["enum"], list(life.SCOPES))

    def test_a_project_may_name_its_anchor_by_id_and_revision_only(self):
        project = schema("gamearts-project")
        jsonschema.validate(settings(art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}}), project)
        for bad in ({}, {"mockup_id": "look"}, {"mockup_id": "look", "revision": "1"}, {"mockup_id": "Look Now", "revision": "v001"},
                    {"mockup_id": "look", "revision": "v001", "extra": 1}):
            with self.subTest(bad=bad), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(settings(art_style={"id": "pixel_art", "anchor": bad}), project)

    def test_changing_the_anchor_is_a_material_change_of_the_style(self):
        base = common.canonical_settings_hash(settings(art_style={"id": "pixel_art"}))
        anchored = common.canonical_settings_hash(settings(art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}}))
        self.assertNotEqual(base, anchored)


class AnchorResolutionTests(AnchorGame):
    def test_no_anchor_means_nothing_to_resolve(self):
        write_settings(self.root)
        self.assertIsNone(common.resolve_style_anchor(self.root, settings()))

    def test_an_approved_style_board_resolves_to_its_file(self):
        image = self.style_board()
        write_settings(self.root, art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
        found = common.resolve_style_anchor(self.root, common.load_project_settings(self.root)[0])
        self.assertEqual((found["status"], found["problem"]), ("approved", None))
        self.assertEqual(found["path"], image.resolve())

    def test_each_way_an_anchor_can_be_unusable_is_named(self):
        cases = {
            "not registered": (lambda: None, "is not registered"),
            "still waiting": (lambda: self.style_board(approve=False), "generated, not approved"),
            "wrong scope": (lambda: self.style_board(scope="scene", approve=True), "must be a style board"),
        }
        for label, (arrange, fragment) in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as td:
                self.root = Path(td)
                arrange()
                write_settings(self.root, art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
                found = common.resolve_style_anchor(self.root, common.load_project_settings(self.root)[0])
                self.assertIn(fragment, found["problem"])

    def test_a_withdrawn_anchor_is_unusable(self):
        self.style_board()
        life.revoke(self.root, "mockups", "look", "wrong direction", "v001")
        write_settings(self.root, art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
        found = common.resolve_style_anchor(self.root, common.load_project_settings(self.root)[0])
        self.assertEqual(found["status"], "revoked")
        self.assertIn("revoked, not approved", found["problem"])

    def test_an_anchor_image_changed_on_disk_is_refused(self):
        image = self.style_board()
        write_settings(self.root, art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
        Image.new("RGB", (64, 40), (1, 1, 1)).save(image)
        found = common.resolve_style_anchor(self.root, common.load_project_settings(self.root)[0])
        self.assertIn("differ", found["problem"])

    def test_check_settings_reports_the_anchor_and_its_state(self):
        self.style_board()
        write_settings(self.root, art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
        result = life.check_settings(self.root)
        self.assertEqual((result["style_anchor"]["id"], result["style_anchor"]["status"], result["style_anchor"]["problem"]), ("look", "approved", None))
        write_settings(self.root)
        self.assertIsNone(life.check_settings(self.root)["style_anchor"])


class PacketTests(AnchorGame):
    def test_a_packet_carries_the_anchor_as_a_second_reference_beside_the_crop(self):
        source = self.style_board()
        packet_file = self.prepare(art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
        anchor = packet["style_anchor"]
        self.assertEqual((anchor["id"], anchor["revision"], anchor["image"]), ("look", "v001", "style_anchor.png"))
        copy = packet_file.parent / anchor["image"]
        self.assertTrue(copy.is_file())
        self.assertEqual(common.sha256_file(copy), anchor["sha256"])
        self.assertEqual(anchor["sha256"], common.sha256_file(source))
        self.assertNotIn(str(self.root), json.dumps(packet))
        prompt = (packet_file.parent / packet["prompt_path"]).read_text(encoding="utf-8")
        self.assertIn("STYLE ANCHOR", prompt)
        self.assertIn("style_anchor.png", prompt)
        jsonschema.validate(packet, schema("gamearts-reference-packet"))

    def test_a_game_without_an_anchor_gets_the_same_packet_as_before(self):
        packet_file = self.prepare()
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
        self.assertNotIn("style_anchor", packet)
        self.assertNotIn("STYLE ANCHOR", (packet_file.parent / packet["prompt_path"]).read_text(encoding="utf-8"))
        self.assertFalse((packet_file.parent / "style_anchor.png").exists())

    def test_production_is_blocked_while_the_named_anchor_is_unusable(self):
        self.style_board(approve=False)
        with self.assertRaisesRegex(ValueError, "generated, not approved"):
            self.prepare(art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})

    def test_verify_reports_whether_the_anchor_reached_the_image_tool(self):
        self.style_board()
        packet_file = self.prepare(art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
        candidate = self.root / "candidate.png"
        kit.key_image((16, 16), {(8, 8): (11, 22, 33, 255)}).save(candidate)

        def verify(**extra):
            receipt = self.root / "receipt.json"
            receipt.write_text(json.dumps({"reference_crop_sha256": packet["reference_crop_sha256"], "reference_image_path": packet["reference_crop"],
                                           "image_input_attached": True, "tool_invocation_id": "t-1", "candidate_image": str(candidate),
                                           "candidate_sha256": kit.digest(candidate), **extra}))
            return crop.verify(packet_file, receipt)

        self.assertEqual(verify(style_anchor_attached=True)["style_anchor"], "attached")
        missing = verify()
        self.assertEqual(missing["style_anchor"], "not_attached")
        self.assertIn("anchor", missing["style_anchor_note"])
        self.assertEqual(verify(style_anchor_attached=False)["style_anchor"], "not_attached")

    def test_verify_notices_a_changed_anchor_copy(self):
        self.style_board()
        packet_file = self.prepare(art_style={"id": "pixel_art", "anchor": {"mockup_id": "look", "revision": "v001"}})
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
        (packet_file.parent / "style_anchor.png").write_bytes(b"not the board")
        candidate = self.root / "candidate.png"
        kit.key_image((16, 16), {(8, 8): (11, 22, 33, 255)}).save(candidate)
        receipt = self.root / "receipt.json"
        receipt.write_text(json.dumps({"reference_crop_sha256": packet["reference_crop_sha256"], "reference_image_path": packet["reference_crop"],
                                       "image_input_attached": True, "tool_invocation_id": "t-1", "candidate_image": str(candidate),
                                       "candidate_sha256": kit.digest(candidate), "style_anchor_attached": True}))
        with self.assertRaisesRegex(ValueError, "style_anchor.png"):
            crop.verify(packet_file, receipt)

    def test_a_packet_without_an_anchor_verifies_as_not_set(self):
        packet_file = self.prepare()
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
        candidate = self.root / "candidate.png"
        kit.key_image((16, 16), {(8, 8): (11, 22, 33, 255)}).save(candidate)
        receipt = self.root / "receipt.json"
        receipt.write_text(json.dumps({"reference_crop_sha256": packet["reference_crop_sha256"], "reference_image_path": packet["reference_crop"],
                                       "image_input_attached": True, "tool_invocation_id": "t-1", "candidate_image": str(candidate),
                                       "candidate_sha256": kit.digest(candidate)}))
        self.assertEqual(crop.verify(packet_file, receipt)["style_anchor"], "not_set")


class StyleBoardLifecycleTests(AnchorGame):
    def test_a_style_board_goes_through_the_normal_lifecycle(self):
        write_settings(self.root)
        self.style_board()
        record = life.records(self.root, "mockups")[0]
        self.assertEqual((record["scope"], record["status"]), ("style", "approved"))
        self.assertEqual(life.reconcile_mockups(self.root)["status"], "consistent")

    def test_a_style_board_needs_no_storyboard_scene_even_when_a_storyboard_exists(self):
        import gamearts_storyboard as board
        write_settings(self.root)
        board.write(self.root, {"title": "T", "origin": "agent_authored", "brief": "x", "scenes": [{"id": "a", "title": "A", "summary": "s"}]})
        self.style_board()
        self.assertEqual(life.records(self.root, "mockups")[0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
