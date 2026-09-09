"""Adapt the user-edited hand source to EG's unchanged guitar geometry.

Run in Blender background mode. Writes blender/eg_adapted only.
"""
import bisect
import json
from pathlib import Path
import shutil
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'blender/eg_adapted'
HAND_FILE = ROOT / 'blender/hand_mocap_tpose/hands_mocap.blend'
SOURCE = ROOT / 'blender/source_validation/source_validation.blend'
EG = ROOT / 'blender/EG.blend'
FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
NAMES = ['mixamorig:' + word + 'Hand' + ending
         for word in ['Left', 'Right']
         for ending in [''] + [f + str(i) for f in FINGERS for i in range(1, 4)]]


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def interpolate(xs, ys, x):
    i = max(0, min(len(xs) - 2, bisect.bisect_right(xs, x) - 1))
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] * (1 - t) + ys[i + 1] * t


def fit_rigid(before, after):
    a, b = np.asarray(before), np.asarray(after)
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    u, _, vt = np.linalg.svd((a-ca).T @ (b-cb))
    rotation = vt.T @ u.T
    assert np.linalg.det(rotation) > .999, 'User edits include a reflection'
    result = Matrix(rotation.tolist()).to_4x4()
    result.translation = Vector(cb - rotation @ ca)
    error = max((result @ Vector(p) - Vector(q)).length for p, q in zip(before, after))
    assert error < 1e-5, ('Edited hands contain more than one rigid coordinate change', error)
    return result, error


def rotation_of(matrix):
    u, _, vt = np.linalg.svd(np.array(matrix.to_3x3()))
    r = u @ vt
    assert np.linalg.det(r) > 0
    return Matrix(r.tolist())


def aim(original, head, tail):
    q = original.to_quaternion()
    delta = (q @ Vector((0, 1, 0))).rotation_difference((tail-head).normalized())
    mat = (delta @ q).to_matrix().to_4x4()
    mat.translation = head
    return mat


def fabrik(points, root, target, lengths):
    points = [p.copy() for p in points]
    points[0] = root.copy()
    if (target-root).length >= sum(lengths):
        direction = (target-root).normalized()
        for i, length in enumerate(lengths):
            points[i+1] = points[i] + direction * length
        return points
    for _ in range(600):
        points[-1] = target.copy()
        for i in reversed(range(3)):
            points[i] = points[i+1] + (points[i]-points[i+1]).normalized() * lengths[i]
        points[0] = root.copy()
        for i in range(3):
            points[i+1] = points[i] + (points[i+1]-points[i]).normalized() * lengths[i]
        if (points[-1]-target).length < 1e-7:
            break
    return points


def reachable_wrist_shift(chains):
    """Nearest common wrist translation keeping all five targets reachable.

    Dykstra projections onto reach spheres preserve palm/base proportions and
    avoid stretching near-straight fingers when EG's fret spacing is larger.
    """
    shift = Vector()
    corrections = [Vector() for _ in chains]
    for _ in range(80):
        previous = shift.copy()
        for i, chain in enumerate(chains):
            center = chain['tip'] - chain['root']
            radius = sum(chain['lengths']) - .0003
            point = shift + corrections[i]
            delta = point - center
            projected = center + delta.normalized() * radius if delta.length > radius else point
            corrections[i] = point-projected
            shift = projected
        if (shift-previous).length < 1e-8:
            break
    return shift


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Actual mesh string rings, not object origins (origins are at tuners).
    bpy.ops.wm.open_mainfile(filepath=str(EG))
    scene = bpy.context.scene
    scene.frame_set(120)
    bpy.context.view_layer.update()
    guitar = scene.objects['Guitar_Rig']
    guitar_world = guitar.matrix_world.copy()
    eg_strings = []
    for label in ['E', 'A', 'D', 'G', 'B', 'E2']:
        obj = scene.objects['String ' + label].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = obj.to_mesh()
        vertices = [obj.matrix_world @ v.co for v in mesh.vertices]
        rings = []
        for z in [.685801, .45744, .089917]:
            ring = [p for p in vertices if abs(p.z-z) < 2e-6]
            assert len(ring) == 4, (label, z, len(ring))
            rings.append(sum(ring, Vector()) / len(ring))
        bridge = sorted([p for p in vertices if 0 < p.z < .04], key=lambda p: p.z)[-4:]
        assert len(bridge) == 4
        rings.append(sum(bridge, Vector()) / 4)
        eg_strings.append(sorted(rings, key=lambda p: p.z))
        obj.to_mesh_clear()
    fret_centres = []
    for i in range(22):
        obj = scene.objects[f'Fret.{i:03d}']
        fret_centres.append(sum((obj.matrix_world @ v.co for v in obj.data.vertices), Vector()) / len(obj.data.vertices))
    # Source geometry landmarks, and original world animation for validating
    # the user's origin/rotation correction independently of hard-coded shifts.
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    source_guitar = scene.objects['guitar'].matrix_world.copy()
    src_strings = [(scene.objects[f'G:string{i}'].location.copy(),
                    scene.objects[f'G:string{i}_end'].location.copy()) for i in range(6, 0, -1)]
    src_frets = [scene.objects[f'G:fret{i}'].location.copy() for i in range(1, 23)]
    axial = sorted([(src_strings[0][0].y, float(np.mean([s[-1].z for s in eg_strings])))] +
                   [(p.y, q.z) for p, q in zip(src_frets, fret_centres)] +
                   [(float(np.mean([s[1].y for s in src_strings])), float(np.mean([s[0].z for s in eg_strings])))])
    src_by_name = {}
    for word, side in [('Left', 'LH'), ('Right', 'RH')]:
        src_by_name['mixamorig:' + word + 'Hand'] = side + ':wrist'
        for finger in FINGERS:
            for i in range(1, 4):
                src_by_name[f'mixamorig:{word}Hand{finger}{i}'] = f'{side}:{finger.lower()}{i}'
    source_points = []
    for frame in [0, 120, 599]:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        source_points.extend(tuple(scene.objects[src_by_name[n]].matrix_world.translation) for n in NAMES)
    bpy.ops.wm.open_mainfile(filepath=str(HAND_FILE))
    scene = bpy.context.scene
    rig = next(o for o in scene.objects if o.type == 'ARMATURE')
    user_world = rig.matrix_world.copy()
    rest_before = {b.name: b.matrix_local.copy() for b in rig.data.bones}
    edited_points = []
    for frame in [0, 120, 599]:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        edited_points.extend(tuple(rig.matrix_world @ rig.pose.bones[n].head) for n in NAMES)
    correction, correction_error = fit_rigid(source_points, edited_points)
    reference_world = correction @ source_guitar
    reference_inverse = reference_world.inverted()
    # The field preserves fret interval and string interval coordinates, and
    # signed height above the local string surface. Extrapolate beyond strings
    # so palms and lifted fingers do not clamp onto the outer strings.
    def field(p):
        z = interpolate([v[0] for v in axial], [v[1] for v in axial], p.y)
        source_x = [interpolate([b.y, a.y], [b.x, a.x], p.y) for a, b in src_strings]
        dest = [interpolate([v.z for v in ring], ring, z) for ring in eg_strings]
        x = interpolate(source_x, [v.x for v in dest], p.x)
        y_surface = interpolate(source_x, [v.y for v in dest], p.x)
        return Vector((x, y_surface - (p.z - .0123), z))
    # EG remains metric and rigid. Position it around the original playing
    # area using the reference guitar's orientation and a central neck anchor.
    src_to_eg = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
    placement = (reference_world.to_3x3() @ src_to_eg.transposed()).to_4x4()
    anchor = Vector((0, -.15, .0123))
    placement.translation = reference_world @ anchor - placement.to_3x3() @ field(anchor)
    def map_point(world):
        return placement @ field(reference_inverse @ world)
    def map_rotation(world):
        eps = 1e-4
        columns = []
        for axis in range(3):
            delta = Vector((0, 0, 0))
            delta[axis] = eps
            columns.append((map_point(world+delta)-map_point(world-delta)) / (2*eps))
        return rotation_of(Matrix(columns).transposed()).to_4x4()
    samples = {}
    for frame in range(scene.frame_start, scene.frame_end+1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        samples[frame] = {pb.name: rig.matrix_world @ pb.matrix for pb in rig.pose.bones}
    # Copy action; user file and its rest pose are never rebuilt or overwritten.
    rig.animation_data.action = rig.animation_data.action.copy()
    rig.animation_data.action.name = 'Hands_EG_Adapted_60fps'
    action = rig.animation_data.action
    inverse_rig = rig.matrix_world.inverted()
    previous = {}
    metrics = {'max_tip_target_error_m': 0.0, 'max_hand_shift_m': 0.0,
               'max_arm_reach_error_m': 0.0, 'max_finger_length_error_m': 0.0,
               'max_wrist_reach_correction_m': 0.0}
    tip_errors = []
    check_targets = {}
    for frame, originals in samples.items():
        scene.frame_set(frame)
        check_targets[frame] = {}
        targets = {}
        for word in ['Left', 'Right']:
            hand_name = 'mixamorig:' + word + 'Hand'
            old_hand = originals[hand_name]
            wrist = map_point(old_hand.translation)
            rot_delta = map_rotation(old_hand.translation)
            hand = rot_delta @ old_hand
            hand.translation = wrist
            hand_delta = hand @ old_hand.inverted()
            chains = []
            for finger in FINGERS:
                names = [f'mixamorig:{word}Hand{finger}{i}' for i in range(1, 4)]
                lengths = [rig.data.bones[n].length for n in names]
                original_points = [originals[n].translation for n in names]
                original_points.append(originals[names[-1]] @ Vector((0, lengths[-1], 0)))
                root = hand_delta @ original_points[0]
                desired_tip = map_point(original_points[-1])
                initial = [map_point(p) for p in original_points]
                chains.append(dict(names=names, lengths=lengths, root=root, tip=desired_tip, initial=initial))
            shift = reachable_wrist_shift(chains)
            wrist += shift
            hand.translation = wrist
            targets[hand_name] = hand
            metrics['max_wrist_reach_correction_m'] = max(metrics['max_wrist_reach_correction_m'], shift.length)
            metrics['max_hand_shift_m'] = max(metrics['max_hand_shift_m'], (wrist-old_hand.translation).length)
            for chain in chains:
                names, lengths = chain['names'], chain['lengths']
                root, desired_tip, initial = chain['root']+shift, chain['tip'], chain['initial']
                solved = fabrik(initial, root, desired_tip, lengths)
                error = (solved[-1]-desired_tip).length
                metrics['max_tip_target_error_m'] = max(metrics['max_tip_target_error_m'], error)
                tip_errors.append(error)
                check_targets[frame][names[-1]] = list(desired_tip)
                for i, name in enumerate(names):
                    mat = aim(rot_delta @ originals[name], solved[i], solved[i+1])
                    targets[name] = mat
                    metrics['max_finger_length_error_m'] = max(metrics['max_finger_length_error_m'],
                                                              abs((solved[i+1]-solved[i]).length-lengths[i]))
            arm_name, fore_name = ('mixamorig:' + word + part for part in ['Arm', 'ForeArm'])
            shoulder = originals[arm_name].translation
            old_elbow = originals[fore_name].translation
            direction = wrist - shoulder
            distance = direction.length
            direction.normalize()
            a, b = rig.data.bones[arm_name].length, rig.data.bones[fore_name].length
            reach_error = max(0, distance - a - b)
            metrics['max_arm_reach_error_m'] = max(metrics['max_arm_reach_error_m'], reach_error)
            assert reach_error < 1e-5, (frame, word, reach_error)
            along = (a*a - b*b + distance*distance) / (2*distance)
            pole = old_elbow - shoulder
            perpendicular = (pole-direction*pole.dot(direction)).normalized()
            elbow = shoulder + direction * along + perpendicular * max(0, a*a-along*along)**.5
            targets[arm_name] = aim(originals[arm_name], shoulder, elbow)
            targets[fore_name] = aim(originals[fore_name], elbow, wrist)
        # Parent-first assignment, including unchanged spine/shoulders.
        for pb in rig.pose.bones:
            if pb.name not in targets:
                continue
            pb.rotation_mode = 'QUATERNION'
            parent_args = {}
            if pb.parent:
                parent_args = dict(parent_matrix=inverse_rig @ targets.get(pb.parent.name, originals[pb.parent.name]),
                                   parent_matrix_local=pb.parent.bone.matrix_local)
            pb.matrix_basis = pb.bone.convert_local_to_pose(
                inverse_rig @ targets[pb.name], pb.bone.matrix_local, invert=True, **parent_args)
            if pb.name in previous and pb.rotation_quaternion.dot(previous[pb.name]) < 0:
                pb.rotation_quaternion.negate()
            previous[pb.name] = pb.rotation_quaternion.copy()
            for prop in ['location', 'rotation_quaternion', 'scale']:
                pb.keyframe_insert(data_path=prop, frame=frame, group=pb.name)
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:
                        key.interpolation = 'LINEAR'
    assert rig.matrix_world == user_world
    assert all(b.matrix_local == rest_before[b.name] for b in rig.data.bones)
    # Append the full EG hierarchy (including controls), apply one rigid matrix
    # to its roots. Bone-parent transforms and modifiers stay intact.
    with bpy.data.libraries.load(str(EG), link=False) as (src, dst):
        dst.objects = [name for name in src.objects if name != 'Guide_image']
    eg_collection = bpy.data.collections.new('EG Guitar - original dimensions')
    scene.collection.children.link(eg_collection)
    for obj in dst.objects:
        eg_collection.objects.link(obj)
    bpy.context.view_layer.update()
    for obj in dst.objects:
        if obj.parent is None:
            obj.matrix_world = placement @ obj.matrix_world
        if obj.name in ['Guitar_Shape_Rig', 'Circle_Rig', 'Pick_Rig', 'Finger_Rig']:
            obj.hide_render = True
            obj.hide_set(True)
    bpy.context.view_layer.update()
    eg_rig = next(o for o in dst.objects if o.type == 'ARMATURE')
    assert max(abs((eg_rig.matrix_world @ guitar_world.inverted())[i][j]-placement[i][j])
               for i in range(4) for j in range(4)) < 1e-5
    assert abs(placement.to_3x3().determinant()-1) < 1e-5
    for old in list(bpy.data.collections):
        if old != eg_collection and not old.objects and not old.children:
            bpy.data.collections.remove(old)
    metrics['tip_target_error_p95_m'] = float(np.percentile(tip_errors, 95))
    metrics['tip_target_error_mean_m'] = float(np.mean(tip_errors))
    metrics.update(frames_checked=len(samples), user_coordinate_fit_error_m=correction_error,
                   guitar_uniform_scale=1.0, root_and_rest_preserved=True,
                   source_to_user_matrix=[list(row) for row in correction],
                   eg_placement_matrix=[list(row) for row in placement],
                   fret_pairs=[{'source_y': p.y, 'eg_z': q.z} for p, q in zip(src_frets, fret_centres)],
                   note='Geometric fret/string correspondence, not musical contact detection.')
    dump(OUT / 'adaptation.json', metrics)
    dump(OUT / 'tip_targets.json', check_targets)
    dump(OUT / 'landmarks.json', {'eg_strings_low_to_high': [[list(p) for p in s] for s in eg_strings],
                                 'source_strings_low_to_high': [[list(p) for p in s] for s in src_strings],
                                 'axial_pairs': axial})
    for filename in ['hands_mixamo_ik.bmap', 'hands_mixamo_fk.bmap']:
        shutil.copyfile(HAND_FILE.parent / filename, OUT / filename)
    scene.frame_set(120)
    scene.render.fps = 60
    scene.render.fps_base = 1
    rig['guitar_adaptation'] = 'EG original dimensions; fret/string-relative tip targets; fixed finger lengths'
    for obj in scene.objects:
        obj.select_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.clip_start = .001
                space.region_3d.view_location = Vector((0, -.1, .7))
                space.region_3d.view_distance = 1.8
                space.region_3d.view_perspective = 'ORTHO'
                space.region_3d.view_rotation = Vector((0, 1, 0)).to_track_quat('-Z', 'Y')
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'hands_on_EG.blend'))
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'hands_EG_motion.fbx'), use_selection=True,
        object_types={'ARMATURE'}, add_leaf_bones=False, bake_anim=True,
        bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False, bake_anim_step=1, bake_anim_simplify_factor=0,
        axis_forward='-Z', axis_up='Y')
    print('EG ADAPTED', json.dumps(metrics))


if __name__ == '__main__':
    main()
