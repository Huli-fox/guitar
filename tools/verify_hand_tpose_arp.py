"""Validate saved T-pose and actual ARP mapping import against quin's rig.

Run in Blender with installed ARP enabled. Reads quin.blend without saving it.
"""
import json
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'blender/hand_mocap_tpose'

bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'blender/quin.blend'))
with bpy.data.libraries.load(str(OUT / 'hands_mocap.blend'), link=False) as (src, dst):
    dst.objects = ['Hands_Mocap_Source']
source = dst.objects[0]
bpy.context.scene.collection.objects.link(source)
scene = bpy.context.scene
target = scene.objects['rig']
assert [b.name for b in source.data.bones if b.parent is None] == ['mixamorig:Hips']
for word, sign in [('Left', 1), ('Right', -1)]:
    arm = source.data.bones['mixamorig:' + word + 'Arm']
    fore = source.data.bones['mixamorig:' + word + 'ForeArm']
    hand = source.data.bones['mixamorig:' + word + 'Hand']
    assert abs(arm.head_local.z - arm.tail_local.z) < 1e-6
    assert abs(fore.head_local.z - fore.tail_local.z) < 1e-6
    assert (fore.tail_local - hand.head_local).length < 1e-6
    assert hand.parent == fore and fore.parent == arm
    for finger in ['Index', 'Middle', 'Ring', 'Pinky']:
        for index in range(1, 4):
            bone = source.data.bones[f'mixamorig:{word}Hand{finger}{index}']
            assert (bone.tail_local - bone.head_local).normalized().x * -sign > .999
minimum_side_gap = float('inf')
maximum_wrist_gap = 0.0
for frame in range(600):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    left = [source.pose.bones['mixamorig:LeftArm'].head,
            source.pose.bones['mixamorig:LeftForeArm'].head,
            source.pose.bones['mixamorig:LeftHand'].head]
    right = [source.pose.bones['mixamorig:RightArm'].head,
             source.pose.bones['mixamorig:RightForeArm'].head,
             source.pose.bones['mixamorig:RightHand'].head]
    # Entire arm segments lie in disjoint X intervals, stronger than just
    # checking that the shoulder labels are ordered correctly.
    gap = min(p.x for p in right) - max(p.x for p in left)
    assert gap > .05, (frame, gap)
    minimum_side_gap = min(minimum_side_gap, gap)
    for word in ['Left', 'Right']:
        fore = source.pose.bones['mixamorig:' + word + 'ForeArm']
        hand = source.pose.bones['mixamorig:' + word + 'Hand']
        wrist_gap = (fore.tail - hand.head).length
        assert wrist_gap < 1e-5, (frame, word, wrist_gap)
        maximum_wrist_gap = max(maximum_wrist_gap, wrist_gap)
scene.source_rig = source.name
scene.target_rig = target.name
bpy.context.view_layer.objects.active = source
source.select_set(True)
assert bpy.ops.arp.build_bones_list() == {'FINISHED'}
checks = {'arm_geometry': {'frames_checked': 600,
          'minimum_left_right_x_gap_m': minimum_side_gap,
          'maximum_forearm_to_wrist_gap_m': maximum_wrist_gap}}
for filename in ['hands_mixamo_fk.bmap', 'hands_mixamo_ik.bmap']:
    assert bpy.ops.arp.import_config(filepath=str(OUT / filename), clear_current=True) == {'FINISHED'}
    items = list(scene.bones_map_v2)
    assert len(items) == 33
    roots = [item for item in items if item.set_as_root]
    assert len(roots) == 1
    assert roots[0].source_bone == 'mixamorig:Hips'
    assert roots[0].name == 'c_root_master.x'
    assert all(item.name in target.data.bones for item in items)
    assert all(item.source_bone in source.data.bones for item in items)
    assert len({item.name for item in items}) == 33
    if '_ik.' in filename:
        wrists = [i for i in items if i.source_bone.endswith('Hand')]
        assert len(wrists) == 2 and all(i.ik and i.ik_world for i in wrists)
    checks[filename] = {'mapping_count': len(items), 'root': roots[0].source_bone,
                        'root_target': roots[0].name, 'all_target_bones_exist': True}
(OUT / 'arp_mapping_validation.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
print('ARP MAPPING VERIFIED', json.dumps(checks))
