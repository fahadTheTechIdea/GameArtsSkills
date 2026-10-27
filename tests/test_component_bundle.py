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
            self.assertEqual(data["visual_review_protocol"], "review_packet")
            self.assertEqual(data["validation"]["parent_cleanup"], "pending")  # detachable parts need proof before approval
            self.assertEqual(data["validation"]["engine_validation"],"not_tested")
            self.assertNotIn("godot_runtime", data["validation"])
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

    def test_full_turn_is_a_full_turn_by_default(self):
        full=[{"time":0,"rotation_degrees":0},{"time":1,"rotation_degrees":360}]
        self.assertAlmostEqual(engine.animate(full,.5,"spin")["rotation_degrees"],180)
        wrap=[{"time":0,"rotation_degrees":0},{"time":1,"rotation_degrees":350}]
        self.assertAlmostEqual(engine.animate(wrap,.5,"spin")["rotation_degrees"],175)
        self.assertAlmostEqual(engine.animate(wrap,.5,"spin","shortest")["rotation_degrees"],-5)

    def test_track_that_is_never_selected_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=self.fixture(root)
            cfg["components"][1]["mount_tracks"]={"idle":{"*":[{"time":0,"rotation_degrees":0}]}}
            with self.assertRaisesRegex(ValueError,"never selected"):
                engine.build(cfg,root/"result",root)
            self.assertFalse((root/"result").exists())

    def test_track_keyframes_are_checked_even_when_unsampled(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=self.fixture(root)
            cfg["components"][2]["motion_tracks"]["default"]["*"]=[{"time":.5,"position":[0,0]},{"time":.4,"position":[1,1]}]
            with self.assertRaisesRegex(ValueError,"times must increase"):
                engine.build(cfg,root/"result",root)

    def test_track_for_a_missing_direction_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=self.fixture(root)
            cfg["components"][1]["mount_tracks"]["deploy"]["N"]=[{"time":0,"rotation_degrees":0}]
            with self.assertRaisesRegex(ValueError,"direction the bundle does not have"):
                engine.build(cfg,root/"result",root)

    def test_frame_choice_follows_frame_durations(self):
        frames=[{"duration_ms":100},{"duration_ms":300}]
        self.assertEqual([engine.frame_index(frames,t) for t in (0,.24,.26,.99,1)],[0,0,1,1,1])

    def test_draw_order_is_recorded_per_direction(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=self.fixture(root)
            cfg["components"][2]["draw_order"]={"S":-1,"*":7}
            out=engine.build(cfg,root/"generated"/cfg["name"],root)
            data=json.loads((out/(cfg["name"]+".bundle.json")).read_text())
            tip=next(c for c in data["components"] if c["id"]=="tip")
            self.assertEqual(tip["draw_order"],{"S":-1,"E":7})

    def test_single_component_bundle_needs_no_review_packet(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            Image.new("RGBA",(8,8),PINK).save(root/"solo.png")
            solo=Image.open(root/"solo.png"); solo.putpixel((3,3),(10,20,30,255)); solo.save(root/"solo.png")
            cfg={"name":"solo_machine_v001","directions":["S"],"sample_times":[0],
                 "components":[{"id":"body","parent":None,"views":{"S":{"frames":[{"file":"solo.png","pivot":[4,4]}]}}}]}
            out=engine.build(cfg,root/"generated"/cfg["name"],root)
            data=json.loads((out/"solo_machine_v001.bundle.json").read_text())
            self.assertIsNone(data["visual_review_protocol"])
            self.assertEqual(data["validation"]["parent_cleanup"], "not_applicable")

if __name__=="__main__":
    unittest.main()
