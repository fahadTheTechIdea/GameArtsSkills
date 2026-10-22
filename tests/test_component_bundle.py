"""Regression tests for nested moving Game Arts components."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "build_component_bundle.py"
import sys
sys.path.insert(0, str(MODULE.parent))
spec = importlib.util.spec_from_file_location("build_component_bundle", MODULE)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
PINK=(255,0,255,255)


class ComponentTests(unittest.TestCase):
    def fixture(self, root):
        def frame(name, x, y):
            im=Image.new("RGBA",(20,20),PINK)
            im.putpixel((x,y),(30,100,70,255))
            im.save(root/name)
        for n in ("base_s.png","base_e.png","joint_s.png","joint_e.png","tip_s.png","tip_e.png"):
            frame(n,10,10)
        views_base={}
        views_joint={}
        views_tip={}
        for d,suffix in (("S","s"),("E","e")):
            views_base[d]={"frames":[{"file":f"base_{suffix}.png","pivot":[10,10],
                                     "anchors":{"root_mount":[12,10]}}]}
            views_joint[d]={"frames":[{"file":f"joint_{suffix}.png","pivot":[10,10],
                                      "anchors":{"tip_mount":[10,13]}}]}
            views_tip[d]={"frames":[{"file":f"tip_{suffix}.png","pivot":[10,10]}]}
        return {
            "name":"test_scene_machine_v001",
            "directions":["S","E"],"sample_times":[0,.5,1],
            "components":[
                {"id":"base","parent":None,"views":views_base},
                {"id":"joint","parent":"base","mount":"root_mount","views":views_joint,
                 "parent_action":"deploy",
                 "mount_tracks":{"deploy":{
                     "S":[{"time":0,"rotation_degrees":0},{"time":1,"rotation_degrees":90}],
                     "E":[{"time":0,"rotation_degrees":0},{"time":1,"rotation_degrees":-90}]} }},
                {"id":"tip","parent":"joint","mount":"tip_mount","views":views_tip,
                 "motion_tracks":{"default":{"*":[
                     {"time":0,"position":[0,0]},{"time":1,"position":[1,0]}]}}}
            ]
        }

    def test_sheet_build_and_nested_animated_transforms(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            cfg=self.fixture(root)
            out=engine.build(cfg,root/"generated"/cfg["name"],root)
            self.assertTrue((out/"test_scene_machine_v001.bundle.json").is_file())
            self.assertEqual(len(list(out.glob("*.png"))),6)
            self.assertEqual(len(list(out.glob("*.atlas.json"))),6)
            data=json.loads((out/"test_scene_machine_v001.bundle.json").read_text())
            self.assertEqual(data["component_order"],["base","joint","tip"])
            self.assertEqual(data["visual_review_protocol"], "review_packet_v1")
            self.assertEqual(data["validation"]["godot_runtime"],"not_tested")
            poses={(p["direction"],p["normalized_time"]):p for p in data["sampled_poses"]}
            def pos(p,component):
                m=p["nodes"][component]["world_matrix_2d"]
                return [round(m[0][2],4),round(m[1][2],4)]
            self.assertEqual(pos(poses["S",0],"joint"),[2,0])
            self.assertEqual(pos(poses["S",1],"joint"),[2,0])
            self.assertEqual(pos(poses["S",0],"tip"),[2,3])
            self.assertEqual(pos(poses["S",1],"tip"),[-1,1])
            self.assertEqual(pos(poses["E",1],"tip"),[5,-1])

    def test_missing_direction_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=self.fixture(root)
            cfg["components"][2]["views"].pop("E")
            with self.assertRaisesRegex(ValueError,"directional views"):
                engine.build(cfg,root/"result",root)
            self.assertFalse((root/"result").exists())

    def test_missing_mount_fails_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=self.fixture(root)
            cfg["components"][0]["views"]["S"]["frames"][0]["anchors"]={}
            with self.assertRaisesRegex(ValueError,"mount"):
                engine.build(cfg,root/"result",root)
            self.assertFalse((root/"result").exists())

    def test_cycle_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=self.fixture(root)
            cfg["components"][1]["parent"]="tip"
            cfg["components"][1]["mount"]="tip_mount"
            with self.assertRaisesRegex(ValueError,"cycle"):
                engine.validate_structure(cfg)

    def test_interpolated_rotation(self):
        tr=engine.animate([{"time":0,"rotation_degrees":0},
                           {"time":1,"rotation_degrees":90}],.5,"test")
        self.assertAlmostEqual(tr["rotation_degrees"],45)

if __name__=="__main__":
    unittest.main()
