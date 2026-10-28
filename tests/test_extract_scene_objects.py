"""The extraction step of the mockup analyzer: every object of a scene cut out of its mockup as the blueprint says, with the account checked."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from PIL import Image  # noqa: E402

import extract_scene_objects as extractor  # noqa: E402
import gamearts_common as common  # noqa: E402

SCRIPT = ROOT / "scripts" / "extract_scene_objects.py"
CLASSES = ["character", "vehicle", "building", "plant", "sign", "street_furniture", "lighting", "barrier", "opening", "prop", "structure_part", "street", "parking", "other"]
# id, class, region [x, y, w, h], colour painted in the synthetic mockup
OBJECTS = [("hall", "building", [4, 4, 60, 40], (170, 60, 50)), ("door", "opening", [24, 20, 12, 24], (30, 40, 110)), ("oak", "plant", [70, 10, 20, 30], (30, 110, 30)),
           ("car", "vehicle", [10, 56, 30, 14], (200, 200, 205)), ("walker", "character", [28, 22, 6, 16], (240, 200, 160))]


def mockup():
    image = Image.new("RGB", (100, 80), (120, 120, 125))
    for _, _, (x, y, w, h), colour in OBJECTS:
        image.paste(colour, (x, y, x + w, y + h))
    return image


def blueprint(objects=OBJECTS, status="approved", sha=None, drop=()):
    members = [o for o in objects if o[0] not in drop]
    by_class = {}
    for object_id, cls, _, _ in members:
        by_class.setdefault(cls, []).append(object_id)
    elements = [{"element_id": "scene", "scope": "scene", "evidence_status": "observed", "observed_details": {}, "motion_candidates": [], "production_strategy": "separate everything",
                 "separation_inventory": [{"component_id": i, "ownership": ["independent_prop"], "object_class": c, "source_evidence": "seen"} for i, c, _, _ in members]}]
    for object_id, cls, region, _ in members:
        element = {"element_id": object_id, "scope": "asset", "parent_id": "scene", "source_region_px": region, "evidence_status": "observed", "observed_details": {}, "motion_candidates": [],
                   "production_strategy": "separate sprite"}
        if sha:
            element["approved_source_sha256"] = sha
        elements.append(element)
    sweep = [{"object_class": c, "status": "present", "component_ids": by_class[c], "evidence": "found"} if c in by_class else {"object_class": c, "status": "absent", "evidence": "looked, none"}
             for c in CLASSES]
    return {"schema_version": "1.0", "mockup_id": "street", "mockup_revision": "v001", "approval_status": status, "scope": "scene", "elements": elements, "object_sweep": sweep,
            "coverage_audit": {"status": "pass", "unassigned_regions": []}}


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        mockup().save(self.root / "mock.png")
        self.sha = hashlib.sha256((self.root / "mock.png").read_bytes()).hexdigest()
        self.out = self.root / "out"

    def write(self, data):
        path = self.root / "bp.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def extract(self, data=None, **kw):
        return extractor.extract(self.write(data or blueprint(sha=self.sha)), self.root / "mock.png", kw.pop("out", self.out), **kw)

    def crop(self, relative):
        with Image.open(self.out / relative) as opened:
            opened.load()
            return opened.copy()


class ExtractTests(Case):
    def test_every_object_is_cut_from_the_mockup_into_its_class_folder_exactly(self):
        manifest = self.extract()
        source = mockup()
        for object_id, cls, (x, y, w, h), _ in OBJECTS:
            crop = self.crop(f"{cls}/{object_id}.png")
            self.assertEqual(list(crop.getdata()), list(source.crop((x, y, x + w, y + h)).getdata()), object_id)
        self.assertEqual(manifest["per_class"], {"building": 1, "opening": 1, "plant": 1, "vehicle": 1, "character": 1})

    def test_a_building_is_an_object_and_so_are_its_door_and_the_person_in_front_of_it(self):
        manifest = self.extract()
        by_id = {o["id"]: o for o in manifest["objects"]}
        self.assertEqual(by_id["hall"]["object_class"], "building")
        self.assertEqual(by_id["door"]["object_class"], "opening")
        self.assertEqual(by_id["walker"]["object_class"], "character")
        self.assertEqual(by_id["hall"]["crop"], "building/hall.png")

    def test_the_manifest_records_the_mockup_hash_the_regions_the_crop_hashes_and_what_was_not_assessed(self):
        manifest = self.extract()
        self.assertEqual((manifest["mockup_sha256"], manifest["mockup_size"], manifest["provisional"]), (self.sha, [100, 80], False))
        hall = next(o for o in manifest["objects"] if o["id"] == "hall")
        self.assertEqual(hall["region_px"], [4, 4, 60, 40])
        self.assertEqual(hall["crop_sha256"], common.sha256_file(self.out / "building" / "hall.png"))
        self.assertEqual(manifest["absent_classes"], [c for c in CLASSES if c not in ("character", "vehicle", "building", "plant", "opening")])
        self.assertTrue(any("clean plate" in line for line in manifest["not_assessed"]))
        self.assertEqual(common.read_json(self.out / "extraction.json")["mockup_id"], "street")

    def test_the_overview_and_the_contact_sheet_are_written(self):
        self.extract()
        overview = self.crop("overview.png")
        self.assertEqual(overview.size, (100, 80))
        self.assertNotEqual(overview.getpixel((4, 4)), mockup().getpixel((4, 4)))     # the region's outline is drawn over the mockup
        self.assertTrue((self.out / "contact_sheet.png").is_file())

    def test_the_share_of_the_mockup_the_objects_cover_is_reported(self):
        manifest = self.extract()
        covered = {(x, y) for _, _, (rx, ry, w, h), _ in OBJECTS for x in range(rx, rx + w) for y in range(ry, ry + h)}
        self.assertEqual(manifest["mockup_covered_by_objects"], round(len(covered) / 8000, 4))


class MaskTests(Case):
    def with_mask(self, mask_image, mask_ref="masks/oak.png"):
        data = blueprint(sha=self.sha)
        next(c for c in data["elements"][0]["separation_inventory"] if c["component_id"] == "oak")["removal_mask_ref"] = mask_ref
        if mask_image is not None:
            (self.root / "masks").mkdir(exist_ok=True)
            mask_image.save(self.root / mask_ref)
        return data

    def test_an_object_with_a_mask_also_gets_a_cut_out_sprite_whose_alpha_is_the_mask(self):
        mask = Image.new("L", (20, 30), 0)
        mask.paste(255, (5, 5, 15, 25))
        manifest = self.extract(self.with_mask(mask))
        entry = next(o for o in manifest["objects"] if o["id"] == "oak")
        sprite = self.crop(entry["sprite"])
        self.assertEqual(sprite.size, (20, 30))
        self.assertEqual((sprite.getpixel((10, 10)), sprite.getpixel((1, 1))), ((30, 110, 30, 255), (30, 110, 30, 0)))     # opaque inside the mask, transparent outside
        self.assertEqual(entry["sprite_sha256"], common.sha256_file(self.out / entry["sprite"]))
        self.assertTrue((self.out / "plant" / "oak.png").is_file())                                                         # the plain crop is still made
        self.assertNotIn("sprite", next(o for o in manifest["objects"] if o["id"] == "hall"))                              # an object with no mask has none

    def test_a_mask_of_another_size_or_one_that_is_not_there_is_refused_before_anything_is_written(self):
        with self.assertRaisesRegex(ValueError, "the mask is 10 x 10 and the region is 20 x 30"):
            self.extract(self.with_mask(Image.new("L", (10, 10), 255)))
        self.assertFalse(self.out.exists())                                          # nothing was written, not even the crops made before the bad mask
        (self.root / "masks" / "oak.png").unlink()
        with self.assertRaisesRegex(ValueError, "is not beside the blueprint"):
            self.extract(self.with_mask(None), out=self.root / "second")
        self.assertFalse((self.root / "second").exists())


class DuplicateTests(Case):
    def test_a_person_in_front_of_a_door_is_not_a_duplicate_but_two_near_identical_regions_are(self):
        manifest = self.extract()
        self.assertEqual(manifest["possible_duplicates"], [])                         # the walker stands inside the door, which stands inside the hall
        twin = OBJECTS + [("oak_again", "plant", [71, 10, 20, 30], (30, 110, 30))]
        again = self.extract(blueprint(twin, sha=self.sha), out=self.root / "second")
        self.assertEqual([d["objects"] for d in again["possible_duplicates"]], [["oak", "oak_again"]])
        self.assertGreaterEqual(again["possible_duplicates"][0]["overlap"], extractor.DUPLICATE_OVERLAP)

    def test_the_overlap_is_intersection_over_union(self):
        self.assertEqual(extractor.overlap([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(extractor.overlap([0, 0, 10, 10], [10, 0, 10, 10]), 0.0)
        self.assertAlmostEqual(extractor.overlap([0, 0, 10, 10], [5, 0, 10, 10]), 50 / 150)


class RefusalTests(Case):
    def test_an_unapproved_blueprint_is_extracted_only_when_asked_and_is_then_labelled_provisional(self):
        pending = blueprint(status="pending_approval")
        with self.assertRaisesRegex(ValueError, "extract with --provisional"):
            self.extract(pending)
        self.assertFalse(self.out.exists())
        manifest = self.extract(pending, provisional=True)
        self.assertTrue(manifest["provisional"])

    def test_an_approved_blueprint_must_name_the_source_by_hash_and_the_mockup_must_match(self):
        with self.assertRaisesRegex(ValueError, "no element names the approved source's sha256"):
            self.extract(blueprint(sha=None))
        with self.assertRaisesRegex(ValueError, "not the approved source"):
            self.extract(blueprint(sha="0" * 64))
        with self.assertRaisesRegex(ValueError, "not the source the blueprint names"):
            self.extract(blueprint(status="pending_approval", sha="0" * 64), provisional=True)

    def test_a_missing_or_inconsistent_sweep_is_refused(self):
        data = blueprint(sha=self.sha)
        del data["object_sweep"]
        with self.assertRaisesRegex(ValueError, "no object_sweep"):
            self.extract(data)
        data = blueprint(sha=self.sha)
        data["object_sweep"] = data["object_sweep"][:-1]
        with self.assertRaisesRegex(ValueError, "sweep is inconsistent"):
            self.extract(data)

    def test_a_component_with_no_region_no_class_or_a_repeated_id_cannot_be_extracted(self):
        data = blueprint(sha=self.sha)
        data["elements"] = [e for e in data["elements"] if e["element_id"] != "oak"]
        with self.assertRaisesRegex(ValueError, "oak has no element with that id giving its source_region_px"):
            self.extract(data)
        data = blueprint(sha=self.sha)
        for component in data["elements"][0]["separation_inventory"]:
            if component["component_id"] == "car":
                component.pop("object_class")
        data["object_sweep"] = blueprint(sha=self.sha, drop=("car",))["object_sweep"]
        with self.assertRaises(ValueError):                                             # the sweep no longer lists it, or the class is missing: either way it is refused
            self.extract(data)
        data = blueprint(sha=self.sha)
        data["elements"][0]["separation_inventory"].append(dict(data["elements"][0]["separation_inventory"][0]))
        with self.assertRaises(ValueError):
            self.extract(data)

    def test_a_region_outside_the_mockup_is_refused_before_anything_is_written(self):
        data = blueprint(sha=self.sha)
        next(e for e in data["elements"] if e["element_id"] == "car")["source_region_px"] = [90, 70, 30, 14]
        with self.assertRaisesRegex(ValueError, "car: the region .* lies outside the 100 x 80 mockup"):
            self.extract(data)
        self.assertFalse(self.out.exists())

    def test_a_folder_with_something_in_it_is_never_written_into(self):
        self.out.mkdir()
        (self.out / "old.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "is not empty"):
            self.extract()
        self.assertEqual([p.name for p in self.out.iterdir()], ["old.txt"])

    def test_an_empty_inventory_is_refused(self):
        data = blueprint(sha=self.sha)
        data["elements"][0]["separation_inventory"] = []
        data["object_sweep"] = [{"object_class": c, "status": "absent", "evidence": "none"} for c in CLASSES]
        with self.assertRaisesRegex(ValueError, "nothing to extract"):
            self.extract(data)


class CommandTests(Case):
    def test_the_command_extracts_and_says_what_it_did_not_assess(self):
        path = self.write(blueprint(sha=self.sha))
        done = subprocess.run([sys.executable, str(SCRIPT), "extract", "--blueprint", str(path), "--mockup", str(self.root / "mock.png"), "--output-dir", str(self.out)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(report["per_class"]["building"], 1)
        self.assertTrue(any("reference crop" in line for line in report["not_assessed"]))

    def test_the_command_refuses_with_the_reason_in_words(self):
        path = self.write(blueprint(status="pending_approval"))
        done = subprocess.run([sys.executable, str(SCRIPT), "extract", "--blueprint", str(path), "--mockup", str(self.root / "mock.png"), "--output-dir", str(self.out)], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--provisional", done.stderr)


if __name__ == "__main__":
    unittest.main()
