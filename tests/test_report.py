"""The offline art report (plan P13.1): built only from the records, safe to open, and rebuilt after every change."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image

import gamearts_testkit as kit
from gamearts_testkit import key_image, make_mockup, make_sheet, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_report as report  # noqa: E402
import gamearts_storyboard as board  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ".gamearts/outputs"
VOID = {"meta", "img", "br", "hr", "input", "link"}
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


class Page(HTMLParser):
    """Collects what the tests assert on and checks that every element is closed."""

    def __init__(self, text):
        super().__init__()
        self.stack, self.errors, self.images, self.links, self.cards, self.tags = [], [], [], [], [], []
        self.in_details = []
        self.lang = None
        self.feed(text)
        self.close()
        if self.stack:
            self.errors.append(f"unclosed: {self.stack}")

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if tag == "html":
            self.lang = attrs.get("lang")
        if tag == "img":
            self.images.append(attrs)
        if tag in ("a", "link"):
            self.links.append(attrs)
        if attrs.get("data-record"):
            self.cards.append({"record": attrs["data-record"], "status": attrs.get("data-status"), "in_details": "details" in self.stack})
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> with {self.stack[-3:]}")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()


class ReportCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, **kwargs):
        return report.build(self.root, now=NOW, **kwargs)

    def html(self):
        return (self.root / report.REPORT / "index.html").read_text(encoding="utf-8")

    def page(self):
        return Page(self.html())

    def approved_mockup(self, mockup_id="test-scene", revision="v001", reference="approved-in-test"):
        image, metadata = make_mockup(self.root, mockup_id, revision, "world")
        life.register_mockup(self.root, metadata, image)
        life.approve_mockup(self.root, mockup_id, revision, reference)

    def generated_mockup(self, mockup_id, revision="v001"):
        image, metadata = make_mockup(self.root, mockup_id, revision, "world")
        life.register_mockup(self.root, metadata, image)

    def generated_asset(self, asset_id="workshop", revision="v001", source=("test-scene", "v001")):
        name = f"{asset_id}_{revision}"
        folder = self.root / OUT / "assets/generated" / name
        folder.mkdir(parents=True)
        make_sheet(folder, f"{name}_sheet", asset_id)
        life.register_asset(self.root, name, revision, f"{OUT}/assets/generated/{name}", [source])
        return name


class PageShapeTests(ReportCase):
    def test_a_game_with_nothing_yet_gets_a_valid_page_that_says_what_to_do_first(self):
        result = self.build()
        page = self.page()
        self.assertEqual(page.errors, [])
        self.assertEqual(page.lang, "en")
        self.assertIn("Set up the game's art settings", result["next_steps"][0])
        self.assertEqual(result["counts"], {"mockups": 0, "assets": 0, "withdrawn": 0})
        self.assertIn("No mockups yet.", self.html())

    def test_the_page_is_self_contained_and_needs_no_network_and_no_script(self):
        write_settings(self.root)
        self.approved_mockup()
        self.generated_asset()
        self.build()
        text = self.html()
        self.assertNotRegex(text, r"""(?i)(src|href)\s*=\s*["'](https?:|//|javascript:|data:)""")
        self.assertNotIn("<script", text.lower())
        self.assertNotIn("@import", text)
        self.assertEqual([a for a in self.page().links if a.get("rel") == "stylesheet"], [])

    def test_there_is_one_title_heading_and_every_image_has_a_text_alternative(self):
        write_settings(self.root)
        self.approved_mockup()
        self.generated_asset()
        self.build()
        page = self.page()
        self.assertEqual(page.tags.count("h1"), 1)
        self.assertGreaterEqual(len(page.images), 2)
        for image in page.images:
            self.assertTrue(image.get("alt", "").strip(), image)

    def test_user_text_is_escaped_everywhere_it_is_shown(self):
        write_settings(self.root, project_id="a<b>&c")
        self.approved_mockup(reference='<script>alert(1)</script> yes & "ok"')
        self.build()
        text = self.html()
        self.assertNotIn("<script", text.lower())
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertIn("a&lt;b&gt;&amp;c", text)
        self.assertEqual(self.page().errors, [])

    def test_the_approval_words_are_shown_as_a_quote(self):
        write_settings(self.root)
        self.approved_mockup(reference="Yes, this is the look I want.")
        self.build()
        self.assertIn("<blockquote>Yes, this is the look I want.</blockquote>", self.html())


class RecordsOnlyTests(ReportCase):
    def test_every_card_carries_exactly_the_status_its_record_holds(self):
        write_settings(self.root)
        self.approved_mockup("scene-a")
        self.generated_mockup("scene-b")
        self.generated_mockup("scene-c")
        life.revoke(self.root, "mockups", "scene-c", "not the right mood", "v001")
        self.generated_asset("workshop", source=("scene-a", "v001"))
        self.build()
        shown = {card["record"]: card["status"] for card in self.page().cards}
        expected = {f"mockup:{r['mockup_id']}:{r['revision']}": r["status"] for r in life.records(self.root, "mockups")}
        expected.update({f"asset:{r['asset_id']}:{r['revision']}": r["status"] for r in life.records(self.root, "assets")})
        self.assertEqual(shown, expected)
        self.assertEqual(sorted(set(shown.values())), ["approved", "generated", "revoked"])

    def test_withdrawn_items_are_collapsed_and_keep_their_reason(self):
        write_settings(self.root)
        self.generated_mockup("scene-c")
        life.revoke(self.root, "mockups", "scene-c", "not the right mood", "v001")
        self.build()
        cards = self.page().cards
        self.assertTrue(all(card["in_details"] for card in cards if card["status"] == "revoked"))
        self.assertIn("Withdrawn because: not the right mood", self.html())

    def test_mockup_images_point_at_the_real_files_through_relative_paths(self):
        write_settings(self.root)
        self.approved_mockup()
        self.build()
        folder = self.root / report.REPORT
        sources = [a["src"] for a in self.page().images]
        self.assertTrue(sources)
        for src in sources:
            self.assertFalse(src.startswith(("/", "http")))
            self.assertTrue((folder / src).resolve().is_file(), src)

    def test_a_record_with_a_missing_file_still_gets_a_card_without_an_image(self):
        write_settings(self.root)
        self.approved_mockup()
        record = life.records(self.root, "mockups")[0]
        (self.root / record["file"]).unlink()
        result = self.build()
        self.assertEqual([c["record"] for c in self.page().cards], ["mockup:test-scene:v001"])
        self.assertEqual(result["records"]["mockups"], "blocked")
        self.assertIn("needs attention", self.html())

    def test_reconcile_findings_are_listed_on_the_page(self):
        write_settings(self.root)
        self.generated_mockup("scene-b")
        (self.root / OUT / "mockups/generated/stray.png").write_bytes((self.root / OUT / "mockups/generated").glob("*.png").__next__().read_bytes())
        self.build()
        self.assertIn("Unregistered mockup image", self.html())

    def test_nothing_is_invented_for_a_record_without_approval_words(self):
        write_settings(self.root)
        self.generated_mockup("scene-b")
        self.build()
        self.assertNotIn("<blockquote>", self.html())
        self.assertNotIn("in your words", self.html())


class SettingsAndGuidanceTests(ReportCase):
    def test_the_settings_appear_in_plain_words_with_the_engine_notes(self):
        write_settings(self.root, art_style={"id": "pixel_art", "preset": "pixel_mid"}, directions="dirs_4",
                       image_generation={"tool": "user_supplied"}, engine_target={"profile": "godot"})
        self.build()
        text = self.html()
        for phrase in ("Pixel art, 16-bit era", "A tile map", "four directions", "you make the pictures yourself", "Godot",
                       "confirmed by the owner", "Notes for using the files in your engine or tool", "Nearest"):
            self.assertIn(phrase, text)

    def test_pixel_art_games_show_their_pictures_with_hard_pixels(self):
        write_settings(self.root, art_style={"id": "pixel_art"})
        self.approved_mockup()
        self.build()
        self.assertTrue(all("pixel" in (a.get("class") or "") for a in self.page().images))

    def test_other_styles_do_not_get_the_pixel_class(self):
        write_settings(self.root, art_style={"id": "vector"})
        self.approved_mockup()
        self.build()
        self.assertFalse(any("pixel" in (a.get("class") or "") for a in self.page().images))

    def test_a_screen_space_game_is_described_without_a_world(self):
        write_settings(self.root, world_kind="screen_space", screen={"base_resolution_px": [1280, 720]}, drop=("world", "directions"))
        self.build()
        text = self.html()
        self.assertIn("No ground world", text)
        self.assertIn("1280 × 720 px", text)
        self.assertNotIn("Tiles and viewpoint", text)

    def test_an_unknown_engine_is_named_with_no_profile_instead_of_guessing(self):
        write_settings(self.root, engine_target={"profile": "some-other-engine"})
        self.build()
        self.assertIn("some-other-engine (no profile installed)", self.html())

    def test_unreadable_settings_are_shown_on_the_page_and_the_report_still_builds(self):
        (self.root / ".gamearts").mkdir()
        (self.root / ".gamearts" / "project.json").write_text('{"project_id": "partial"}', encoding="utf-8")
        result = self.build()
        self.assertTrue(any("settings could not be read" in p for p in result["problems"]))
        self.assertIn("settings could not be read", self.html())
        self.assertIn("Set up the game's art settings", result["next_steps"][0])

    def test_a_missing_validator_package_stops_the_build_instead_of_hiding_it(self):
        write_settings(self.root)
        original = common.validate_schema

        def fails(*args, **kwargs):
            raise common.DependencyMissing("jsonschema is required for contract validation (pip install jsonschema)")
        common.validate_schema = fails
        try:
            with self.assertRaises(common.DependencyMissing):
                self.build()
        finally:
            common.validate_schema = original


class NextStepTests(unittest.TestCase):
    def steps(self, state="owner_confirmed", mockups=(), assets=(), storyboard=None):
        return report.next_steps(state, list(mockups), list(assets), storyboard)

    def test_each_state_names_the_right_next_thing(self):
        self.assertIn("Set up", self.steps("missing")[0])
        self.assertIn("Confirm", self.steps("inferred")[0])
        self.assertEqual(self.steps(), ["Everything registered is approved. Ask for the next piece of art."])
        generated = {"mockup_id": "m", "revision": "v001", "status": "generated"}
        self.assertEqual(self.steps(mockups=[generated]), ["Approve or ask for changes to the mockup m v001."])
        approved = dict(generated, status="approved")
        self.assertEqual(self.steps(mockups=[approved]), ["Plan the art from the approved mockup m v001."])
        built = {"asset_id": "a", "revision": "v001", "status": "generated", "source_mockups": [{"mockup_id": "m", "revision": "v001"}]}
        self.assertEqual(self.steps(mockups=[approved], assets=[built]), ["Review and approve the asset a v001."])
        failed = dict(built, technical_validation={"status": "failed"})
        self.assertEqual(self.steps(mockups=[approved], assets=[failed]), ["Fix and rebuild the asset a v001."])

    def test_a_withdrawn_asset_no_longer_counts_as_built_from_its_mockup(self):
        approved = {"mockup_id": "m", "revision": "v001", "status": "approved"}
        gone = {"asset_id": "a", "revision": "v001", "status": "revoked", "source_mockups": [{"mockup_id": "m", "revision": "v001"}]}
        self.assertEqual(self.steps(mockups=[approved], assets=[gone]), ["Plan the art from the approved mockup m v001."])

    def test_storyboard_steps_come_from_the_sequence_and_the_waiting_scenes(self):
        self.assertIn("Choose which storyboard scenes", self.steps(storyboard={"sequence": "proposed", "waiting": []})[0])
        waiting = [{"id": "a", "title": "Arrival"}, {"id": "b", "title": "Market"}]
        self.assertEqual(self.steps(storyboard={"sequence": "approved", "waiting": waiting}),
                         ["Make the mockup for the scene “Arrival” (1 more after it)."])

    def test_the_list_is_capped(self):
        many = [{"mockup_id": f"m{i}", "revision": "v001", "status": "generated"} for i in range(20)]
        self.assertEqual(len(self.steps(mockups=many)), report.MAX_NEXT_STEPS)


class StoryboardTests(ReportCase):
    def test_storyboard_progress_is_listed_from_the_document(self):
        write_settings(self.root)
        board.write(self.root, {"title": "First season", "origin": "agent_authored", "brief": "x",
                                "scenes": [{"id": "arrival", "title": "Arrival", "summary": "s"}, {"id": "match", "title": "First match", "summary": "s"}]})
        result = self.build()
        text = self.html()
        self.assertIn("Storyboard: First season", text)
        self.assertIn("Arrival", text)
        self.assertIn("Choose which storyboard scenes", " ".join(result["next_steps"]))


class PreviewTests(ReportCase):
    def preview_files(self):
        folder = self.root / report.REPORT / "previews"
        return sorted(p for p in folder.glob("*.png") if not p.name.endswith(".strip.png")) if folder.is_dir() else []

    def animation_files(self):
        folder = self.root / report.REPORT / "previews"
        return sorted(folder.glob("*.strip.png")) + sorted(folder.glob("*.gif")) if folder.is_dir() else []

    def test_a_sheet_preview_shows_the_key_colour_as_a_checkerboard_and_links_the_delivered_file(self):
        write_settings(self.root)
        self.approved_mockup()
        name = self.generated_asset()
        self.build()
        previews = self.preview_files()
        self.assertEqual(len(previews), 1)
        with Image.open(previews[0]) as shown:
            colours = set(shown.convert("RGB").getdata())
        self.assertNotIn((255, 0, 255), colours)
        self.assertIn(f"{name}_sheet.png", self.html())
        link = next(a["href"] for a in self.page().links if a.get("href") and a["href"].endswith("_sheet.png"))
        self.assertTrue(((self.root / report.REPORT) / link).resolve().is_file())

    def test_the_delivered_sheet_is_never_changed_by_the_report(self):
        write_settings(self.root)
        self.approved_mockup()
        self.generated_asset()
        sheet = next((self.root / OUT / "assets/generated").rglob("*_sheet.png"))
        before = common.sha256_file(sheet)
        self.build()
        self.assertEqual(common.sha256_file(sheet), before)

    def test_a_preview_of_an_asset_that_no_longer_exists_is_removed(self):
        write_settings(self.root)
        self.approved_mockup()
        self.generated_asset()
        self.build()
        stale = self.root / report.REPORT / "previews" / "gone_v001_0.png"
        stale.write_bytes(b"x")
        self.build()
        self.assertFalse(stale.exists())
        self.assertEqual(len(self.preview_files()), 1)

    def test_an_animation_is_shown_as_a_still_strip_with_a_link_to_the_gif(self):
        write_settings(self.root)
        self.approved_mockup()
        self.generated_asset()
        self.build()
        names = [p.name for p in self.animation_files()]
        self.assertEqual(len(names), 2, names)
        strip = next(img for img in self.page().images if img["src"].endswith(".strip.png"))
        self.assertIn("2 frames", strip["alt"])
        self.assertIn("200 ms", strip["alt"])
        self.assertEqual([img for img in self.page().images if img["src"].endswith(".gif")], [])  # nothing starts moving by itself
        gif = next(a["href"] for a in self.page().links if a.get("href", "").endswith(".gif"))
        self.assertTrue(((self.root / report.REPORT) / gif).resolve().is_file())
        self.assertIn("Play it as an animated GIF", self.html())

    def test_stale_animation_previews_are_removed_with_the_other_previews(self):
        write_settings(self.root)
        self.approved_mockup()
        self.generated_asset()
        self.build()
        folder = self.root / report.REPORT / "previews"
        for name in ("gone_v001_0.walk.E.gif", "gone_v001_0.walk.E.strip.png"):
            (folder / name).write_bytes(b"x")
        self.build()
        self.assertFalse((folder / "gone_v001_0.walk.E.gif").exists())
        self.assertFalse((folder / "gone_v001_0.walk.E.strip.png").exists())
        self.assertEqual(len(self.animation_files()), 2)

    def test_a_sheet_with_one_frame_per_animation_gets_no_animation_preview(self):
        write_settings(self.root)
        self.approved_mockup()
        name = "still_v001"
        folder = self.root / OUT / "assets/generated" / name
        folder.mkdir(parents=True)
        with tempfile.TemporaryDirectory() as frames:
            key_image((12, 10), {(4, 5): (20, 50, 90, 255)}).save(Path(frames) / "frame.png")
            kit.build_sheet({"_input_dir": frames, "name": f"{name}_sheet", "asset_id": "still", "columns": 1, "padding": 2,
                             "frames": [{"file": "frame.png", "name": "S0", "direction": "S", "pivot": [4, 9], "duration_ms": 100}]}, folder)
        life.register_asset(self.root, name, "v001", f"{OUT}/assets/generated/{name}", [("test-scene", "v001")])
        result = self.build()
        self.assertEqual(self.animation_files(), [])
        self.assertEqual(result["problems"], [])
        self.assertNotIn("Play it as an animated GIF", self.html())

    def test_an_animation_preview_that_cannot_be_made_is_named_on_the_page_and_the_report_still_builds(self):
        write_settings(self.root)
        self.approved_mockup()
        name = self.generated_asset()
        atlas = next((self.root / OUT / "assets/generated" / name).glob("*.atlas.json"))
        atlas.write_text("{not json", encoding="utf-8")
        result = self.build()
        self.assertTrue(any("animation preview" in problem for problem in result["problems"]), result["problems"])
        self.assertIn("animation preview", self.html())

    def test_an_asset_with_engine_ready_copies_says_so_and_calls_them_derived(self):
        write_settings(self.root)
        self.approved_mockup()
        name = self.generated_asset()
        life.approve_asset(self.root, name, "approved-in-test")
        self.build()
        self.assertNotIn("Engine-ready copies", self.html())
        life.export_runtime(self.root, name)
        self.build()
        text = self.html()
        self.assertIn("Engine-ready copies", text)
        self.assertIn("derived files, not new art", text)

    def test_a_wide_sheet_is_reduced_to_a_readable_width(self):
        big = self.root / "wide.png"
        Image.new("RGBA", (2000, 100), (255, 0, 255, 255)).save(big)
        target = self.root / "out" / "wide_preview.png"
        report.write_preview(big, target, pixel_art=True)
        with Image.open(target) as shown:
            self.assertEqual(shown.size, (report.PREVIEW_WIDTH, 32))


class LifecycleHookTests(ReportCase):
    def test_refresh_report_returns_the_path_it_built(self):
        write_settings(self.root)
        result = life.refresh_report(self.root)
        self.assertTrue(result["updated"])
        self.assertTrue(Path(result["path"]).is_file())

    def test_a_report_that_cannot_be_built_is_reported_not_raised(self):
        write_settings(self.root)
        original = report.build

        def broken(game_root, now=None):
            raise OSError("the disk is full")
        report.build = broken
        try:
            result = life.refresh_report(self.root)
        finally:
            report.build = original
        self.assertEqual(result["updated"], False)
        self.assertIn("the disk is full", result["problem"])

    def test_a_command_that_changes_a_record_names_the_rebuilt_report(self):
        write_settings(self.root)
        image, metadata = make_mockup(self.root, "cli-scene", "v001", "world")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "gamearts_asset_lifecycle.py"), "register", "--game-root", str(self.root),
                               "--metadata", str(metadata), "--image", str(image)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertTrue(result["report"]["updated"])
        self.assertIn("cli-scene", Path(result["report"]["path"]).read_text(encoding="utf-8"))

    def test_a_command_that_only_reads_does_not_touch_the_report(self):
        write_settings(self.root)
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "gamearts_asset_lifecycle.py"), "list", "--game-root", str(self.root),
                               "--kind", "mockups"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((self.root / report.REPORT).exists())

    def test_every_operation_that_changes_records_is_one_that_rebuilds_the_report(self):
        self.assertEqual(set(life.MUTATING_OPERATIONS),
                         {"register", "register-generated", "import-mockup", "approve-mockup", "register-asset", "import-asset", "approve", "approve-batch", "export-runtime", "revoke", "restore"})


class CommandLineTests(ReportCase):
    def test_the_command_writes_the_page_and_prints_where(self):
        write_settings(self.root)
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "gamearts_report.py"), "--game-root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        printed = json.loads(done.stdout)
        self.assertTrue(Path(printed["path"]).is_file())
        self.assertEqual(printed["problems"], [])

    def test_the_page_stays_out_of_version_control_by_living_with_the_system_files(self):
        self.assertEqual(report.REPORT.parts[:3], (".gamearts", "system", "report"))


if __name__ == "__main__":
    unittest.main()
