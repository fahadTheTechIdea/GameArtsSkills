"""The owner's fallback image generator: used only when asked for explicitly, with the reason recorded; never assumed, never a way round the owner's choice."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gamearts_testkit import make_mockup, shaded_picture, write_settings

import gamearts_asset_lifecycle as life  # noqa: E402  (the testkit puts scripts/ on the path)
import gamearts_common as common  # noqa: E402
import gamearts_disclosure as disclosure  # noqa: E402
import gamearts_doctor as doctor  # noqa: E402
import gamearts_report as report  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gamearts_asset_lifecycle.py"
OUT = ".gamearts/outputs"
SPRITECOOK = {"tool": "connected_tool", "tool_name": "SpriteCook"}
PROMPT = "A village pitch in warm afternoon light, elevated 3/4 view."


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "game"
        self.root.mkdir()

    def choose(self, **generation):
        write_settings(self.root, image_generation=generation)

    def picture(self):
        path = Path(self._tmp.name) / "tool_output.png"
        shaded_picture((60, 40), (80, 140, 60)).save(path, format="PNG")
        return path

    def record(self):
        return common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"][0]


class SettingTests(Case):
    def test_a_fallback_validates_and_a_connected_one_needs_its_name(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        self.assertEqual(life.check_settings(self.root)["image_generation"]["fallback"], SPRITECOOK)
        self.choose(tool="built_in_image_gen", fallback={"tool": "connected_tool"})
        with self.assertRaises(ValueError):
            life.check_settings(self.root)

    def test_the_owners_own_picture_is_not_a_fallback_tool(self):
        self.choose(tool="built_in_image_gen", fallback={"tool": "user_supplied"})
        with self.assertRaises(ValueError):
            life.check_settings(self.root)

    def test_choosing_a_fallback_never_reopens_approved_art(self):
        write_settings(self.root, image_generation={"tool": "built_in_image_gen"})
        before = common.canonical_settings_hash(common.read_json(self.root / ".gamearts" / "project.json"))
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        self.assertEqual(common.canonical_settings_hash(common.read_json(self.root / ".gamearts" / "project.json")), before)


FIRST = {"tool": "connected_tool", "tool_name": "First Tool"}
SECOND = {"tool": "connected_tool", "tool_name": "Second Tool", "notes": "model two"}


class ChainTests(Case):
    """The owner's ordered list of other image generators: one is the same as a list of one, each is used only by its number and with a reason, none is assumed."""

    def test_the_helper_gives_one_list_for_an_object_a_list_or_nothing(self):
        self.assertEqual(common.image_fallbacks({"tool": "built_in_image_gen"}), [])
        self.assertEqual(common.image_fallbacks(None), [])
        self.assertEqual(common.image_fallbacks({"fallback": FIRST}), [FIRST])
        self.assertEqual(common.image_fallbacks({"fallback": [FIRST, SECOND]}), [FIRST, SECOND])

    def test_the_contract_takes_an_ordered_list_and_refuses_a_bad_one(self):
        self.choose(tool="built_in_image_gen", fallback=[FIRST, SECOND])
        self.assertEqual(life.check_settings(self.root)["image_generation"]["fallback"], [FIRST, SECOND])
        for bad in ([FIRST, FIRST], [FIRST, {"tool": "connected_tool"}], [FIRST, {"tool": "user_supplied"}], []):
            with self.subTest(bad=bad):
                self.choose(tool="built_in_image_gen", fallback=bad)
                with self.assertRaises(ValueError):
                    life.check_settings(self.root)

    def test_each_tool_in_the_list_registers_by_its_number_and_the_position_is_recorded(self):
        self.choose(tool="built_in_image_gen", fallback=[FIRST, SECOND])
        for number, name, model in ((1, "First Tool", None), (2, "Second Tool", "gpt-image-2.5")):
            life.register_generated_mockup(self.root, self.picture(), f"market-{number}", "v001", "scene", PROMPT, model=model,
                                           use_fallback=number, fallback_reason="the tools before it are not in this session")
        rows = {row["mockup_id"]: row for row in common.read_json(self.root / OUT / "manifests" / "mockups.json")["mockups"]}
        for number, name in ((1, "First Tool"), (2, "Second Tool")):
            self.assertEqual(rows[f"market-{number}"]["tool_name"], name)
            provenance = common.read_json(self.root / rows[f"market-{number}"]["metadata"])["provenance"]
            self.assertEqual((provenance["generator_role"], provenance["fallback_position"]), ("fallback", number))

    def test_a_bare_use_fallback_means_the_first_and_a_number_outside_the_list_is_refused(self):
        self.choose(tool="built_in_image_gen", fallback=[FIRST, SECOND])
        life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT, use_fallback=True, fallback_reason="unavailable")
        self.assertEqual(self.record()["tool_name"], "First Tool")
        for number in (0, 3, "2"):
            with self.subTest(number=number), self.assertRaisesRegex(ValueError, "from 1 to 2"):
                life.register_generated_mockup(self.root, self.picture(), "other", "v001", "scene", PROMPT, use_fallback=number, fallback_reason="unavailable")

    def test_every_tool_in_the_list_passes_the_gate_and_one_outside_it_does_not(self):
        self.choose(tool="built_in_image_gen", fallback=[FIRST, SECOND])
        for name in ("second tool", "First Tool"):
            image, metadata = make_mockup(self.root, f"scene-{name.split()[0].lower()}")
            body = common.read_json(metadata)
            body.update({"tool_mode": "connected_tool", "tool_name": name})
            common.atomic_write_json(metadata, body)
            self.assertEqual(life.register_mockup(self.root, metadata, image)["status"], "generated")
        image, metadata = make_mockup(self.root, "scene-other")
        body = common.read_json(metadata)
        body.update({"tool_mode": "connected_tool", "tool_name": "Third Tool"})
        common.atomic_write_json(metadata, body)
        with self.assertRaisesRegex(ValueError, "connected tool Third Tool"):
            life.register_mockup(self.root, metadata, image)

    def test_the_command_line_takes_the_number(self):
        self.choose(tool="built_in_image_gen", fallback=[FIRST, SECOND])
        prompt = Path(self._tmp.name) / "prompt.txt"
        prompt.write_text(PROMPT, encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "register-generated", "--game-root", str(self.root), "--image", str(self.picture()), "--id", "market",
                               "--revision", "v001", "--scope", "scene", "--prompt-file", str(prompt), "--use-fallback", "2", "--fallback-reason", "nothing before it is here"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.record()["tool_name"], "Second Tool")

    def test_the_doctor_the_report_and_the_disclosure_show_every_tool_and_which_one_was_used(self):
        self.choose(tool="built_in_image_gen", fallback=[FIRST, SECOND])
        detail = next(item["detail"] for item in doctor.check_settings(self.root) if item["name"] == "image generator")
        self.assertIn("fallback 1: connected_tool (First Tool)", detail)
        self.assertIn("fallback 2: connected_tool (Second Tool) with the note: model two", detail)
        text = Path(report.build(self.root)["path"]).read_text(encoding="utf-8")
        for expected in ("If that is unavailable (1)", "If that is unavailable too (2)", "Note with the fallback (2)", "Second Tool"):
            self.assertIn(expected, text)
        entry = disclosure._mockup_entry({"mockup_id": "m", "revision": "v001", "scope": "scene", "tool_mode": "connected_tool", "tool_name": "Second Tool",
                                          "provenance": {"generator_role": "fallback", "fallback_position": 2}})
        self.assertEqual((entry["generator_role"], entry["fallback_position"]), ("fallback", 2))
        self.choose(tool="built_in_image_gen", fallback=FIRST)  # one tool reads as it always did
        detail = next(item["detail"] for item in doctor.check_settings(self.root) if item["name"] == "image generator")
        self.assertIn("; fallback: connected_tool (First Tool)", detail)


class RegisterTests(Case):
    def test_the_fallback_tool_registers_and_the_reason_is_recorded_with_the_picture(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        result = life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT, model="gpt-image-2.5",
                                                use_fallback=True, fallback_reason="Codex is not available in this Claude Code session")
        self.assertEqual(result["status"], "generated")
        row = self.record()
        self.assertEqual((row["tool_mode"], row["tool_name"]), ("connected_tool", "SpriteCook"))
        metadata = common.read_json(self.root / row["metadata"])
        self.assertEqual(metadata["provenance"]["generator_role"], "fallback")
        self.assertIn("not available", metadata["provenance"]["fallback_reason"])
        self.assertEqual(metadata["provenance"]["model"], "gpt-image-2.5")

    def test_the_main_tool_still_registers_without_any_fallback_mark(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT)
        row = self.record()
        self.assertEqual(row["tool_mode"], "built_in_image_gen")
        self.assertNotIn("generator_role", common.read_json(self.root / row["metadata"])["provenance"])

    def test_the_fallback_is_refused_without_a_reason(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        with self.assertRaisesRegex(ValueError, "why the main image generator was not used"):
            life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT, use_fallback=True)
        self.assertFalse((self.root / OUT / "manifests" / "mockups.json").exists())

    def test_a_game_with_no_fallback_refuses_it_so_the_main_tool_is_the_only_one(self):
        self.choose(tool="built_in_image_gen")
        with self.assertRaisesRegex(ValueError, "no fallback image generator"):
            life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT, use_fallback=True, fallback_reason="unavailable")

    def test_a_tool_that_is_neither_the_main_nor_the_fallback_is_still_refused(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        with self.assertRaisesRegex(ValueError, "image generator is built_in_image_gen"):
            life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT, tool_mode="cli_image_gen")
        with self.assertRaisesRegex(ValueError, "connected tool Other"):
            life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT, tool_mode="connected_tool", tool_name="Other")

    def test_naming_the_fallback_tool_by_hand_is_accepted_but_not_marked_as_the_fallback_path(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        image, metadata = make_mockup(self.root, "scene-a")
        body = common.read_json(metadata)
        body.update({"tool_mode": "connected_tool", "tool_name": "spritecook"})
        common.atomic_write_json(metadata, body)
        self.assertEqual(life.register_mockup(self.root, metadata, image)["status"], "generated")

    def test_the_use_of_the_fallback_cannot_also_name_a_tool(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        with self.assertRaisesRegex(ValueError, "do not also name a tool"):
            life.register_generated_mockup(self.root, self.picture(), "market", "v001", "scene", PROMPT, tool_mode="cli_image_gen",
                                           use_fallback=True, fallback_reason="unavailable")

    def test_the_command_line_takes_the_flags(self):
        self.choose(tool="built_in_image_gen", fallback=SPRITECOOK)
        prompt = Path(self._tmp.name) / "prompt.txt"
        prompt.write_text(PROMPT, encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "register-generated", "--game-root", str(self.root), "--image", str(self.picture()), "--id", "market",
                               "--revision", "v001", "--scope", "scene", "--prompt-file", str(prompt), "--use-fallback", "--fallback-reason", "Codex is not installed"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "generated")


if __name__ == "__main__":
    unittest.main()
