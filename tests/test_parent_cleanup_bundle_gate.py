"""End-to-end parent cleanup approval checks on actual generated component bundles."""
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from build_component_bundle import build
from validate_component_bundle import validate as validate_bundle
from test_component_bundle import ComponentTests

PINK = (255, 0, 255, 255)


def prepare_cleanup_evidence(root, config):
    records = []
    config["detached_inventory"] = {"base": ["joint"], "joint": ["tip"]}
    for part_id, child_id in (("base", "joint"), ("joint", "tip")):
        for direction, suffix in (("S", "s"), ("E", "e")):
            workspace = root / "proof" / f"{part_id}_{direction}_0"
            workspace.mkdir(parents=True)
            parent_source = root / f"{part_id}_{suffix}.png"
            child_source = root / f"{child_id}_{suffix}.png"
            clean = Image.open(parent_source).convert("RGBA")
            composite = clean.copy()
            composite.putpixel((4, 4), (220, 65, 33, 255))
            composite.save(workspace / "source.png")
            shutil.copy2(parent_source, workspace / "master.png")
            shutil.copy2(parent_source, workspace / "plate.png")
            child = Image.open(child_source).convert("RGBA")
            child.save(workspace / "child.png")
            silhouette = Image.new("L", child.size, 0)
            for py in range(child.height):
                for px in range(child.width):
                    if child.getpixel((px, py)) != PINK:
                        silhouette.putpixel((px, py), 255)
            silhouette.save(workspace / "child_silhouette.png")
            mask = Image.new("L", clean.size, 0)
            mask.putpixel((4, 4), 255)
            mask.save(workspace / "remove.mask.png")
            job = {
                "schema_version": "1.0", "method": "pixel_exact",
                "source_composite": "source.png", "static_parent": "master.png",
                "clean_plate": "plate.png", "clean_plate_reference_id": "approved_test_plate",
                "clean_plate_review": "approved", "art_style_id": "illustrated",
                "detached_components": [{
                    "id": child_id, "kind": "animated", "sprite": "child.png",
                    "removal_mask": "remove.mask.png",
                    "sprite_silhouette_mask": "child_silhouette.png",
                    "silhouette_review": "approved",
                    "silhouette_reference_id": child_id + "_observed_source"
                }]
            }
            (workspace / "cleanup.json").write_text(json.dumps(job))
            records.append({
                "parent_component": part_id, "direction": direction,
                "frame_index": 0, "manifest": str((workspace / "cleanup.json").relative_to(root))
            })
    config["parent_cleanup_evidence"] = records


class ParentCleanupBundleGateTests(unittest.TestCase):
    def setup_case(self, folder):
        root = Path(folder)
        config = ComponentTests().fixture(root)
        return root, config, root / "generated" / config["name"]

    def test_bundle_without_cleanup_cannot_pass_approval_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg, out = self.setup_case(tmp)
            build(cfg, out, root)
            problems = validate_bundle(out, approval_gate=True)
            self.assertTrue(any("missing mandatory parent-cleanup evidence" in p for p in problems))
            data = json.loads(next(out.glob("*.bundle.json")).read_text())
            self.assertEqual(data["validation"]["parent_cleanup"], "pending")

    def test_bundle_packages_approved_evidence_and_passes_strict_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg, out = self.setup_case(tmp)
            prepare_cleanup_evidence(root, cfg)
            build(cfg, out, root)
            self.assertEqual(validate_bundle(out, approval_gate=True), [])
            self.assertEqual(len(list(out.glob("parent_cleanup/*/cleanup.json"))), 4)
            meta = json.loads(next(out.glob("*.bundle.json")).read_text())
            self.assertEqual(meta["validation"]["parent_cleanup"], "passed_declared_pixel_check")
            self.assertEqual(len(meta["parent_cleanup_evidence"]), 4)
            # No evidence is allowed to escape the self-contained candidate folder.
            for rec in meta["parent_cleanup_evidence"]:
                self.assertTrue((out / rec["manifest"]).is_file())

    def test_missing_direction_cleanup_blocks_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg, out = self.setup_case(tmp)
            prepare_cleanup_evidence(root, cfg)
            cfg["parent_cleanup_evidence"].pop()
            with self.assertRaisesRegex(ValueError, "missing mandatory parent-cleanup"):
                build(cfg, out, root)
            self.assertFalse(out.exists())

    def test_parent_still_contains_component_blocks_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg, out = self.setup_case(tmp)
            prepare_cleanup_evidence(root, cfg)
            workspace = root / "proof" / "base_S_0"
            Image.open(workspace / "source.png").save(workspace / "master.png")
            with self.assertRaisesRegex(ValueError, "clean plate"):
                build(cfg, out, root)
            self.assertFalse(out.exists())

    def test_evidence_must_be_bound_to_real_atlas_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg, out = self.setup_case(tmp)
            prepare_cleanup_evidence(root, cfg)
            build(cfg, out, root)
            clean_path = out / "parent_cleanup" / "base_S_0" / "static_parent.png"
            edited = Image.open(clean_path)
            edited.putpixel((18, 18), (111, 222, 55, 255))
            edited.save(clean_path)
            problems = validate_bundle(out, approval_gate=True)
            self.assertTrue(any("does not match actual atlas source frame" in p or
                                "outside removal masks" in p for p in problems))

    def test_detached_inventory_must_include_every_named_prop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg, out = self.setup_case(tmp)
            prepare_cleanup_evidence(root, cfg)
            cfg["detached_inventory"]["base"].append("extra_workbench")
            with self.assertRaisesRegex(ValueError, "absent from cleanup proof"):
                build(cfg, out, root)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
