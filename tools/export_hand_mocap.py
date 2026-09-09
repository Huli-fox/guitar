"""Run with Blender --background --factory-startup --python this_file.

Reads the saved source scene, samples evaluated rigid bodies, and writes a
standalone Mixamo-named hand subset. No source file is overwritten.
"""
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'blender/hand_mocap'
SOURCE = ROOT / 'blender/source_validation/source_validation.blend'


def tpose_layout():
    """Synthetic body dimensions in metres; hands use MJCF zero-joint rest."""
    layout = {}
    def add(name, head, tail, parent=None):
        # Place the helper torso behind/above this recording's playing area.
        # Compact helper proportions keep both recorded wrists within reach.
        def place(point):
            x, y, z = point
            # Recorded LH is at smaller world X than RH. Face +Y so the
            # anatomical left shoulder sits on that same side of the take.
            return Vector((-x + .2, -y - .18, z - .27 if z >= .9 else z * .7))
        layout['mixamorig:' + name] = (place(head), place(tail),
                                      'mixamorig:' + parent if parent else None)
    add('Hips', (0, 0, .9), (0, 0, 1.0))
    add('Spine', (0, 0, 1.0), (0, 0, 1.15), 'Hips')
    add('Spine1', (0, 0, 1.15), (0, 0, 1.3), 'Spine')
    add('Spine2', (0, 0, 1.3), (0, 0, 1.45), 'Spine1')
    add('Neck', (0, 0, 1.45), (0, 0, 1.55), 'Spine2')
    add('Head', (0, 0, 1.55), (0, 0, 1.75), 'Neck')
    rest = {}
    for side, word, sign, filename in [('LH', 'Left', 1, 'left_hand_guitar.xml'),
                                        ('RH', 'Right', -1, 'right_hand.xml')]:
        add(word + 'Shoulder', (0, 0, 1.45), (sign * .18, 0, 1.45), 'Spine2')
        add(word + 'Arm', (sign * .18, 0, 1.45), (sign * .50, 0, 1.45), word + 'Shoulder')
        add(word + 'ForeArm', (sign * .50, 0, 1.45), (sign * .82, 0, 1.45), word + 'Arm')
        add(word + 'UpLeg', (sign * .10, 0, .9), (sign * .10, 0, .49), 'Hips')
        add(word + 'Leg', (sign * .10, 0, .49), (sign * .10, 0, .08), word + 'UpLeg')
        add(word + 'Foot', (sign * .10, 0, .08), (sign * .10, -.13, .04), word + 'Leg')
        add(word + 'ToeBase', (sign * .10, -.13, .04), (sign * .10, -.22, .04), word + 'Foot')
        # Fingers point outward, palms face down, thumbs toward the front (+Y).
        y = Vector((sign, 0, 0))
        z = Vector((0, 0, 1))
        x = y.cross(z)
        wrist = Matrix((x, y, z)).transposed().to_4x4()
        wrist.translation = Vector((-sign * .82 + .2, -.18, 1.18))
        root = ET.parse(ROOT / 'assets' / filename).getroot()
        body = next(b for b in root.iter('body') if b.get('name') == side + ':wrist')
        def visit(node, matrix):
            rest[node.get('name')] = matrix
            for child in node.findall('body'):
                pos = Vector(tuple(map(float, child.get('pos', '0 0 0').split())))
                quat = Quaternion(tuple(map(float, child.get('quat', '1 0 0 0').split())))
                local = Matrix.LocRotScale(pos, quat, Vector((1, 1, 1)))
                visit(child, matrix @ local)
        visit(body, wrist)
    return layout, rest


def aim_matrix(head, tail, rest_matrix):
    rotation = rest_matrix.to_quaternion()
    delta = (rotation @ Vector((0, 1, 0))).rotation_difference((tail - head).normalized())
    result = (delta @ rotation).to_matrix().to_4x4()
    result.translation = head
    return result


def main():
    global OUT
    tpose = '--tpose' in sys.argv
    if tpose:
        OUT = ROOT / 'blender/hand_mocap_tpose'
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    frames = list(range(scene.frame_start, scene.frame_end + 1))
    specs = []
    for side, word, suffix in [('LH', 'Left', 'l'), ('RH', 'Right', 'r')]:
        hand = 'mixamorig:' + word + 'Hand'
        specs.append((side + ':wrist', hand, None, side + ':middle1', 'c_hand_fk.' + suffix))
        for finger in ['thumb', 'index', 'middle', 'ring', 'pinky']:
            for i in range(1, 4):
                name = hand + finger.title() + str(i)
                parent = hand if i == 1 else hand + finger.title() + str(i - 1)
                end = side + ':' + finger + (str(i + 1) if i < 3 else '_top')
                specs.append((side + ':' + finger + str(i), name, parent, end,
                              'c_' + finger + str(i) + '.' + suffix))
    samples = {}
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        samples[frame] = {src: scene.objects[src].matrix_world.copy() for src, *_ in specs}
    scene.frame_set(frames[0])
    bpy.context.view_layer.update()
    ends = {end: scene.objects[end].matrix_world.translation.copy() for _, _, _, end, _ in specs}
    body_layout, rest = tpose_layout() if tpose else ({}, samples[frames[0]])
    if tpose:
        ends = {end: rest[end].translation.copy() for _, _, _, end, _ in specs}
    # The output contains only the new armature. Source data was sampled first.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    rig = bpy.data.objects.new('Hands_Mocap_Source', bpy.data.armatures.new('Hands_Mocap_Source'))
    scene.collection.objects.link(rig)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    rig.show_in_front = True
    bpy.ops.object.mode_set(mode='EDIT')
    for name, (head, tail, parent) in body_layout.items():
        bone = rig.data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = rig.data.edit_bones[parent]
    for src, name, parent, end, _ in specs:
        bone = rig.data.edit_bones.new(name)
        bone.head = rest[src].translation
        bone.tail = ends[end]
        bone.align_roll(rest[src].to_3x3() @ Vector((0, 0, 1)))
        if parent:
            bone.parent = rig.data.edit_bones[parent]
        elif tpose:
            bone.parent = rig.data.edit_bones[name.replace('Hand', 'ForeArm')]
        bone.use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    offsets = {src: rest[src].inverted() @ rig.data.bones[name].matrix_local
               for src, name, *_ in specs}
    all_names = set(rig.data.bones.keys())
    max_arm_stretch = 1.0
    expected = {}
    previous = {}
    for frame in frames:
        scene.frame_set(frame)
        expected[frame] = {}
        if tpose:
            # Synthetic arm pose solves toward the measured wrist; never drives
            # or alters the measured hands. Not a measured elbow trajectory.
            for side, word, sign in [('LH', 'Left', 1), ('RH', 'Right', -1)]:
                arm_name = 'mixamorig:' + word + 'Arm'
                fore_name = 'mixamorig:' + word + 'ForeArm'
                shoulder = rig.data.bones[arm_name].head_local
                wrist = samples[frame][side + ':wrist'].translation
                direction = wrist - shoulder
                distance = direction.length
                direction.normalize()
                pole = Vector((-sign, -.4, -.3))
                perpendicular = (pole - direction * pole.dot(direction)).normalized()
                assert distance < .64, ('Synthetic arms cannot reach this recording', side, frame, distance)
                length = .32
                elbow = (shoulder + wrist) / 2 + perpendicular * math.sqrt(max(0, length**2 - (distance/2)**2))
                for name, head, tail in [(arm_name, shoulder, elbow), (fore_name, elbow, wrist)]:
                    pb = rig.pose.bones[name]
                    mat = aim_matrix(head, tail, rig.data.bones[name].matrix_local)
                    pb.matrix = mat
                    bpy.context.view_layer.update()
            for name in body_layout:
                pb = rig.pose.bones[name]
                pb.rotation_mode = 'QUATERNION'
                if name in previous and pb.rotation_quaternion.dot(previous[name]) < 0:
                    pb.rotation_quaternion.negate()
                previous[name] = pb.rotation_quaternion.copy()
                for prop in ('location', 'rotation_quaternion', 'scale'):
                    pb.keyframe_insert(data_path=prop, frame=frame, group=name)
        for src, name, *_ in specs:
            pb = rig.pose.bones[name]
            mat = samples[frame][src] @ offsets[src]
            expected[frame][name] = mat.copy()
            pb.rotation_mode = 'QUATERNION'
            pb.matrix = mat
            if name in previous and pb.rotation_quaternion.dot(previous[name]) < 0:
                pb.rotation_quaternion.negate()
            previous[name] = pb.rotation_quaternion.copy()
            for prop in ('location', 'rotation_quaternion', 'scale'):
                pb.keyframe_insert(data_path=prop, frame=frame, group=name)
            bpy.context.view_layer.update()
    action = rig.animation_data.action
    action.name = 'Hands_Mocap_60fps'
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:
                        key.interpolation = 'LINEAR'
    def verify(arm, shift=0, matrix_tolerance=1e-4):
        pos_error = matrix_error = 0.0
        for frame in frames:
            scene.frame_set(frame + shift)
            bpy.context.view_layer.update()
            for _, name, *_ in specs:
                actual = arm.matrix_world @ arm.pose.bones[name].matrix
                target = expected[frame][name]
                pos_error = max(pos_error, (actual.translation - target.translation).length)
                matrix_error = max(matrix_error, max(abs(actual[i][j] - target[i][j])
                                                    for i in range(4) for j in range(4)))
        assert pos_error < 1e-5, pos_error
        assert matrix_error < matrix_tolerance, matrix_error
        return {'frames_checked': len(frames), 'max_position_error_m': pos_error,
                'max_matrix_component_error': matrix_error}
    report = {'baked_vs_source': verify(rig), 'bone_count': len(all_names),
              'fps': scene.render.fps / scene.render.fps_base, 'frame_range': [frames[0], frames[-1]],
              'rest_pose_source_frame': frames[0], 'standard': 'Mixamo hand naming subset, not a full Mixamo rig'}
    if tpose:
        roots = [b.name for b in rig.data.bones if b.parent is None]
        assert roots == ['mixamorig:Hips'], roots
        report.update(rest_pose_source_frame=None, standard='Mixamo names; synthetic T-pose body and MJCF zero-joint hands',
                      root_bone=roots[0], measured_bones=32, synthetic_bones=len(body_layout),
                      max_synthetic_arm_stretch=max_arm_stretch)
    rig['naming_standard'] = report['standard']
    rig['rest_pose'] = 'T-pose body / MJCF zero-joint hands' if tpose else 'Source frame 0; align target reference pose in ARP before retargeting'
    scene.frame_set(120)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.overlay.show_extras = True
                area.spaces.active.region_3d.view_perspective = 'PERSP'
                area.spaces.active.region_3d.view_location = (0, 0, 0.9)
                area.spaces.active.region_3d.view_distance = 1.3
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'hands_mocap.blend'))
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'hands_mocap.fbx'), use_selection=True,
        object_types={'ARMATURE'}, add_leaf_bones=False, bake_anim=True,
        bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False, bake_anim_step=1, bake_anim_simplify_factor=0,
        axis_forward='-Z', axis_up='Y')
    mapping = [{'source_node': src, 'source_bone': name, 'target_arp_fk': target}
               for src, name, _, _, target in specs]
    (OUT / 'bone_mapping.json').write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    # ARP's legacy five-line record is still supported by its current importer.
    (OUT / 'hands_mixamo_fk.bmap').write_text(''.join(
        target + '\n' + name + '\nFalse\nFalse\n\n' for _, name, _, _, target in specs), encoding='utf-8')
    ik_records = []
    if tpose:
        ik_records.append('c_root_master.x\nmixamorig:Hips\nTrue\nFalse\n\n')
        fk_path = OUT / 'hands_mixamo_fk.bmap'
        fk_path.write_text(ik_records[0] + fk_path.read_text(encoding='utf-8'), encoding='utf-8')
    for _, name, parent, _, target in specs:
        if parent is None:
            target = target.replace('hand_fk', 'hand_ik')
            first = target + '%False%ABSOLUTE%0,0,0%0,0,0%1.0%False%True%Y%'
            ik_records.append(first + '\n' + name + '\nFalse\nTrue\n\n')
        else:
            ik_records.append(target + '\n' + name + '\nFalse\nFalse\n\n')
    (OUT / 'hands_mixamo_ik.bmap').write_text(''.join(ik_records), encoding='utf-8')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = int(report['fps'])
    bpy.ops.import_scene.fbx(filepath=str(OUT / 'hands_mocap.fbx'), anim_offset=0,
                             automatic_bone_orientation=False)
    imported = [o for o in scene.objects if o.type == 'ARMATURE']
    assert len(imported) == 1 and len(scene.objects) == 1
    assert set(imported[0].pose.bones.keys()) == all_names
    # FBX stores Euler curves; near singularities its float conversion loses
    # more rotation precision than the native quaternion action.
    report['fbx_roundtrip_vs_source'] = verify(imported[0], matrix_tolerance=5e-4)
    (OUT / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('HAND MOCAP VERIFIED', json.dumps(report))


if __name__ == '__main__':
    main()
