"""Mock-based test for tools/import_motion.py (no Blender required).

Validates the JSON parsing / keyframe logic of the Blender importer on
machines without Blender installed (e.g. the headless Isaac Gym box).

Usage:
    python tools/test_import_motion_mock.py [motion.json]
"""
import math
import sys
import types


def install_mock_bpy():
    class FakeObj:
        def __init__(self, name):
            self.name = name
            self.location = None
            self.rotation_quaternion = None
            self.rotation_mode = None
            self.keyframes = []

        def keyframe_insert(self, data_path="", frame=0):
            assert data_path in ("location", "rotation_quaternion")
            self.keyframes.append((data_path, frame))

    created = []

    fake_bpy = types.ModuleType("bpy")

    class Scene:
        def __init__(self):
            self.render = types.SimpleNamespace(fps=None)
            self.frame_start = None
            self.frame_end = None

    scene = Scene()

    class Ctx:
        pass

    ctx = Ctx()
    ctx.scene = scene
    ctx.collection = types.SimpleNamespace(
        objects=types.SimpleNamespace(
            link=lambda o: created.append(o)))
    fake_bpy.context = ctx
    fake_bpy.data = types.SimpleNamespace(
        objects=types.SimpleNamespace(
            new=lambda name, ob: FakeObj(name)))

    fake_mathutils = types.ModuleType("mathutils")

    class Vector(list):
        def __add__(self, other):
            return Vector(a + b for a, b in zip(self, other))

        def __mul__(self, s):
            return Vector(a * s for a in self)

        __rmul__ = __mul__

    class Quaternion(tuple):
        def normalized(self):
            n = math.sqrt(sum(v * v for v in self))
            return Quaternion(v / n for v in self)

    fake_mathutils.Vector = Vector
    fake_mathutils.Quaternion = Quaternion

    sys.modules["bpy"] = fake_bpy
    sys.modules["mathutils"] = fake_mathutils
    return scene, created


def main(path):
    scene, created = install_mock_bpy()
    sys.path.insert(0, "tools")
    import import_motion

    import_motion.import_motion(path)

    with open(path) as handle:
        import json
        data = json.load(handle)
    n_frames = len(data["frames"])
    n_links = len(data["links"])

    assert scene.render.fps == data["fps"]
    assert scene.frame_end == data["frames"][-1]["frame"]
    assert len(created) == n_links, (len(created), n_links)
    for obj in created:
        assert len(obj.keyframes) == 2 * n_frames
        locs = [k for k in obj.keyframes if k[0] == "location"]
        rots = [k for k in obj.keyframes if k[0] == "rotation_quaternion"]
        assert len(locs) == n_frames and len(rots) == n_frames
        q = obj.rotation_quaternion
        norm = math.sqrt(sum(v * v for v in q))
        assert abs(norm - 1.0) < 1e-6, norm

    print("MOCK TEST PASSED: {} objects x {} frames, fps={}".format(
        len(created), n_frames, scene.render.fps))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "recordings/left_hand_motion.json")
