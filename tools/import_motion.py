"""Import a recorded Isaac Gym motion JSON into Blender (see left_hand.md section 10).

The JSON is produced by MotionRecorder in main.py and looks like:

    {
      "fps": 60,
      "quaternion_order": "xyzw",
      "up_axis": "z",
      "links": ["LH:wrist", ...],
      "frames": [
        {
          "frame": 0, "time": 0.0, "reset": false,
          "links": {"LH:wrist": {"position": [x, y, z], "quaternion": [x, y, z, w]}, ...}
        }, ...
      ]
    }

For every recorded rigid body an Empty object is created and its world
position/rotation are keyframed at the JSON frame rate, so the motion can be
played back and inspected in Blender before retargeting it onto a character
rig or mesh.

Usage:
    # from a shell (opens Blender without UI)
    blender --background --python tools/import_motion.py -- recordings/left_hand_motion.json

    # or inside Blender's Text Editor: set MOTION_FILE below and run the script
    # (command line arguments after "--" take precedence).

Optional arguments:
    --scale S        scale factor applied to positions (default 1.0)
    --offset X Y Z   offset added to positions (default 0 0 0)
"""

import json
import sys

import bpy
from mathutils import Vector, Quaternion

# Used when running the script inside Blender's Text Editor without arguments.
MOTION_FILE = "recordings/left_hand_motion.json"


def parse_args():
    """Return (motion_file, scale, offset) from the command line.

    In Blender, arguments passed after "--" are available in sys.argv
    after the "--" separator.
    """
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    motion_file = MOTION_FILE
    scale = 1.0
    offset = (0.0, 0.0, 0.0)

    it = iter(argv)
    for arg in it:
        if arg == "--scale":
            scale = float(next(it))
        elif arg == "--offset":
            offset = tuple(float(next(it)) for _ in range(3))
        elif arg.startswith("-"):
            raise SystemExit("Unknown argument: {}".format(arg))
        else:
            motion_file = arg

    return motion_file, scale, offset


def load_motion(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_empty(name, empties, scale):
    """Create (or reuse) an Empty for one rigid body."""
    obj = empties.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = 'ARROWS'
        obj.empty_display_size = 0.02 * scale
        bpy.context.collection.objects.link(obj)
        empties[name] = obj
    return obj


def import_motion(path, scale=1.0, offset=(0.0, 0.0, 0.0)):
    data = load_motion(path)
    frames = data["frames"]
    if not frames:
        raise SystemExit("No frames found in {}".format(path))

    quat_order = data.get("quaternion_order", "xyzw")
    if quat_order != "xyzw":
        raise SystemExit(
            "Unsupported quaternion order '{}'. "
            "This importer expects Isaac Gym xyzw data.".format(quat_order))

    fps = data.get("fps", 60)
    scene = bpy.context.scene
    scene.render.fps = fps
    scene.frame_start = frames[0]["frame"]
    scene.frame_end = frames[-1]["frame"]

    empties = {}
    offset_vec = Vector(offset)

    for frame in frames:
        frame_id = frame["frame"]
        if frame.get("reset"):
            print("WARNING: environment reset marked at frame {} "
                  "(motion jumps back to the initial pose here; consider "
                  "splitting the take)".format(frame_id))
        for name, state in frame["links"].items():
            obj = get_empty(name, empties, scale)
            obj.location = Vector(state["position"]) * scale + offset_vec
            # Isaac Gym stores quaternions as (x, y, z, w);
            # mathutils.Quaternion expects (w, x, y, z).
            qx, qy, qz, qw = state["quaternion"]
            obj.rotation_mode = 'QUATERNION'
            obj.rotation_quaternion = Quaternion((qw, qx, qy, qz)).normalized()
            obj.keyframe_insert(data_path="location", frame=frame_id)
            obj.keyframe_insert(data_path="rotation_quaternion", frame=frame_id)

    print("Imported {} frames @ {} fps, {} objects, from {}".format(
        len(frames), fps, len(empties), path))
    print("Timeline: frames {} - {} ({} s)".format(
        scene.frame_start, scene.frame_end,
        (scene.frame_end - scene.frame_start + 1) / fps))


if __name__ == "__main__":
    motion_file, scale, offset = parse_args()
    import_motion(motion_file, scale=scale, offset=offset)
