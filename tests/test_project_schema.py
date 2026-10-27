"""World-profile and camera settings validation for Game Arts projects."""
import json
import unittest
from pathlib import Path

import jsonschema

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "gamearts-project.schema.json"


class ProjectSchemaTests(unittest.TestCase):
    def project(self, grid, camera_profile, tile_size):
        return {
            "schema_version": "1.0",
            "project_id": "test.game",
            "art_style": {"id": "rendered_2d"},
            "world": {
                "grid": grid,
                "camera_profile": camera_profile,
                "logical_tile_m": [16, 16],
                "ground_tile_px": tile_size,
                "pixels_per_meter": 16,
                "construction_snap_m": 1,
                "object_camera": "Project-selected camera",
                "ground_camera": "Project-selected ground"
            },
            "directions": ["S"],
            "animation": {"preferred_method": "hybrid", "animated_attachment_anchors": True},
            "workflow": {"mockup_approval_required": True, "detail_decomposition_required": True},
            "export": {"background_hex": "#FF00FF", "background_alpha": 255,
                       "atlas_per_sheet": True, "no_zip": True}
        }

    def validate(self, body):
        jsonschema.validate(body, json.loads(SCHEMA.read_text(encoding="utf-8")))

    def test_supported_world_and_camera_presets_validate(self):
        cases = [
            ("orthogonal_square", "orthogonal_3_4_oblique", [256, 256]),
            ("orthogonal_square", "top_down", [256, 256]),
            ("orthogonal_square", "side", [256, 256]),
            ("isometric", "isometric_3_4", [256, 128]),
            ("custom", "custom", [256, 256])
        ]
        for grid, camera, tile in cases:
            with self.subTest(grid=grid, camera=camera):
                self.validate(self.project(grid, camera, tile))

    def test_image_generator_choices_validate(self):
        for choice in ({"tool": "built_in_image_gen"}, {"tool": "cli_image_gen", "notes": "high quality"},
                       {"tool": "connected_tool", "tool_name": "Studio Painter"}, {"tool": "user_supplied"}):
            with self.subTest(choice=choice):
                body = self.project("orthogonal_square", "side", [256, 256])
                body["image_generation"] = choice
                self.validate(body)

    def test_a_game_without_an_image_generator_choice_still_validates(self):
        self.validate(self.project("orthogonal_square", "side", [256, 256]))

    def test_bad_image_generator_choices_are_rejected(self):
        for choice in ({"tool": "magic_brush"}, {"tool": "connected_tool"}, {"tool": "connected_tool", "tool_name": ""},
                       {}, {"tool": "user_supplied", "model": "x"}):
            with self.subTest(choice=choice):
                body = self.project("orthogonal_square", "side", [256, 256])
                body["image_generation"] = choice
                with self.assertRaises(jsonschema.ValidationError):
                    self.validate(body)

    def test_unknown_world_profile_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.validate(self.project("diamond_only", "isometric_3_4", [256, 128]))

    def test_unknown_camera_profile_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.validate(self.project("orthogonal_square", "orthographic_magic", [256, 256]))


if __name__ == "__main__":
    unittest.main()
