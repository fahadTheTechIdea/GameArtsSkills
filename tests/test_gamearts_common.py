"""The single owner of shared helpers: paths, locks, atomic writes, schema validation, key-colour pixel policy, settings."""
import ast
import os
import shutil
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from gamearts_testkit import PINK, key_image, settings, write_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gamearts_common as common  # noqa: E402


class SafeMemberTests(unittest.TestCase):
    def test_nested_relative_paths_resolve_inside_the_base(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual(common.safe_member(base, "a/b/c.png"), (Path(base) / "a" / "b" / "c.png").resolve())

    def test_escapes_and_absolute_paths_are_refused(self):
        with tempfile.TemporaryDirectory() as base:
            for bad in ("../x", "a/../../x", "/etc/passwd", "\\windows", "C:\\temp\\x.png", "", "  ", None, 5):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    common.safe_member(base, bad)


class AtomicWriteTests(unittest.TestCase):
    def test_concurrent_writers_never_share_a_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "state.json"
            errors = []

            def writer(number):
                try:
                    for _ in range(30):
                        common.atomic_write_json(target, {"writer": number})
                except Exception as exc:  # collected so the assertion below can show it
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertIn(json.loads(target.read_text())["writer"], range(6))
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["state.json"])

    def test_a_failed_write_leaves_no_temp_file_and_keeps_the_old_content(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "state.json"
            common.atomic_write_json(target, {"v": 1})
            with mock.patch.object(common.os, "replace", side_effect=OSError("denied")):
                with self.assertRaises(OSError):
                    common.atomic_write_json(target, {"v": 2})
            self.assertEqual(json.loads(target.read_text()), {"v": 1})
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["state.json"])


class FileLockTests(unittest.TestCase):
    HOLDER = ("import sys, time\n"
              "sys.path.insert(0, sys.argv[1])\n"
              "import gamearts_common as common\n"
              "with common.file_lock(sys.argv[2], name='holder'):\n"
              "    print('locked', flush=True)\n"
              "    time.sleep(120)\n")

    def holder(self, path):
        child = subprocess.Popen([sys.executable, "-c", self.HOLDER, str(Path(common.__file__).parent), str(path)],
                                 stdout=subprocess.PIPE, text=True)
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.assertEqual(child.stdout.readline().strip(), "locked")
        return child

    def test_a_live_owner_blocks_with_a_clear_message(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.lock"
            child = self.holder(path)
            try:
                with self.assertRaisesRegex(common.LockBusy, "Another lifecycle change is running"):
                    with common.file_lock(path, wait_seconds=0.2, name="lifecycle change"):
                        self.fail("must not acquire")
            finally:
                # The folder cannot be removed while the lock is held. In a Windows virtual environment python.exe is a
                # launcher: wait() returns for it while the real holder is still exiting, so wait for the lock itself.
                child.kill()
                child.wait()
                with common.file_lock(path, wait_seconds=10, name="test"):
                    pass

    def test_a_killed_owner_releases_the_lock_without_any_recovery_step(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.lock"
            child = self.holder(path)
            child.kill()
            child.wait()
            with common.file_lock(path, wait_seconds=10, name="test"):
                pass

    def test_a_waiter_gets_the_lock_when_the_owner_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.lock"
            order = []

            def first():
                with common.file_lock(path, name="first"):
                    order.append("first in")
                    time.sleep(0.3)
                    order.append("first out")

            thread = threading.Thread(target=first)
            thread.start()
            while not order:
                time.sleep(0.01)
            with common.file_lock(path, wait_seconds=10, name="second"):
                order.append("second in")
            thread.join()
            self.assertEqual(order, ["first in", "first out", "second in"])

    def test_the_lock_is_released_when_the_work_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.lock"
            with self.assertRaises(RuntimeError):
                with common.file_lock(path, name="test"):
                    raise RuntimeError("work failed")
            with common.file_lock(path, name="test"):
                pass

    def test_there_is_no_stale_state_to_leave_behind(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.lock"
            path.write_text("garbage left by an older version")
            with common.file_lock(path, name="test"):
                pass

class IdentifierRuleTests(unittest.TestCase):
    def test_mockup_ids_follow_the_one_lifecycle_rule(self):
        for good in ("city.scene", "city-scene_1", "a", "0day"):
            self.assertTrue(common.MOCKUP_ID.fullmatch(good), good)
        for bad in ("City_Scene", "-lead", ".lead", "has space", "", "a/b"):
            self.assertIsNone(common.MOCKUP_ID.fullmatch(bad), bad)

    def test_revision_and_slug_rules(self):
        self.assertTrue(common.REVISION.fullmatch("v001") and common.REVISION.fullmatch("v1234"))
        for bad in ("v1", "001", "V001", "v001a"):
            self.assertIsNone(common.REVISION.fullmatch(bad), bad)
        self.assertTrue(common.SLUG.fullmatch("Asset_1-b"))
        self.assertIsNone(common.SLUG.fullmatch("../x"))


class MoveRetryTests(unittest.TestCase):
    """A folder or file that was just written can be held open for a moment by a scanner or indexer on Windows; the move waits a little and asks again."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "bundle").mkdir()
        (self.root / "bundle" / "sheet.png").write_bytes(b"png")
        self.source, self.destination = self.root / "bundle", self.root / "approved"
        self.sleeps = []
        self._patches = [mock.patch.object(common, "RETRY_SHARING_VIOLATIONS", True), mock.patch.object(common.time, "sleep", self.sleeps.append)]
        for patch in self._patches:
            patch.start()

    def tearDown(self):
        for patch in self._patches:
            patch.stop()
        self._tmp.cleanup()

    def flaky_move(self, failures, real=shutil.move):
        calls = []

        def move(source, destination):
            calls.append(source)
            if len(calls) <= failures:
                raise PermissionError(5, "Access is denied")
            return real(source, destination)
        return calls, mock.patch.object(common.shutil, "move", move)

    def test_a_move_that_hits_a_sharing_violation_is_retried_and_then_succeeds(self):
        calls, patched = self.flaky_move(3)
        with patched:
            common.move_path(self.source, self.destination)
        self.assertEqual(len(calls), 4)
        self.assertEqual((self.destination / "sheet.png").read_bytes(), b"png")
        self.assertFalse(self.source.exists())

    def test_the_pauses_grow_and_the_total_wait_is_bounded(self):
        calls, patched = self.flaky_move(10 ** 6)
        with patched, self.assertRaises(PermissionError):
            common.move_path(self.source, self.destination)
        self.assertEqual(len(calls), common.REPLACE_ATTEMPTS)
        self.assertEqual(self.sleeps, sorted(self.sleeps))
        self.assertGreater(self.sleeps[-1], self.sleeps[0])  # the pauses grow, so a brief hold clears fast and a longer one is waited out
        self.assertLess(sum(self.sleeps), 3.0)
        self.assertTrue(self.source.exists() and not self.destination.exists())

    def test_a_violation_that_persists_is_explained_with_the_likely_cause(self):
        _, patched = self.flaky_move(10 ** 6)
        with patched, self.assertRaisesRegex(PermissionError, "bundle could not be moved to .*approved: another program.*virus scanner.*Nothing was changed"):
            common.move_path(self.source, self.destination)

    def test_other_errors_are_raised_at_once_not_retried(self):
        calls = []

        def move(source, destination):
            calls.append(source)
            raise FileNotFoundError("gone")
        with mock.patch.object(common.shutil, "move", move), self.assertRaises(FileNotFoundError):
            common.move_path(self.source, self.destination)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.sleeps, [])

    def test_a_move_that_half_happened_is_never_repeated_blindly(self):
        calls = []

        def move(source, destination):
            calls.append(source)
            Path(destination).mkdir()  # the destination appeared before the error, so the state is no longer the one the move started from
            raise PermissionError(5, "Access is denied")
        with mock.patch.object(common.shutil, "move", move), self.assertRaises(PermissionError):
            common.move_path(self.source, self.destination)
        self.assertEqual(len(calls), 1)

    def test_other_platforms_do_not_retry(self):
        calls, patched = self.flaky_move(10 ** 6)
        with patched, mock.patch.object(common, "RETRY_SHARING_VIOLATIONS", False), self.assertRaises(PermissionError) as raised:
            common.move_path(self.source, self.destination)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("another program", str(raised.exception))

    def test_replace_file_uses_the_same_retry_and_raises_a_persistent_violation_unchanged(self):
        target = self.root / "target.txt"
        temp = self.root / "temp.txt"
        temp.write_text("new", encoding="utf-8")
        real, calls = os.replace, []

        def replace(source, destination):
            calls.append(source)
            if len(calls) <= 2:
                raise PermissionError(5, "Access is denied")
            return real(source, destination)
        with mock.patch.object(common.os, "replace", replace):
            common.replace_file(temp, target)
        self.assertEqual((len(calls), target.read_text(encoding="utf-8")), (3, "new"))
        with mock.patch.object(common.os, "replace", mock.Mock(side_effect=PermissionError(5, "Access is denied"))), self.assertRaisesRegex(PermissionError, "Access is denied"):
            common.replace_file(temp, target)


class OneOwnerOfMovesTests(unittest.TestCase):
    """Moving or replacing a path is done in gamearts_common only. Blind spot: a move written another way (a subprocess `mv`, a copy then delete)."""

    def test_no_script_moves_or_replaces_a_path_except_through_the_common_owner(self):
        scripts = Path(common.__file__).parent
        for script in sorted(scripts.glob("*.py")):
            if script.name == "gamearts_common.py":
                continue
            tree = ast.parse(script.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                name, owner = node.func.attr, node.func.value
                direct_shutil = name == "move" and isinstance(owner, ast.Name) and owner.id == "shutil"
                direct_os = name in ("replace", "rename") and isinstance(owner, ast.Name) and owner.id == "os"
                path_method = name in ("replace", "rename") and len(node.args) == 1 and not node.keywords  # str.replace takes two arguments
                self.assertFalse(direct_shutil or direct_os or path_method,
                                 f"{script.name}:{node.lineno} moves a path directly; use common.move_path or common.replace_file (bounded retry for Windows sharing violations)")


class OneOwnerOfRightsTests(unittest.TestCase):
    """The rights an owner can state about supplied art are defined and checked in gamearts_common only. Blind spot: a value spelled another way
    (built from pieces, read from a file) or a new place that lists a different subset on purpose."""

    def test_every_value_the_owner_can_state_is_accepted(self):
        for rights in ("owned", "licensed", "user_supplied", "unknown"):
            common.require_rights(rights)
        self.assertEqual(common.RIGHTS, ("owned", "licensed", "user_supplied", "unknown"))

    def test_anything_else_is_refused_in_the_one_set_of_words(self):
        for rights in ("found on the internet", "", None, "Owned"):
            with self.assertRaisesRegex(ValueError, "^rights must be owned, licensed, user_supplied or unknown$"):
                common.require_rights(rights)

    def test_no_script_spells_the_rights_out_again(self):
        """Keyed on "licensed", which only the rights use ("user_supplied" is also the image generator's mode, a different setting)."""
        spelled = []
        for script in sorted(Path(common.__file__).parent.glob("*.py")):
            if script.name != "gamearts_common.py":
                spelled += [f"{script.name}:{node.lineno}" for node in ast.walk(ast.parse(script.read_text(encoding="utf-8")))
                            if isinstance(node, ast.Constant) and node.value == "licensed"]
        self.assertEqual(spelled, [], "a rights value is spelled out; use common.RIGHTS and common.require_rights")

    def test_the_manifest_schemas_list_the_same_values_in_the_same_order(self):
        found = []

        def walk(node):
            if isinstance(node, dict):
                if isinstance(node.get("enum"), list) and "licensed" in node["enum"]:
                    found.append(node["enum"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        for schema in sorted(common.SCHEMAS.glob("*.json")):
            walk(json.loads(schema.read_text(encoding="utf-8")))
        self.assertEqual(len(found), 3, "the assets manifest, the mockups manifest and the mockup metadata each list the rights values")
        for values in found:
            self.assertEqual(values, list(common.RIGHTS))


class DeprecatedPillowApiTests(unittest.TestCase):
    def test_no_script_calls_the_deprecated_pixel_iterator(self):
        for script in (Path(common.__file__).parent).glob("*.py"):
            text = script.read_text(encoding="utf-8")
            self.assertNotIn(".getdata(", text, f"{script.name} uses Image.getdata(), removed in a future Pillow; use the image-level operations in gamearts_common")


class SchemaTests(unittest.TestCase):
    def test_valid_settings_pass_and_missing_fields_name_the_path(self):
        common.validate_schema(settings(), "gamearts-project")
        broken = settings()
        del broken["animation"]
        with self.assertRaisesRegex(ValueError, "gamearts-project contract violation at \\(root\\): 'animation'"):
            common.validate_schema(broken, "gamearts-project")

    def test_owner_confirmed_requires_who_and_when(self):
        body = settings()
        del body["confirmed_by"]
        with self.assertRaisesRegex(ValueError, "confirmed_by"):
            common.validate_schema(body, "gamearts-project")

    def test_a_missing_schema_file_is_a_failure_not_a_skip(self):
        with self.assertRaisesRegex(ValueError, "Contract schema is missing"):
            common.validate_schema({}, "gamearts-does-not-exist")

    def test_a_missing_validator_package_is_reported_not_skipped(self):
        with mock.patch.dict(sys.modules, {"jsonschema": None}):
            with self.assertRaises(common.DependencyMissing):
                common.validate_schema({}, "gamearts-project")

    def test_sub_schema_path_validates_one_manifest_record(self):
        record = {"mockup_id": "a", "revision": "v001"}
        with self.assertRaises(ValueError):
            common.validate_schema(record, "gamearts-mockups-manifest", ("properties", "mockups", "items"))


class SettingsGateTests(unittest.TestCase):
    def test_formatting_and_unrelated_edits_do_not_change_the_material_hash(self):
        with tempfile.TemporaryDirectory() as root:
            write_settings(root)
            _, first, raw_first = common.load_project_settings(root)
            body = settings(confirmed_by="a different owner", project_id="test_project")
            (Path(root) / ".gamearts" / "project.json").write_text(json.dumps(body, indent=8))
            _, second, raw_second = common.load_project_settings(root)
            self.assertEqual(first, second)
            self.assertNotEqual(raw_first, raw_second)

    def test_material_edits_change_the_hash(self):
        with tempfile.TemporaryDirectory() as root:
            write_settings(root)
            _, first, _ = common.load_project_settings(root)
            write_settings(root, art_style={"id": "vector"})
            self.assertNotEqual(first, common.load_project_settings(root)[1])

    def test_unconfirmed_settings_are_refused_unless_asked_for(self):
        with tempfile.TemporaryDirectory() as root:
            write_settings(root, settings_status="inferred")
            with self.assertRaisesRegex(ValueError, "owner_confirmed"):
                common.load_project_settings(root)
            self.assertEqual(common.load_project_settings(root, require_confirmed=False)[0]["settings_status"], "inferred")

    def test_a_partial_or_garbage_project_file_is_refused_with_the_contract_violation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".gamearts" / "project.json"
            path.parent.mkdir()
            path.write_text('{"project_id": "partial", "settings_status": "owner_confirmed"}')
            for require in (True, False):
                with self.assertRaisesRegex(ValueError, "contract violation"):
                    common.load_project_settings(root, require_confirmed=require)
            path.write_text("[1, 2, 3]")
            with self.assertRaisesRegex(ValueError, "contract violation"):
                common.load_project_settings(root)

    def test_owner_confirmation_without_who_and_when_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            write_settings(root)
            path = Path(root) / ".gamearts" / "project.json"
            body = json.loads(path.read_text())
            del body["confirmed_by"]
            path.write_text(json.dumps(body))
            with self.assertRaisesRegex(ValueError, "confirmed_by"):
                common.load_project_settings(root)

    def test_missing_file_is_named(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "Missing .gamearts/project.json"):
                common.load_project_settings(root)


class KeyPolicyTests(unittest.TestCase):
    def test_exact_key_background_with_framed_art_passes(self):
        image = key_image((20, 10), {(2, 2): (10, 20, 30, 255)})
        report = common.key_policy_report(image, [(0, 0, 10, 10)])
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["outside_frames_non_key"], 0)

    def test_art_outside_every_frame_is_reported(self):
        image = key_image((20, 10), {(15, 5): (10, 20, 30, 255)})
        report = common.key_policy_report(image, [(0, 0, 10, 10)])
        self.assertEqual(report["outside_frames_non_key"], 1)
        self.assertTrue(any("not exact #FF00FF" in issue for issue in report["issues"]))

    def test_near_key_fringe_is_contamination_unless_allowed(self):
        image = key_image((10, 10), {(1, 1): (250, 6, 252, 255), (5, 5): (10, 20, 30, 255)})
        report = common.key_policy_report(image, [(0, 0, 10, 10)])
        self.assertEqual(report["near_key_pixels"], 1)
        self.assertTrue(any("near-#FF00FF" in issue for issue in report["issues"]))
        self.assertEqual(common.key_policy_report(image, [(0, 0, 10, 10)], allow_near_key=True)["issues"], [])

    def test_a_pixel_just_beyond_the_tolerance_is_art_not_contamination(self):
        far = (255 - common.NEAR_KEY_TOLERANCE - 1, 0, 255, 255)
        report = common.key_policy_report(key_image((4, 4), {(1, 1): far}), [(0, 0, 4, 4)])
        self.assertEqual(report["near_key_pixels"], 0)

    def test_full_bleed_ignores_frames_but_not_opacity_or_contamination(self):
        painted = Image.new("RGBA", (6, 6), (40, 90, 30, 255))
        self.assertEqual(common.key_policy_report(painted, [(0, 0, 1, 1)], full_bleed=True)["issues"], [])
        painted.putpixel((0, 0), (250, 4, 250, 255))
        self.assertTrue(common.key_policy_report(painted, full_bleed=True)["issues"])
        transparent = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        self.assertTrue(any("alpha" in i for i in common.key_policy_report(transparent, full_bleed=True)["issues"]))

    def test_load_rgba_refuses_transparency(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "t.png"
            Image.new("RGBA", (3, 3), (1, 2, 3, 0)).save(path)
            with self.assertRaisesRegex(ValueError, "fully opaque"):
                common.load_rgba(path)

    def test_ink_bbox_and_diff_mask(self):
        image = key_image((10, 10), {(3, 4): (1, 2, 3, 255), (6, 7): (1, 2, 3, 255)})
        self.assertEqual(common.ink_bbox(image), (3, 4, 7, 8))
        self.assertIsNone(common.ink_bbox(key_image((4, 4))))
        other = image.copy()
        other.putpixel((0, 0), (PINK[0] - 3, 0, 255, 255))
        self.assertEqual(common.mask_count(common.diff_mask(image, other)), 1)
        self.assertEqual(common.mask_count(common.diff_mask(image, other, tolerance=3)), 0)


if __name__ == "__main__":
    unittest.main()
