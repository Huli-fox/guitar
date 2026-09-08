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
import math

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

def preview_edges(names):
    edges = []

    for hand in ("LH", "RH"):
        for finger in ("thumb", "index", "middle", "ring", "pinky"):
            chain = [hand + ":wrist"] + [
                "{}:{}{}".format(hand, finger, joint)
                for joint in (1, 2, 3)
            ]

            for start, end in zip(chain, chain[1:]):
                if start in names and end in names:
                    edges.append((start, end))

    return edges


def create_preview(empties, scale=1.0):
    radius = 0.003 * abs(scale)
    scene = bpy.context.scene

    collection = bpy.data.collections.new("MotionPreview")
    scene.collection.children.link(collection)

    materials = {}

    for hand, color in (
        ("LH", (0.1, 0.45, 1.0, 1.0)),
        ("RH", (1.0, 0.35, 0.08, 1.0)),
    ):
        material = bpy.data.materials.new("MotionPreview_" + hand)
        material.diffuse_color = color
        materials[hand] = material

    def mesh_object(name, vertices, faces, hand):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)

        material = materials.get(hand, materials["LH"])
        mesh.materials.append(material)
        obj.color = material.diffuse_color

        return obj

    for name, target in empties.items():
        vertices = [
            (radius, 0, 0),
            (-radius, 0, 0),
            (0, radius, 0),
            (0, -radius, 0),
            (0, 0, radius),
            (0, 0, -radius),
        ]

        faces = [
            (0, 2, 4),
            (2, 1, 4),
            (1, 3, 4),
            (3, 0, 4),
            (2, 0, 5),
            (1, 2, 5),
            (3, 1, 5),
            (0, 3, 5),
        ]

        marker = mesh_object(
            "Joint_" + name,
            vertices,
            faces,
            name[:2],
        )
        marker.parent = target

    edges = preview_edges(empties)

    for start, end in edges:
        vertices = [
            (
                radius * 0.4 * math.cos(index * math.tau / 8),
                height,
                radius * 0.4 * math.sin(index * math.tau / 8),
            )
            for height in (0.0, 1.0)
            for index in range(8)
        ]

        faces = [
            (
                index,
                (index + 1) % 8,
                (index + 1) % 8 + 8,
                index + 8,
            )
            for index in range(8)
        ]

        connector = mesh_object(
            "Link_" + start + "_" + end,
            vertices,
            faces,
            start[:2],
        )

        location = connector.constraints.new("COPY_LOCATION")
        location.target = empties[start]

        stretch = connector.constraints.new("STRETCH_TO")
        stretch.target = empties[end]
        stretch.rest_length = 1.0
        stretch.volume = "NO_VOLUME"

    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.shading.color_type = "MATERIAL"

    scene.frame_set(scene.frame_start)

    for obj in bpy.context.selected_objects:
        obj.select_set(False)

    for obj in collection.objects:
        obj.select_set(True)

    print(
        "Preview created: {} markers, {} connectors; "
        "LH=blue, RH=orange".format(len(empties), len(edges))
    )

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
    return empties


if __name__ == "__main__":
    motion_file, scale, offset = parse_args()

    empties = import_motion(
        motion_file,
        scale=scale,
        offset=offset,
    )

    create_preview(empties, scale=scale)
