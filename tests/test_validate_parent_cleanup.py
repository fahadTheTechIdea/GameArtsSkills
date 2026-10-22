"""Tests for mandatory parent-cleanup gate across ALL Game Arts media."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

script = Path(__file__).resolve().parents[1] / "scripts" / "validate_parent_cleanup.py"
spec = importlib.util.spec_from_file_location("validate_parent_cleanup", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
PINK = (255, 0, 255, 255)


def example(folder, style="illustrated"):
    folder = Path(folder)
    base = Image.new("RGBA", (12, 12), (218, 205, 175, 255))
    for x in range(12):
        base.putpixel((x, 0), (60, 42, 32, 255))
    source = base.copy()
    components = []
    for identifier, rectangle, color in (
        ("workbench", (3, 3, 5, 5), (133, 75, 23, 255)),
        ("screw", (7, 6, 9, 8), (150, 159, 169, 255))
    ):
        mask = Image.new("L", base.size, 0)
        for x in range(rectangle[0], rectangle[2]):
            for y in range(rectangle[1], rectangle[3]):
                source.putpixel((x, y), color)
                mask.putpixel((x, y), 255)
        mask.save(folder / (identifier + ".mask.png"))
        isolated = Image.new("RGBA", (8, 8), PINK)
        isolated.putpixel((3, 3), color)
        isolated.save(folder / (identifier + ".png"))
        components.append({"id": identifier, "kind": "removable",
                           "sprite": identifier + ".png",
                           "removal_mask": identifier + ".mask.png"})
    source.save(folder / "source.png")
    base.save(folder / "master.png")
    base.save(folder / "plate.png")
    job = {"schema_version": "1.0", "method": "pixel_exact",
           "source_composite": "source.png", "static_parent": "master.png",
           "clean_plate": "plate.png", "clean_plate_review": "approved",
           "clean_plate_reference_id": "reviewed_empty_workshop_v001",
           "art_style_id": style, "detached_components": components}
    path = folder / "cleanup.json"
    path.write_text(json.dumps(job))
    return path


class ParentCleanupTests(unittest.TestCase):
    def test_separation_works_for_every_style(self):
        for style in ("pixel_art", "illustrated", "hand_painted",
                      "vector", "rendered_2d", "custom"):
            with self.subTest(style=style), tempfile.TemporaryDirectory() as folder:
                result = mod.validate(example(folder, style))
                self.assertEqual(result["technical_status"], "passed")
                self.assertEqual(result["visual_inventory_completeness"], "not_verified")
                self.assertEqual(result["parent_pixels_unrestored_inside_masks"], 0)
                self.assertEqual(len(result["components"]), 2)

    def test_baked_in_workbench_is_rejected_even_if_exported_separately(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            src = Image.open(Path(folder) / "source.png")
            base = Image.open(Path(folder) / "master.png")
            for x in range(3, 5):
                for y in range(3, 5):
                    base.putpixel((x, y), src.getpixel((x, y)))
            base.save(Path(folder) / "master.png")
            with self.assertRaisesRegex(ValueError, "clean plate inside masks"):
                mod.validate(path)

    def test_static_pixels_outside_detachment_masks_must_stay_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            base = Image.open(Path(folder) / "master.png")
            base.putpixel((6, 9), (1, 2, 3, 255))
            base.save(Path(folder) / "master.png")
            with self.assertRaisesRegex(ValueError, "outside removal masks"):
                mod.validate(path)

    def test_no_actual_removal_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            Image.open(Path(folder) / "source.png").save(Path(folder) / "master.png")
            with self.assertRaisesRegex(ValueError, "no detached component"):
                mod.validate(path)

    def test_missing_detached_sprite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            (Path(folder) / "workbench.png").unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                mod.validate(path)

    def test_opaque_pink_only_is_not_an_exported_component(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            Image.new("RGBA", (8, 8), PINK).save(Path(folder) / "workbench.png")
            with self.assertRaisesRegex(ValueError, "no non-pink artwork"):
                mod.validate(path)

    def test_overlapping_masks_need_proper_layer_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            mask = Image.open(Path(folder) / "screw.mask.png")
            mask.putpixel((3, 3), 255)
            mask.save(Path(folder) / "screw.mask.png")
            with self.assertRaisesRegex(ValueError, "overlapping separation masks"):
                mod.validate(path)

    def test_antialiased_mask_must_be_rasterized_binary_for_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            mask = Image.open(Path(folder) / "workbench.mask.png")
            mask.putpixel((3, 3), 128)
            mask.save(Path(folder) / "workbench.mask.png")
            with self.assertRaisesRegex(ValueError, "binary black/white"):
                mod.validate(path)

    def test_mask_dimensions_must_match_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            Image.new("L", (5, 5), 0).save(Path(folder) / "workbench.mask.png")
            with self.assertRaisesRegex(ValueError, "dimensions differ"):
                mod.validate(path)

    def test_clean_plate_requires_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            data = json.loads(path.read_text())
            data["clean_plate_review"] = "pending"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "approved status"):
                mod.validate(path)

    def test_clean_plate_is_separate_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            data = json.loads(path.read_text())
            data["clean_plate"] = "master.png"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "distinct source"):
                mod.validate(path)

    def test_no_coverage_without_declared_components(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            data = json.loads(path.read_text())
            data["detached_components"] = []
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "At least one"):
                mod.validate(path)

    def test_transparent_master_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            base = Image.open(Path(folder) / "master.png")
            base.putpixel((6, 6), (2, 2, 2, 0))
            base.save(Path(folder) / "master.png")
            with self.assertRaisesRegex(ValueError, "fully opaque"):
                mod.validate(path)

    def test_unverified_workflows_cannot_get_technical_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            path = example(folder)
            data = json.loads(path.read_text())
            data["method"] = "style_guess"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "pixel_exact"):
                mod.validate(path)


if __name__ == "__main__":
    unittest.main()
