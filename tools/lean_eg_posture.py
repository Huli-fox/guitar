"""Create a forward-lean variant from the current, user-reviewable EG scene."""
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from adapt_hands_to_eg import aim

OUT = ROOT / 'blender/eg_adapted'
bpy.ops.wm.open_mainfile(filepath=str(OUT / 'hands_on_EG.blend'))
scene = bpy.context.scene
rig = scene.objects['Hands_Mocap_Source']
world = rig.matrix_world.copy()
inverse = world.inverted()
rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
forward = Vector((0, -1, 0))
shift = forward * .16
translation = Matrix.Translation(shift)
rotation = Matrix.Rotation(math.radians(12), 4, 'X')
samples = {}
for frame in range(600):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    samples[frame] = {p.name: world @ p.matrix for p in rig.pose.bones}
rig.animation_data.action = rig.animation_data.action.copy()
rig.animation_data.action.name = 'Hands_EG_Forward_Lean_60fps'
upper = ['Spine', 'Spine1', 'Spine2', 'Neck', 'Head', 'LeftShoulder', 'RightShoulder']
previous = {}
expected = {}
min_reach_margin = float('inf')
for frame, old in samples.items():
    scene.frame_set(frame)
    pivot = old['mixamorig:Spine'].translation
    lean = Matrix.Translation(pivot) @ rotation @ Matrix.Translation(-pivot)
    targets = {n: mat.copy() for n, mat in old.items()}
    for name in upper:
        n = 'mixamorig:' + name
        targets[n] = lean @ old[n]
    for word, sign in [('Left', 1), ('Right', -1)]:
        for n in old:
            if n.startswith('mixamorig:' + word + 'Hand'):
                targets[n] = translation @ old[n]
        arm = 'mixamorig:' + word + 'Arm'
        fore = 'mixamorig:' + word + 'ForeArm'
        shoulder = lean @ old[arm].translation
        wrist = targets['mixamorig:' + word + 'Hand'].translation
        delta = wrist - shoulder
        distance = delta.length
        direction = delta.normalized()
        a, b = rig.data.bones[arm].length, rig.data.bones[fore].length
        min_reach_margin = min(min_reach_margin, a + b - distance)
        assert abs(a-b) < distance < a+b, (frame, word, distance)
        along = (a*a-b*b+distance*distance)/(2*distance)
        # Elbows bend outward and forward instead of remaining in the torso plane.
        pole = Vector((sign*.65, -.8, -.25))
        perpendicular = (pole-direction*pole.dot(direction)).normalized()
        elbow = shoulder + direction*along + perpendicular*math.sqrt(max(0, a*a-along*along))
        targets[arm] = aim(lean @ old[arm], shoulder, elbow)
        targets[fore] = aim(lean @ old[fore], elbow, wrist)
    expected[frame] = targets
    for pb in rig.pose.bones:
        if pb.name not in ['mixamorig:'+n for n in upper] and not any(
                token in pb.name for token in ['Arm', 'Hand']):
            continue
        parent_args = {}
        if pb.parent:
            parent_args = dict(parent_matrix=inverse @ targets[pb.parent.name],
                               parent_matrix_local=pb.parent.bone.matrix_local)
        pb.rotation_mode = 'QUATERNION'
        pb.matrix_basis = pb.bone.convert_local_to_pose(inverse @ targets[pb.name],
                            pb.bone.matrix_local, invert=True, **parent_args)
        if pb.name in previous and pb.rotation_quaternion.dot(previous[pb.name]) < 0:
            pb.rotation_quaternion.negate()
        previous[pb.name] = pb.rotation_quaternion.copy()
        for prop in ['location', 'rotation_quaternion', 'scale']:
            pb.keyframe_insert(data_path=prop, frame=frame, group=pb.name)
for layer in rig.animation_data.action.layers:
    for strip in layer.strips:
        for bag in strip.channelbags:
            for curve in bag.fcurves:
                for key in curve.keyframe_points:
                    key.interpolation = 'LINEAR'
collection = bpy.data.collections['EG Guitar - original dimensions']
guitar_before = {obj.name: obj.matrix_world.copy() for obj in collection.objects}
for obj in collection.objects:
    if obj.parent is None:
        obj.matrix_world = translation @ obj.matrix_world
bpy.context.view_layer.update()
assert max(abs(obj.matrix_world[i][j]-(translation@guitar_before[obj.name])[i][j])
           for obj in collection.objects for i in range(4) for j in range(4)) < 1e-5
assert rig.matrix_world == world
assert all(b.matrix_local == rest[b.name] for b in rig.data.bones)
scene.frame_set(120)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'hands_on_EG_forward.blend'))
bpy.ops.wm.open_mainfile(filepath=str(OUT / 'hands_on_EG_forward.blend'))
scene = bpy.context.scene
rig = scene.objects['Hands_Mocap_Source']
max_error = max_gap = 0.0
for frame, targets in expected.items():
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    for pb in rig.pose.bones:
        mat = rig.matrix_world @ pb.matrix
        max_error = max(max_error, max(abs(mat[i][j]-targets[pb.name][i][j]) for i in range(4) for j in range(4)))
    for word in ['Left', 'Right']:
        for a, b in [('Arm', 'ForeArm'), ('ForeArm', 'Hand')]:
            max_gap = max(max_gap, (rig.pose.bones['mixamorig:'+word+a].tail-
                                    rig.pose.bones['mixamorig:'+word+b].head).length)
assert max_error < 1e-5, max_error
assert max_gap < 1e-5, max_gap
for obj in scene.objects:
    obj.select_set(False)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.fbx(filepath=str(OUT/'hands_EG_forward.fbx'), use_selection=True,
    object_types={'ARMATURE'}, add_leaf_bones=False, bake_anim=True,
    bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
    bake_anim_use_all_actions=False, bake_anim_step=1, bake_anim_simplify_factor=0,
    axis_forward='-Z', axis_up='Y')
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 60
bpy.ops.import_scene.fbx(filepath=str(OUT/'hands_EG_forward.fbx'), anim_offset=0,
                        automatic_bone_orientation=False)
rig = next(o for o in scene.objects if o.type=='ARMATURE')
fbx_position = fbx_matrix = 0.0
for frame, targets in expected.items():
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    for pb in rig.pose.bones:
        actual = rig.matrix_world @ pb.matrix
        target = targets[pb.name]
        fbx_position = max(fbx_position, (actual.translation-target.translation).length)
        fbx_matrix = max(fbx_matrix, max(abs(actual[i][j]-target[i][j]) for i in range(4) for j in range(4)))
assert fbx_position < 1e-5 and fbx_matrix < 5e-4, (fbx_position, fbx_matrix)
report = dict(frames_checked=600, lean_degrees=12, guitar_and_hands_forward_m=.16,
    max_saved_matrix_error=max_error, max_arm_joint_gap_m=max_gap,
    min_arm_reach_margin_m=min_reach_margin, fbx_position_error_m=fbx_position,
    fbx_matrix_error=fbx_matrix, hands_relative_to_guitar_preserved=True,
    original_object_transform_rest_hips_legs_preserved=True)
body_mapping = [('Spine', 'c_spine_01.x'), ('Spine1', 'c_spine_02.x'),
                ('Spine2', 'c_spine_03.x'), ('Neck', 'c_neck.x'), ('Head', 'c_head.x'),
                ('LeftShoulder', 'c_shoulder.l'), ('RightShoulder', 'c_shoulder.r')]
mapping = (OUT/'hands_mixamo_ik.bmap').read_text(encoding='utf-8')
mapping += ''.join(f'{target}\nmixamorig:{source}\nFalse\nFalse\n\n' for source, target in body_mapping)
(OUT/'hands_forward_ik.bmap').write_text(mapping, encoding='utf-8')
(OUT/'forward_posture_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('FORWARD POSTURE VERIFIED', json.dumps(report))
