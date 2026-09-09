"""Read-back geometry/action checks, plus FBX roundtrip, for EG adaptation."""
import json
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'blender/eg_adapted'
def matrices_equal(a, b, tolerance=1e-6):
    return max(abs(a[i][j]-b[i][j]) for i in range(4) for j in range(4)) < tolerance

bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'blender/hand_mocap_tpose/hands_mocap.blend'))
rig = bpy.data.objects['Hands_Mocap_Source']
user_matrix = rig.matrix_world.copy()
user_rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
lengths = {b.name: b.length for b in rig.data.bones}
bpy.ops.wm.open_mainfile(filepath=str(OUT / 'hands_on_EG.blend'))
scene = bpy.context.scene
rig = bpy.data.objects['Hands_Mocap_Source']
assert matrices_equal(rig.matrix_world, user_matrix)
assert all(matrices_equal(b.matrix_local, user_rest[b.name]) for b in rig.data.bones)
assert scene.render.fps == 60 and (scene.frame_start, scene.frame_end) == (0, 599)
assert all(not o.library for o in scene.objects)
goals = json.loads((OUT / 'tip_targets.json').read_text())
report = {'user_origin_rotation_rest_preserved': True, 'frames_checked': 600}
max_tip = max_length = max_gap = 0.0
saved = {}
for frame in range(600):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    saved[frame] = {pb.name: rig.matrix_world @ pb.matrix for pb in rig.pose.bones}
    for name, target in goals[str(frame)].items():
        pb = rig.pose.bones[name]
        max_tip = max(max_tip, (rig.matrix_world @ pb.tail - Vector(target)).length)
    for pb in rig.pose.bones:
        max_length = max(max_length, abs((rig.matrix_world @ pb.tail - rig.matrix_world @ pb.head).length-lengths[pb.name]))
        if 'ForeArm' in pb.name or (any(f in pb.name for f in ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']) and pb.name[-1] in '23'):
            max_gap = max(max_gap, (pb.head-pb.parent.tail).length)
    for word in ['Left', 'Right']:
        max_gap = max(max_gap, (rig.pose.bones['mixamorig:'+word+'Hand'].head - rig.pose.bones['mixamorig:'+word+'ForeArm'].tail).length)
assert max_length < 1e-5, max_length
assert max_gap < 1e-5, max_gap
report.update(max_saved_tip_target_error_m=max_tip, max_bone_length_error_m=max_length,
              max_chain_joint_gap_m=max_gap)
# Compare evaluated EG string ring positions with pre-placement originals.
placement = Matrix(json.loads((OUT / 'adaptation.json').read_text())['eg_placement_matrix'])
landmarks = json.loads((OUT / 'landmarks.json').read_text())
max_guitar_error = 0.0
scene.frame_set(120)
dg = bpy.context.evaluated_depsgraph_get()
for label, rings in zip(['E', 'A', 'D', 'G', 'B', 'E2'], landmarks['eg_strings_low_to_high']):
    obj = scene.objects['String '+label].evaluated_get(dg)
    mesh = obj.to_mesh()
    points = [placement.inverted() @ obj.matrix_world @ v.co for v in mesh.vertices]
    for center in rings[1:]:
        near = sorted(points, key=lambda p: abs(p.z-center[2]))[:4]
        actual = sum(near, Vector()) / 4
        max_guitar_error = max(max_guitar_error, (actual-Vector(center)).length)
    obj.to_mesh_clear()
assert max_guitar_error < 1e-5, max_guitar_error
report['max_eg_string_landmark_error_m'] = max_guitar_error
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 60
bpy.ops.import_scene.fbx(filepath=str(OUT / 'hands_EG_motion.fbx'), anim_offset=0, automatic_bone_orientation=False)
rig = next(o for o in scene.objects if o.type == 'ARMATURE')
assert len(scene.objects) == 1 and len(rig.data.bones) == 52
max_position = max_matrix = 0.0
for frame, poses in saved.items():
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    for pb in rig.pose.bones:
        actual = rig.matrix_world @ pb.matrix
        expected = poses[pb.name]
        max_position = max(max_position, (actual.translation-expected.translation).length)
        max_matrix = max(max_matrix, max(abs(actual[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
assert max_position < 1e-5, max_position
assert max_matrix < 5e-4, max_matrix
report['fbx_max_position_error_m'] = max_position
report['fbx_max_matrix_component_error'] = max_matrix
(OUT / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('EG VERIFIED', json.dumps(report))
