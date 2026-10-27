"""Contracts: every schema is valid and used, every script contract names a real schema, and the documented examples validate."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

from gamearts_testkit import settings, write_settings

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
sys.path.insert(0, str(ROOT / "scripts"))
import gamearts_common as common  # noqa: E402
import gamearts_storyboard as board  # noqa: E402


def schema_names():
    return sorted(p.name[: -len(".schema.json")] for p in SCHEMAS.glob("*.schema.json"))


def script_schema_references():
    pattern = re.compile(r"""(?:validate_schema|_validate)\(\s*[^,()]+,\s*["']([a-z0-9-]+)["']""")
    names = {}
    for script in sorted((ROOT / "scripts").glob("*.py")):
        for name in pattern.findall(script.read_text(encoding="utf-8")):
            names.setdefault(name, set()).add(script.name)
    return names


def json_blocks(path):
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", path.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S)]


class SchemaFileTests(unittest.TestCase):
    def test_every_schema_is_a_valid_2020_12_schema(self):
        for name in schema_names():
            schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema", name)

    def test_every_schema_a_script_names_exists(self):
        existing = set(schema_names())
        for name, scripts in script_schema_references().items():
            self.assertIn(name, existing, f"{sorted(scripts)} validate against a schema that does not exist: {name}")

    def test_every_schema_is_enforced_by_some_script(self):
        used = set(script_schema_references())
        for name in schema_names():
            if name == "mockup-blueprint":
                used |= {name} if "mockup-blueprint" in (ROOT / "scripts" / "validate_blueprint.py").read_text(encoding="utf-8") else set()
            self.assertIn(name, used, f"schema {name} is enforced by no script (an unread contract is an unfinished one)")

    def test_a_missing_schema_is_an_error_not_a_skip(self):
        with self.assertRaises(ValueError):
            common.validate_schema({}, "no-such-contract")


class RecordShapeTests(unittest.TestCase):
    def test_a_minimal_asset_record_is_valid_and_a_record_without_files_is_not(self):
        record = {"asset_id": "a", "status": "generated", "bundle_path": ".gamearts/outputs/assets/generated/a_v001", "files": ["a.png"]}
        common.validate_schema(record, "gamearts-assets-manifest", ("properties", "assets", "items"))
        del record["files"]
        with self.assertRaises(ValueError):
            common.validate_schema(record, "gamearts-assets-manifest", ("properties", "assets", "items"))

    def test_statuses_outside_the_three_lifecycle_states_are_refused(self):
        record = {"asset_id": "a", "status": "approvedish", "bundle_path": "x", "files": ["a.png"]}
        with self.assertRaises(ValueError):
            common.validate_schema(record, "gamearts-assets-manifest", ("properties", "assets", "items"))

    def test_the_blueprint_accepts_the_current_and_the_legacy_format_marker_only(self):
        schema = json.loads((SCHEMAS / "mockup-blueprint.schema.json").read_text(encoding="utf-8"))
        marker = schema["properties"]["schema_version"]
        self.assertEqual(sorted(marker["enum"]), ["1.0", "7.2"])

    def test_owner_confirmed_settings_need_who_and_when(self):
        common.validate_schema(settings(), "gamearts-project")
        for field in ("confirmed_at", "confirmed_by"):
            body = settings()
            del body[field]
            with self.assertRaises(ValueError):
                common.validate_schema(body, "gamearts-project")

    def test_the_storyboard_contract_has_no_version_field_and_refuses_unknown_keys(self):
        schema = json.loads((SCHEMAS / "gamearts-storyboard.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(any("version" in key for key in schema["properties"]))
        self.assertIs(schema["additionalProperties"], False)

    def test_the_bundle_and_atlas_contracts_record_engine_validation_not_engine_names(self):
        for name in ("gamearts-bundle", "gamearts-atlas"):
            text = (SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8")
            self.assertIn("engine_validation", text, name)


class DocumentedExampleTests(unittest.TestCase):
    """An example in a guide that no longer validates teaches agents to write invalid files."""

    def test_the_frames_job_example(self):
        job = json_blocks(ROOT / "docs" / "ATLAS_GENERATION.md")[0]
        common.validate_schema(job, "gamearts-frames-job")

    def test_the_component_job_and_cleanup_examples(self):
        blocks = json_blocks(ROOT / "docs" / "COMPONENT_ANIMATION.md")
        common.validate_schema(blocks[0], "gamearts-component-job")
        cleanup = next(b for b in blocks if "detached_components" in b)
        common.validate_schema(cleanup, "gamearts-cleanup")
        inventory = next(b for b in blocks if "detached_inventory" in b)
        self.assertIn("parent_cleanup_evidence", inventory)

    def test_the_project_settings_example(self):
        example = json_blocks(ROOT / "docs" / "PROJECT_SETTINGS.md")
        full = next(b for b in example if "art_style" in b)
        common.validate_schema(full, "gamearts-project")

    def test_the_storyboard_draft_example_is_accepted_by_write(self):
        draft = json_blocks(ROOT / "docs" / "STORYBOARD.md")[0]
        with tempfile.TemporaryDirectory() as root:
            write_settings(root)
            board.write(root, draft, "agent", "example from the guide")
            self.assertEqual(board.audit(root), [])

    def test_the_lifecycle_record_examples_have_the_documented_shape(self):
        metadata, record = json_blocks(ROOT / "docs" / "ASSET_LIFECYCLE.md")
        for key in ("mockup_id", "revision", "scope", "status", "file", "sha256", "prompt", "tool_mode", "created_at_utc"):
            self.assertIn(key, metadata)
        placeholder = dict(metadata, sha256="0" * 64)
        common.validate_schema(placeholder, "gamearts-mockup-metadata")
        record = json.loads(json.dumps(record))
        record["artifact_hashes"] = {k: "0" * 64 for k in record["artifact_hashes"]}
        record["source_mockups"][0]["reference_sha256"] = "0" * 64
        common.validate_schema(record, "gamearts-assets-manifest", ("properties", "assets", "items"))


if __name__ == "__main__":
    unittest.main()
