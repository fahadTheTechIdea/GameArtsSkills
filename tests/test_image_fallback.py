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
