"""Guards for the shipped framework text: one owner per fact, mirrored trees, no versions, no engine, no corrupted text.

A written rule regrows unless a test fails when it is broken. These tests read the real repository files.
"""
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SKILLS, AGENT_SKILLS = ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"
SHIPPED_DIRS = ("scripts", "schemas", "docs", "presets", ".claude", ".agents")
ENGINE_DATA = "presets/engines/"  # the one place engine names may appear in shipped text: validated profile data (plan D-17)
SHIPPED_FILES = ("README.md", "README_INSTALL.md", "CLAUDE.md", "AGENTS.md")
ENGINE_SUFFIXES = {".gd", ".tscn", ".gdshader", ".import", ".godot"}
ENGINE_NAMES = {"project.godot", ".godot", ".gdignore"}


# Engines the framework has profiles for, and others it may get: shipped text outside presets/engines says "your engine". Word boundaries keep "community" apart from "unity".
ENGINE_WORDS = ("godot", "unity", "unreal", "defold", "phaser", "gamemaker", "game maker", "gdevelop", "cocos", "love2d", "monogame", "pixijs", "construct 3")
# Image tools and products the shipped text must not recommend or depend on. Formats the exports target (Aseprite, Tiled, the GIMP palette) and the host agents
# are named where the file format or the host is the point, so they are not listed here.
VENDOR_WORDS = ("texturepacker", "midjourney", "dall-e", "dalle", "stable diffusion", "spritecook", "pixellab", "leonardo.ai", "retro diffusion", "photoshop", "krita",
                "scenario.com", "layer.ai")
SKILL_BYTES = 12_000  # one skill; the skills were deliberately cut to about 40% of their first size and this keeps them from regrowing
SKILLS_TOTAL_BYTES = 80_000

MASTER = "GAME_ARTS_MASTER_STANDARD.md"
BRIDGE = "GAME_ARTS_MASTER_STANDARD_v7.7.md"  # the pointer older updaters look for; the owner deletes it once games have updated


def master_path():
    path = ROOT / MASTER
    assert path.is_file(), f"{MASTER} is missing"
    return path


def shipped_files():
    files = [ROOT / name for name in SHIPPED_FILES] + [master_path()]
    for folder in SHIPPED_DIRS:
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return sorted(set(files))


def shipped_text_files():
    return [p for p in shipped_files() if p.suffix in {".md", ".py", ".json", ".yml", ".yaml"}]


def markdown_files():
    return [p for p in shipped_files() if p.suffix == ".md"]


def read(path):
    return Path(path).read_text(encoding="utf-8")


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def master_headings():
    return {re.sub(r"^\d+\.\s+", "", line[3:]).strip() for line in read(master_path()).splitlines() if line.startswith("## ")}


def frontmatter(path):
    text = read(path)
    match = re.match(r"^---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    assert match, f"{relative(path)} has no front matter"
    return dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)


class LifecycleOperationsDocumentedTests(unittest.TestCase):
    """A pipeline step the lifecycle offers is a step the master and both lifecycle skills name: an operation nobody documents is one no agent runs."""

    def test_every_lifecycle_operation_is_named_in_the_master_and_in_both_skill_trees(self):
        import re
        source = (ROOT / "scripts" / "gamearts_asset_lifecycle.py").read_text(encoding="utf-8")
        operations = set(re.findall(r'(?<![\w.])op\("([a-z-]+)"', source))
        self.assertGreater(len(operations), 10, operations)
        texts = {"master": (ROOT / "GAME_ARTS_MASTER_STANDARD.md").read_text(encoding="utf-8"),
                 ".claude skill": (ROOT / ".claude" / "skills" / "game-arts-lifecycle" / "SKILL.md").read_text(encoding="utf-8"),
                 ".agents skill": (ROOT / ".agents" / "skills" / "game-arts-lifecycle" / "SKILL.md").read_text(encoding="utf-8")}
        missing = sorted(f"{name}: {op}" for name, text in texts.items() for op in operations if f"`{op}" not in text and op not in text)
        self.assertEqual(missing, [])


class MirroredTreesTests(unittest.TestCase):
    def test_both_skill_trees_hold_the_same_skills_with_identical_text(self):
        claude = {p.relative_to(CLAUDE_SKILLS).as_posix(): read(p) for p in CLAUDE_SKILLS.rglob("*") if p.is_file()}
        agents = {p.relative_to(AGENT_SKILLS).as_posix(): read(p) for p in AGENT_SKILLS.rglob("*") if p.is_file()}
        self.assertEqual(sorted(claude), sorted(agents), "the two skill trees list different files")
        for name in claude:
            self.assertEqual(claude[name].replace("\r\n", "\n"), agents[name].replace("\r\n", "\n"), f"{name} differs between the trees")

    def test_the_two_instruction_files_differ_only_in_the_tool_tokens(self):
        expected = (read(ROOT / "CLAUDE.md").replace("# CLAUDE.md", "# AGENTS.md").replace("Claude Code (claude.ai/code)", "Codex")
                    .replace(".claude/skills", ".agents/skills").replace("Claude Code", "Codex"))
        self.assertEqual(expected.replace("\r\n", "\n"), read(ROOT / "AGENTS.md").replace("\r\n", "\n"))

    def test_each_skill_has_valid_front_matter(self):
        for skill in sorted(CLAUDE_SKILLS.iterdir()):
            fields = frontmatter(skill / "SKILL.md")
            self.assertEqual(fields.get("name"), skill.name)
            description = fields.get("description", "")
            self.assertGreater(len(description), 40, skill.name)
            self.assertLessEqual(len(description), 1024, skill.name)
            self.assertNotIn(" #", description, f"{skill.name}: a ' #' in a description is read as a YAML comment and cuts it off")
            self.assertFalse(description.startswith(('"', "'")), skill.name)

    def test_every_skill_script_and_doc_it_names_exists(self):
        for skill in CLAUDE_SKILLS.glob("*/SKILL.md"):
            for token in re.findall(r"`((?:scripts|schemas|docs|presets)/[A-Za-z0-9_./-]+)`", read(skill)):
                self.assertTrue((ROOT / token).exists(), f"{relative(skill)} names {token}, which does not exist")


class OneOwnerTests(unittest.TestCase):
    def test_no_long_paragraph_is_copied_between_framework_files(self):
        seen = {}
        mirrored_agents = {p for p in AGENT_SKILLS.rglob("*") if p.is_file()} | {ROOT / "AGENTS.md"}
        for path in markdown_files():
            if path in mirrored_agents:
                continue  # the mirrors are checked by the identity tests above
            for paragraph in re.split(r"\n\s*\n", read(path).replace("\r\n", "\n")):
                text = " ".join(paragraph.split())
                if len(text) < 200 or text.startswith(("|", "```", "{", "[")):
                    continue
                if text in seen and seen[text] != path:
                    self.fail(f"the same paragraph is in {relative(seen[text])} and {relative(path)}: {text[:90]}...")
                seen[text] = path

    def test_skills_and_docs_cite_real_master_headings(self):
        headings = master_headings()
        for path in markdown_files():
            if path == master_path() or path in {p for p in AGENT_SKILLS.rglob("*") if p.is_file()}:
                continue
            for span in re.findall(r"(?<![*\w])\*([A-Z][^*\n]{12,})\*(?![*\w])", read(path)):
                if len(span.split()) < 3:
                    continue
                self.assertIn(span.strip(), headings, f"{relative(path)} cites '{span}', which is not a master heading")

    def test_master_headings_are_numbered_once_and_in_order(self):
        numbers = [int(m.group(1)) for line in read(master_path()).splitlines() if (m := re.match(r"^## (\d+)\. ", line))]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)), "master section numbers must be unique and consecutive")
        self.assertGreater(len(numbers), 20)

    def test_every_relative_link_resolves(self):
        for path in markdown_files():
            for target in re.findall(r"\]\(([^)\s]+)\)", read(path)):
                if re.match(r"^(https?:|mailto:|#)", target):
                    continue
                file_part = target.split("#", 1)[0]
                if not file_part:
                    continue
                self.assertTrue((path.parent / file_part).resolve().exists(), f"{relative(path)} links to missing {target}")


class ShippedLinkTests(unittest.TestCase):
    """The updater ships the master, skills, scripts, schemas and docs. A link from them to anything else breaks in a game."""
    NOT_SHIPPED = re.compile(r"(^|/)(README[A-Z_]*\.md|plans/|tests/|CLAUDE\.md|AGENTS\.md)")

    def test_shipped_text_links_only_to_shipped_files(self):
        for path in markdown_files():
            relative_path = relative(path)
            if not (relative_path.startswith(("docs/", ".claude/", ".agents/")) or path == master_path()):
                continue
            for target in re.findall(r"\]\(([^)\s]+)\)", read(path)):
                if re.match(r"^(https?:|mailto:|#)", target):
                    continue
                resolved = (path.parent / target.split("#", 1)[0]).resolve().relative_to(ROOT).as_posix()
                self.assertIsNone(self.NOT_SHIPPED.search(resolved), f"{relative_path} links to {target}, which is not installed in a game")


class NoVersionsTests(unittest.TestCase):
    LINK_TARGETS = re.compile(r"\]\([^)]*\)")

    def test_framework_text_carries_no_version_labels(self):
        label = re.compile(r"(?<![\w.])[vV]\d+\.\d+(?:\.\d+)?\b|^\s*\**Version\**:", re.M)
        for path in markdown_files() + [p for p in shipped_text_files() if p.suffix in {".py", ".json"}]:
            text = self.LINK_TARGETS.sub("]()", read(path))
            self.assertIsNone(label.search(text), f"{relative(path)} has a version label: {label.search(text) and label.search(text).group(0)!r}")

    def test_no_framework_text_names_the_master_by_its_legacy_file_name(self):
        legacy = re.compile(r"GAME_ARTS_MASTER_STANDARD_v\d")
        for path in shipped_text_files():
            text = self.LINK_TARGETS.sub("]()", read(path))
            self.assertIsNone(legacy.search(text), f"{relative(path)} names the master with a version suffix; refer to it by pattern")

    def test_the_updater_finds_the_master_without_a_constant_name(self):
        text = read(ROOT / "scripts" / "sync_local_agents.py")
        self.assertNotIn("v7.", text)
        self.assertIn("MASTER_GLOB", text)

    def test_no_master_standard_field_is_written(self):
        for path in (ROOT / "scripts").glob("*.py"):
            self.assertNotIn("master_standard", read(path), relative(path))


class NoEngineTests(unittest.TestCase):
    def test_no_engine_file_exists_in_the_repository(self):
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or "plans" in path.parts:
                continue
            self.assertNotIn(path.suffix, ENGINE_SUFFIXES, relative(path))
            self.assertNotIn(path.name, ENGINE_NAMES, relative(path))
        self.assertFalse((ROOT / "godot").exists())

    def test_no_engine_workflow_exists(self):
        for workflow in (ROOT / ".github" / "workflows").glob("*.y*ml"):
            self.assertNotRegex(workflow.name.lower(), "godot|unity|unreal", workflow.name)
            self.assertNotRegex(read(workflow).lower(), "godot|unity|unreal", workflow.name)

    def test_shipped_text_names_no_engine_and_no_single_game(self):
        for path in shipped_text_files():
            text = read(path).lower()
            for word in ("godot", "oilfield"):
                if word == "godot" and relative(path).startswith(ENGINE_DATA):
                    continue  # an engine profile is data about an engine; everywhere else shipped text says "your engine"
                self.assertNotIn(word, text, f"{relative(path)} mentions '{word}': engine work and one game's rules do not belong in the universal framework")

    def test_no_engine_and_no_vendor_is_named_outside_the_engine_profiles(self):
        engine = re.compile(r"\b(" + "|".join(re.escape(w) for w in ENGINE_WORDS) + r")\b")
        vendor = re.compile("|".join(re.escape(w) for w in VENDOR_WORDS))
        for path in shipped_text_files():
            if relative(path).startswith(ENGINE_DATA):
                continue
            text = read(path).lower()
            found = engine.search(text)
            self.assertIsNone(found, f"{relative(path)} names the engine '{found and found.group(0)}': say \"your engine\"; engine facts belong in presets/engines")
            found = vendor.search(text)
            self.assertIsNone(found, f"{relative(path)} names '{found and found.group(0)}': shipped text recommends no product")

    def test_the_engine_data_folder_holds_only_validated_json_data(self):
        folder = ROOT / "presets" / "engines"
        self.assertTrue(folder.is_dir())
        for path in folder.rglob("*"):
            if path.is_file():
                self.assertEqual(path.suffix, ".json", f"{relative(path)}: engine profiles are data; code, shaders and scenes never belong here")
                self.assertNotIn(path.suffix, ENGINE_SUFFIXES)

class SkillBudgetTests(unittest.TestCase):
    """The skills route to the master and keep only their own procedure. Their size is part of the design, so it is guarded."""

    def test_no_skill_outgrows_its_budget_and_all_together_stay_small(self):
        sizes = {p.parent.name: p.stat().st_size for p in CLAUDE_SKILLS.glob("*/SKILL.md")}
        self.assertTrue(sizes)
        for name, size in sizes.items():
            self.assertLessEqual(size, SKILL_BYTES, f"{name}/SKILL.md is {size} bytes; the budget is {SKILL_BYTES}. Move policy to the master and keep only procedure here")
        self.assertLessEqual(sum(sizes.values()), SKILLS_TOTAL_BYTES, f"the skills total {sum(sizes.values())} bytes; the budget is {SKILLS_TOTAL_BYTES}")


class CorruptedTextTests(unittest.TestCase):
    def test_no_tabs_stray_escapes_or_literal_newlines_in_documents(self):
        for path in markdown_files():
            text = read(path)
            self.assertNotIn("\t", text, f"{relative(path)} contains a TAB (it corrupted 'top_down' once)")
            self.assertNotIn("\\`", text, f"{relative(path)} contains a literal backslash-backtick")
            prose = re.sub(r"```.*?```|`[^`\n]*`", "", text, flags=re.S)
            self.assertNotIn("\\n", prose, f"{relative(path)} contains a literal \\n outside code")

    def test_documents_are_utf8_without_replacement_characters(self):
        for path in markdown_files():
            self.assertNotIn("�", read(path), relative(path))

    def test_no_known_glued_lines(self):
        for path in markdown_files():
            self.assertNotRegex(read(path), r"atlas JSON- state metadata", relative(path))


class RepositoryHygieneTests(unittest.TestCase):
    def test_gitignore_keeps_bytecode_and_ide_state_out_of_the_repository(self):
        ignore = read(ROOT / ".gitignore")
        for entry in ("__pycache__/", "*.py[cod]", ".vs/"):
            self.assertIn(entry, ignore)

    def test_the_master_is_unversioned_and_the_only_other_file_is_the_small_bridge(self):
        found = {p.name for p in ROOT.glob("GAME_ARTS_MASTER_STANDARD*.md")}
        self.assertIn(MASTER, found)
        self.assertLessEqual(found - {MASTER}, {BRIDGE}, "no other master-named file may exist")
        bridge = ROOT / BRIDGE
        if bridge.exists():
            text = read(bridge)
            self.assertLess(len(text), 1200, "the bridge must stay a pointer, never a second copy of the standard")
            self.assertIn(MASTER, text)
            self.assertIn("deleted", text)
            self.assertFalse([line for line in text.splitlines() if line.startswith("## ")], "the bridge carries no policy sections")

    def test_the_updater_never_ships_the_bridge_to_a_game(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import sync_local_agents
        with tempfile.TemporaryDirectory() as folder:
            tree = Path(folder)
            for name in (".claude", ".agents", "scripts", "schemas", "docs"):
                shutil.copytree(ROOT / name, tree / name, ignore=shutil.ignore_patterns("__pycache__"))
            for name in (MASTER, BRIDGE):
                if (ROOT / name).exists():
                    shutil.copy2(ROOT / name, tree / name)
            wanted = {p.as_posix() for p in sync_local_agents.candidates(tree)}
            self.assertIn(MASTER, wanted)
            self.assertNotIn(BRIDGE, wanted)


class PortablePathTests(unittest.TestCase):
    """The framework is downloaded onto other people's machines, so shipped text never names a path that exists on only one of them."""

    # A drive-letter path, a user's home folder or an app-data folder. A URL scheme such as https:// is not one: its letter follows another letter.
    MACHINE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?=[^\s/\\])|/Users/[^/\s]+/|/home/[^/\s]+/|AppData[\\/]")

    def test_no_shipped_text_names_a_path_on_one_machine(self):
        found = [f"{relative(path)}: {match.group(0)}" for path in shipped_text_files() for match in self.MACHINE_PATH.finditer(read(path))]
        self.assertEqual(found, [], "shipped text uses relative paths, <game> placeholders or environment variables, never a path from one machine")

    def test_the_pattern_catches_what_it_is_for_and_leaves_ordinary_text_alone(self):
        for sample in (r"C:\Users\someone\game", "H:/Source/Repos/game", "/Users/someone/game", "/home/someone/game", r"x\AppData\Local\Temp"):
            self.assertTrue(self.MACHINE_PATH.search(sample), sample)
        for sample in ("https://example.com/a", "file:///a", "scripts/gamearts_palette.py", "<game>/.gamearts/outputs", "$CLAUDE_PROJECT_DIR/scripts", "note: next"):
            self.assertIsNone(self.MACHINE_PATH.search(sample), sample)


class WizardQuestionsDocumentedTests(unittest.TestCase):
    """docs/PROJECT_SETTINGS.md lists the wizard's questions and when each appears. The wizard owns that list, so the table must equal it."""

    def test_the_settings_guide_lists_every_question_in_order_with_the_wizards_own_wording(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import gamearts_setup
        section = read(ROOT / "docs" / "PROJECT_SETTINGS.md").split("## The questions", 1)[1].split("\n## ", 1)[0]
        rows = re.findall(r"^\| `([a-z_]+)` \| (.+?) \|$", section, re.M)
        self.assertEqual(rows, [(name, gamearts_setup.TRIGGERS[name]) for name in gamearts_setup.ORDER])


if __name__ == "__main__":
    unittest.main()
