"""Terrain from a scene (plan P16): labels from a picture, conservative cleanup with a report, and the dual-grid overlay of each terrain."""
import unittest

import gamearts_testkit as kit  # noqa: F401  (puts scripts/ on sys.path)
from PIL import Image

import gamearts_terrain as terrain  # noqa: E402

TERRAINS = [{"id": "water", "colours": ["#3C6EBE"]}, {"id": "sand", "colours": ["#DECD96"]}, {"id": "grass", "colours": ["#60AA50"]}]
COLOUR = {0: (60, 110, 190), 1: (222, 205, 150), 2: (96, 170, 80)}


def picture(rows, cell=4, objects=()):
    """Paint rows of terrain indexes as cells of their colour; `objects` are (x, y, colour) pixels laid over the top."""
    image = Image.new("RGB", (len(rows[0]) * cell, len(rows) * cell))
    for y, row in enumerate(rows):
        for x, label in enumerate(row):
            image.paste(COLOUR[label], (x * cell, y * cell, (x + 1) * cell, (y + 1) * cell))
    for x, y, colour in objects:
        image.putpixel((x, y), colour)
    return image


class ReadTests(unittest.TestCase):
    def test_every_cell_gets_the_terrain_whose_colour_is_nearest(self):
        rows = [[0, 0, 1, 1], [0, 2, 2, 1], [2, 2, 2, 1]]
        read = terrain.read_labels(picture(rows), TERRAINS, (4, 4))
        self.assertEqual(read["labels"], rows)
        self.assertEqual(read["unclassified"], [])

    def test_a_few_object_pixels_over_a_cell_do_not_change_its_terrain(self):
        rows = [[2, 2], [2, 2]]
        dark = [(x, y, (88, 86, 90)) for x in range(4, 6) for y in range(0, 2)]  # four rock pixels in one cell of sixteen
        self.assertEqual(terrain.read_labels(picture(rows, objects=dark), TERRAINS, (4, 4))["labels"], rows)

    def test_a_cell_far_from_every_terrain_is_named_unclassified_not_forced_silently(self):
        image = picture([[0, 0], [0, 0]])
        image.paste((250, 20, 250), (4, 0, 8, 4))
        read = terrain.read_labels(image, TERRAINS, (4, 4))
        self.assertEqual(read["unclassified"], [(1, 0)])
        self.assertIn(read["labels"][0][1], (0, 1, 2))  # it still has its nearest terrain, and the gap is reported
        self.assertGreater(read["distance"][0][1], terrain.UNKNOWN_DISTANCE)

    def test_a_picture_that_is_not_a_whole_number_of_cells_is_refused(self):
        with self.assertRaisesRegex(ValueError, "whole number of cells"):
            terrain.read_labels(Image.new("RGB", (10, 8)), TERRAINS, (4, 4))
        with self.assertRaisesRegex(ValueError, "whole number of cells"):
            terrain.read_labels(Image.new("RGB", (8, 8)), TERRAINS, (0, 4))

    def test_a_colour_must_be_written_in_full(self):
        for bad in ("3C6EBE", "#3C6E", "#GG0000", None):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "#RRGGBB"):
                terrain.parse_colour(bad)


class SampleColourTests(unittest.TestCase):
    def test_a_terrain_with_several_sample_colours_takes_a_cell_near_any_of_them(self):
        grass = {"id": "grass", "colours": ["#60AA50", "#2E5A24"]}  # light and shaded grass
        sand = {"id": "sand", "colours": ["#DECD96"]}
        image = Image.new("RGB", (8, 4), (46, 90, 36))  # a cell of shaded grass
        image.paste((222, 205, 150), (4, 0, 8, 4))
        read = terrain.read_labels(image, [sand, grass], (4, 4))
        self.assertEqual(read["labels"], [[1, 0]])  # shaded grass is grass, not "nearest to sand's one colour"
        self.assertEqual(read["unclassified"], [])

    def test_a_terrain_with_no_sample_colour_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, "lava needs at least one sample colour"):
            terrain.class_colours([{"id": "lava", "colours": []}])


class OccluderTests(unittest.TestCase):
    def test_a_cell_whose_nearest_class_is_an_occluder_gets_an_index_after_the_ground_terrains(self):
        image = picture([[2, 2, 2]])
        image.paste((30, 80, 40), (4, 0, 8, 4))  # a tree over the middle cell
        read = terrain.read_labels(image, TERRAINS, (4, 4), occluders=[{"id": "tree", "colours": ["#1E5028"]}])
        self.assertEqual(read["labels"], [[2, 3, 2]])

    def test_the_cells_an_object_hides_take_the_nearest_ground_and_are_reported_as_inferred(self):
        filled, occluded = terrain.fill_occluded([[0, 0, 3, 3], [0, 0, 3, 1], [3, 3, 3, 1]], 3)
        self.assertEqual(filled, [[0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 1, 1]])
        self.assertEqual(occluded, [(2, 0), (3, 0), (2, 1), (0, 2), (1, 2), (2, 2)])

    def test_ground_cells_are_never_changed_and_a_tie_goes_to_the_first_in_reading_order(self):
        labels = [[0, 3, 1]]
        filled, occluded = terrain.fill_occluded(labels, 3)
        self.assertEqual((filled, occluded), ([[0, 0, 1]], [(1, 0)]))  # the left cell reaches it first
        self.assertEqual(labels, [[0, 3, 1]])

    def test_a_scene_with_no_visible_ground_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no ground to read a terrain from"):
            terrain.fill_occluded([[3, 3]], 3)


class MaskTests(unittest.TestCase):
    def mask(self):
        image = Image.new("L", (12, 4), 0)
        image.paste(255, (0, 0, 4, 4))  # the first cell, wholly covered
        image.paste(255, (4, 0, 8, 2))  # the second cell, exactly half covered
        return image

    def test_a_cell_the_mask_covers_enough_is_hidden_whatever_its_colour(self):
        self.assertEqual(terrain.cells_from_mask(self.mask(), (4, 4)), {(0, 0), (1, 0)})  # half covered counts at the default of one half
        self.assertEqual(terrain.cells_from_mask(self.mask(), (4, 4), threshold=0.75), {(0, 0)})
        self.assertEqual(terrain.cells_from_mask(self.mask(), (4, 4), threshold=0.1), {(0, 0), (1, 0)})
        self.assertEqual(terrain.cells_from_mask(Image.new("L", (8, 4), 0), (4, 4)), set())

    def test_only_white_counts_and_a_picture_of_any_mode_is_read(self):
        grey = Image.new("RGB", (4, 4), (127, 127, 127))
        self.assertEqual(terrain.cells_from_mask(grey, (4, 4)), set())  # grey below 128 is not an object
        white = Image.new("RGB", (4, 4), (255, 255, 255))
        self.assertEqual(terrain.cells_from_mask(white, (4, 4)), {(0, 0)})

    def test_a_mask_that_is_not_whole_cells_or_a_threshold_out_of_range_is_refused(self):
        with self.assertRaisesRegex(ValueError, "the mask is 10 x 8"):
            terrain.cells_from_mask(Image.new("L", (10, 8)), (4, 4))
        for bad in (0, -0.5, 1.5):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "above 0 and at most 1"):
                terrain.cells_from_mask(Image.new("L", (8, 8)), (4, 4), threshold=bad)


class CleanupTests(unittest.TestCase):
    def test_a_region_smaller_than_the_minimum_takes_its_most_common_neighbour_and_the_change_is_reported(self):
        labels = [[2, 2, 2], [2, 0, 2], [2, 2, 2]]
        out, changes = terrain.area_open(labels, 2)
        self.assertEqual(out, [[2, 2, 2]] * 3)
        self.assertEqual(changes, [{"cells": [(1, 1)], "from": 0, "to": 2}])

    def test_a_minimum_of_one_changes_nothing_so_thin_real_features_survive(self):
        labels = [[2, 1, 2], [2, 1, 2], [2, 0, 2]]
        out, changes = terrain.area_open(labels, 1)
        self.assertEqual((out, changes), (labels, []))

    def test_a_region_with_no_neighbour_stays_and_a_tie_is_broken_the_same_way_every_time(self):
        self.assertEqual(terrain.area_open([[1, 1], [1, 1]], 10)[0], [[1, 1], [1, 1]])
        tie = [[0, 1, 2]]
        first = terrain.area_open(tie, 2)
        self.assertEqual(first, terrain.area_open(tie, 2))
        # label 0 has one neighbour (1) and takes it; label 1 sits between 0 and 2 with one cell each, so the tie goes to the lower label; label 2 takes 1
        self.assertEqual(first[0], [[1, 0, 1]])

    def test_the_input_is_not_changed(self):
        labels = [[2, 2], [2, 0]]
        terrain.area_open(labels, 2)
        self.assertEqual(labels, [[2, 2], [2, 0]])


class RowsTests(unittest.TestCase):
    def test_rows_round_trip_through_the_terrains_symbols(self):
        labels = [[0, 1, 2], [2, 2, 0]]
        rows = terrain.encode_rows(labels, ["~", ".", "g"])
        self.assertEqual(rows, ["~.g", "gg~"])
        self.assertEqual(terrain.decode_rows(rows, ["~", ".", "g"]), labels)

    def test_an_unknown_symbol_and_a_ragged_row_are_named(self):
        with self.assertRaisesRegex(ValueError, r"cell \(1, 0\) is 'x'"):
            terrain.decode_rows(["~x"], ["~", "."])
        with self.assertRaisesRegex(ValueError, "row 1 has 1 cells"):
            terrain.decode_rows(["~~", "~"], ["~", "."])


class OverlayTests(unittest.TestCase):
    def test_an_overlay_covers_every_cell_of_at_least_its_priority(self):
        labels = [[0, 1], [2, 1]]
        priorities = [0, 1, 2]  # water lowest, then sand, then grass
        self.assertEqual(terrain.covered(labels, priorities, 0), [[True, True], [True, True]])  # the base covers everything
        self.assertEqual(terrain.covered(labels, priorities, 1), [[False, True], [True, True]])
        self.assertEqual(terrain.covered(labels, priorities, 2), [[False, False], [True, False]])

    def test_the_dual_grid_has_a_tile_where_every_four_cells_meet_and_one_more_row_and_column(self):
        corners = terrain.overlay_corners([[True, False], [False, False]])
        self.assertEqual(len(corners), 3 * 3)
        self.assertEqual(corners[(1, 1)], (True, False, False, False))  # top-left cell covered, the other three not
        self.assertEqual(terrain.corner_number(corners[(1, 1)]), 1)

    def test_a_cell_outside_the_map_counts_as_the_nearest_cell_inside(self):
        corners = terrain.overlay_corners([[True, True], [True, True]])
        self.assertTrue(all(all(value) for value in corners.values()))  # the overlay runs off the edge: no border tile appears
        corner = terrain.overlay_corners([[True, False], [False, False]])
        self.assertEqual(corner[(0, 0)], (True, True, True, True))  # beyond the top-left edge the overlay continues as the cell it touches
        self.assertEqual(corner[(2, 2)], (False, False, False, False))
        none = terrain.overlay_corners([[False]])
        self.assertTrue(all(not any(value) for value in none.values()))

    def test_the_corner_number_is_zero_for_nothing_and_fifteen_for_the_whole_interior(self):
        self.assertEqual(terrain.corner_number((False, False, False, False)), 0)
        self.assertEqual(terrain.corner_number((True, True, True, True)), 15)
        self.assertEqual([terrain.corner_number(c) for c in ((False, True, False, False), (False, False, True, False), (False, False, False, True))], [2, 4, 8])


if __name__ == "__main__":
    unittest.main()
