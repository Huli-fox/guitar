"""Build the repository's MJCF source meshes around recorded world poses.

blender --background --factory-startup --python-exit-code 1 \
    --python tools/build_source_scene.py -- --render

This is intentionally a loader for these source assets, not a general MJCF loader.
"""
import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from import_motion import import_motion


def numbers(element, key, default):
    return tuple(float(x) for x in element.get(key, default).split())


def transform(element):
    unsupported = {"euler", "axisangle", "xyaxes", "zaxis", "fromto"} & element.attrib.keys()
    if unsupported:
        raise ValueError(f"Unsupported MJCF transform: {unsupported}")
    return Matrix.LocRotScale(Vector(numbers(element, "pos", "0 0 0")),
                              Quaternion(numbers(element, "quat", "1 0 0 0")).normalized(),
                              Vector((1, 1, 1)))


def collection(name):
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


def move_to(obj, target):
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    target.objects.link(obj)


def material(name, color, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = 0.4
    return mat


def linear_keys(obj):
    action = obj.animation_data.action
    if hasattr(action, "layers") and len(action.layers):
        curves = [fc for layer in action.layers for strip in layer.strips
                  for bag in strip.channelbags for fc in bag.fcurves]
    else:
        curves = action.fcurves
    for curve in curves:
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'


def build(args):
    data = json.loads(args.motion.read_text(encoding='utf-8'))
    if data.get('up_axis') != 'z' or data.get('quaternion_order') != 'xyzw':
        raise ValueError('Expected z-up, xyzw recording')
    if any(f.get('reset') for f in data['frames']):
        raise ValueError('Split recordings at reset boundaries before building a scene')
    # Explicitly start a new scene. This script is meant to run in a fresh process.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.render.fps_base = 1
    recorded = import_motion(str(args.motion))
    poses = collection('01 Recorded world poses')
    fixed = collection('02 Fixed source frames')
    hands = collection('03 Source hand meshes')
    guitar_meshes = collection('04 Guitar and strings')
    references = collection('05 Contact references')
    cameras = collection('06 Inspection cameras')
    colors = {
        'LH': material('Left hand - blue', (0.10, 0.40, 0.73)),
        'RH': material('Right hand - orange', (0.95, 0.34, 0.09)),
        'wood': material('Neck - dark wood', (0.19, 0.095, 0.045)),
        'body': material('Source body proxy', (0.32, 0.19, 0.10)),
        'metal': material('Frets and strings', (0.65, 0.69, 0.73), 0.8),
        'tip': material('Fingertip reference - green', (0.2, 0.95, 0.4)),
        'pick': material('Pick reference - yellow', (1.0, 0.83, 0.05)),
    }
    for obj in recorded.values():
        move_to(obj, poses)
        obj.empty_display_size = 0.006
        obj.hide_set(True)
        obj['pose_source'] = 'Recorded rigid body world pose; metres; quaternion xyzw'
        linear_keys(obj)

    # Current recording has no sign flips; reject others until the importer
    # supports hemisphere correction for continuous component interpolation.
    for a, b in zip(data['frames'], data['frames'][1:]):
        for name in recorded:
            if sum(x*y for x, y in zip(a['links'][name]['quaternion'],
                                       b['links'][name]['quaternion'])) < 0:
                raise ValueError('Quaternion sign discontinuity: ' + name)

    nodes = dict(recorded)
    specs = {}
    geometry = []
    skipped = []

    def visit(body, parent, definitions, source):
        name = body.get('name')
        local = transform(body)
        if name in recorded:
            obj = recorded[name]  # Already world-space; do not apply MJCF rest twice.
        elif body.find('joint') is not None or body.find('freejoint') is not None:
            obj = None
            skipped.append(name)
        elif parent is None and name != 'guitar':
            raise ValueError('Unrecorded dynamic ancestor: ' + name)
        elif name in nodes:
            obj = nodes[name]
            if max(abs(obj.matrix_basis[i][j] - local[i][j])
                   for i in range(4) for j in range(4)) > 1e-6:
                raise ValueError('Conflicting shared frame: ' + name)
        else:
            obj = bpy.data.objects.new(name, None)
            fixed.objects.link(obj)
            obj.parent = parent
            obj.matrix_basis = local
            obj.empty_display_size = 0.004
            obj.hide_set(True)
            obj['pose_source'] = 'Fixed MJCF transform' if parent else 'Static MJCF guitar root (not recorded)'
            nodes[name] = obj
            specs[name] = (parent.name if parent else None, local.copy())

        for index, geom in enumerate(body.findall('geom')):
            if obj is None:
                raise ValueError('Mesh attached to unrecorded movable body: ' + name)
            kind = geom.get('type')
            mesh_scale = (1, 1, 1)
            if kind == 'mesh':
                definition = definitions[geom.get('mesh')]
                path = source.parent / definition.get('file')
                mesh_scale = numbers(definition, 'scale', '1 1 1')
                if path.suffix == '.stl':
                    bpy.ops.wm.stl_import(filepath=str(path), forward_axis='Y', up_axis='Z')
                elif path.suffix == '.obj':
                    bpy.ops.wm.obj_import(filepath=str(path), forward_axis='Y', up_axis='Z')
                else:
                    raise ValueError(str(path))
                imported = list(bpy.context.selected_objects)
                if len(imported) != 1:
                    raise ValueError('Expected one mesh in ' + str(path))
                mesh = imported[0]
            elif kind == 'box':
                bpy.ops.mesh.primitive_cube_add(size=2)
                mesh = bpy.context.object
                mesh_scale = numbers(geom, 'size', '1 1 1')  # MJCF half extents.
            else:
                raise ValueError('Unsupported geometry: ' + str(kind))
            mesh.name = f'Source {name} {index}'
            mesh.parent = obj
            mesh.matrix_parent_inverse = Matrix.Identity(4)
            mesh.matrix_basis = transform(geom) @ Matrix.Diagonal((*mesh_scale, 1))
            mesh['source_mjcf'] = str(source.relative_to(ROOT))
            mesh['source_body'] = name
            mesh['source_geometry'] = dict(geom.attrib).__str__()
            hand = name[:2] in ('LH', 'RH')
            move_to(mesh, hands if hand else guitar_meshes)
            mat = colors[name[:2]] if hand else colors['metal' if ('fret' in name or 'nut' in name) else 'wood']
            if name == 'G:body':
                mat = colors['body']
            if name == 'G:pluck_range':
                move_to(mesh, references)
                mesh.display_type = 'WIRE'
                mesh.hide_render = True
            mesh.data.materials.clear()
            mesh.data.materials.append(mat)
            geometry.append(mesh)
        for child in body.findall('body'):
            visit(child, obj, definitions, source)

    for filename in ('left_hand_guitar.xml', 'right_hand.xml'):
        source = ROOT / 'assets' / filename
        root = ET.parse(source).getroot()
        definitions = {e.get('name'): e for e in root.findall('asset/mesh')}
        for body in root.findall('worldbody/body'):
            visit(body, None, definitions, source)

    def line(name, points, radius, parent, mat, target):
        curve = bpy.data.curves.new(name, 'CURVE')
        curve.dimensions = '3D'
        curve.bevel_depth = radius
        curve.bevel_resolution = 2
        spline = curve.splines.new('POLY')
        spline.points.add(len(points)-1)
        for pt, co in zip(spline.points, points):
            pt.co = (*co, 1)
        obj = bpy.data.objects.new(name, curve)
        target.objects.link(obj)
        obj.parent = parent
        curve.materials.append(mat)
        return obj

    for i in range(1, 7):
        line(f'String {i}', [nodes[f'G:string{i}'].location, nodes[f'G:string{i}_end'].location],
             0.00022, nodes['guitar'], colors['metal'], guitar_meshes)
    for name, target in nodes.items():
        if name.endswith('_top') or name == 'RH:pick':
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.0015)
            marker = bpy.context.object
            marker.name = 'Contact ' + name
            marker.parent = target
            marker.matrix_basis = Matrix.Identity(4)
            marker.data.materials.append(colors['pick' if name == 'RH:pick' else 'tip'])
            marker['meaning'] = 'MJCF contact point, not measured contact or physical pick mesh'
            move_to(marker, references)

    scene.frame_set(120)
    bpy.context.view_layer.update()
    guitar_matrix = nodes['guitar'].matrix_world.copy()

    def camera(name, target_local, distance):
        target = guitar_matrix @ Vector(target_local)
        eye = target + guitar_matrix.to_quaternion() @ Vector((0.22, 0.12, 1.0)).normalized() * 1.5
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        cameras.objects.link(cam)
        cam.location = eye
        cam.rotation_euler = (target-eye).to_track_quat('-Z', 'Y').to_euler()
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = distance
        cam.data.clip_start = 0.01
        cam.data.clip_end = 20
        return cam

    views = {
        'overview': camera('Camera Overview', (0, -0.08, 0), 0.98),
        'left': camera('Camera Left contact', (0, -0.05, 0), 0.30),
        'right': camera('Camera Right contact', (0, -0.33, 0), 0.30),
    }
    # Fit camera-space bounds over the take, so translating hands stay in view.
    bounds = {view: [] for view in views}
    for frame in data['frames'][::20] + [data['frames'][-1]]:
        scene.frame_set(frame['frame'])
        bpy.context.view_layer.update()
        for view, cam in views.items():
            inv_rotation = cam.rotation_euler.to_matrix().transposed()
            for obj in geometry:
                body = obj['source_body']
                if view == 'left' and not body.startswith('LH:'):
                    continue
                if view == 'right' and not body.startswith('RH:'):
                    continue
                bounds[view].extend(inv_rotation @ (obj.matrix_world @ Vector(corner))
                                    for corner in obj.bound_box)
    for view, cam in views.items():
        points = bounds[view]
        lower = Vector(tuple(min(p[i] for p in points) for i in range(3)))
        upper = Vector(tuple(max(p[i] for p in points) for i in range(3)))
        center = (lower + upper) / 2
        cam.location = cam.rotation_euler.to_matrix() @ (center + Vector((0, 0, 1.5)))
        cam.data.ortho_scale = max(upper.x-lower.x, (upper.y-lower.y)*1100/800) * 1.16
    scene.camera = views['overview']
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    shading = scene.display.shading
    shading.light = 'STUDIO'
    shading.color_type = 'MATERIAL'
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = 'BOTH'
    shading.background_type = 'WORLD'
    scene.world = bpy.data.worlds.new('Inspection background')
    scene.world.color = (0.045, 0.055, 0.075)
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    scene.sync_mode = 'FRAME_DROP'
    for frame, label in ((0, 'Start / settling'), (120, 'Inspection pose'),
                         (203, 'Large translation'), (565, 'Fast finger rotation'), (570, 'Rotation peak'), (599, 'End')):
        scene.timeline_markers.new(label, frame=frame)
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
                area.spaces.active.clip_start = 0.001
                area.spaces.active.shading.color_type = 'MATERIAL'
                area.spaces.active.overlay.show_extras = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = validate(data, recorded, nodes, specs, geometry)
    report['static_guitar_source'] = 'MJCF root; recording does not include guitar pose'
    report['omitted_unrecorded_dofs'] = skipped
    report['contact_note'] = 'Distances are geometric references, not a test of note correctness or force.'
    (args.output.parent / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    readme = bpy.data.texts.new('START HERE')
    readme.write('SOURCE MODEL VALIDATION\n\n'
                 '600 source samples / 60 FPS; original world poses, no smoothing.\n'
                 'Blue = LH. Orange = RH. Green = fingertip reference. Yellow = pick reference.\n'
                 'Space: play. Numpad 0: camera view. Select inspection cameras in Outliner.\n'
                 'Collections 01/02 hold hidden pose frames (unhide to inspect axes).\n'
                 'Collection 05 toggles contact references; these are not contact-force indicators.\n'
                 'Guitar body is the original box proxy; source assets contain no full guitar body mesh.\n'
                 'Guitar root is reconstructed from static MJCF, not measured in this recording.\n'
                 'Palms, fingertips and pick follow fixed MJCF offsets from recorded bodies.\n'
                 'Timeline markers highlight startup and large inter-frame changes.\n'
                 'No character retargeting, IK correction, sound or physical string vibration.\n')
    scene['motion_file'] = str(args.motion)
    scene['source_scene_builder'] = 'tools/build_source_scene.py'
    scene.frame_set(120)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))
    if args.render:
        for view, frame in [('overview', 120), ('left', 0), ('left', 120), ('left', 203),
                            ('left', 565), ('left', 570), ('right', 120), ('right', 570)]:
            scene.camera = views[view]
            scene.frame_set(frame)
            scene.render.filepath = str(args.output.parent / f'{view}_{frame:04d}.png')
            bpy.ops.render.render(write_still=True)
    print('SOURCE SCENE VALIDATED:', json.dumps({k: v for k, v in report.items() if k != 'contact_samples'}))


def validate(data, recorded, nodes, specs, geometry):
    """Evaluate Blender dependencies at every sample, including fixed children."""
    scene = bpy.context.scene
    max_position_error = 0.0
    max_quaternion_error = 0.0
    max_fixed_error = 0.0
    contact_samples = []
    for frame in data['frames']:
        scene.frame_set(frame['frame'])
        bpy.context.view_layer.update()
        for name, obj in recorded.items():
            state = frame['links'][name]
            max_position_error = max(max_position_error, (obj.matrix_world.translation-Vector(state['position'])).length)
            q = state['quaternion']
            expected = Quaternion((q[3], q[0], q[1], q[2])).normalized()
            actual = obj.matrix_world.to_quaternion()
            max_quaternion_error = max(max_quaternion_error, min(
                sum((x-y)**2 for x,y in zip(actual, expected))**0.5,
                sum((x+y)**2 for x,y in zip(actual, expected))**0.5))
        for name, (parent, local) in specs.items():
            expected = nodes[parent].matrix_world @ local if parent else local
            actual = nodes[name].matrix_world
            max_fixed_error = max(max_fixed_error, max(abs(expected[i][j]-actual[i][j])
                                                      for i in range(4) for j in range(4)))
        if frame['frame'] in (0, 120, 203, 565, 570, 599):
            inv = nodes['guitar'].matrix_world.inverted()
            contact_samples.append({'frame': frame['frame'], 'guitar_local_points_m': {
                name: list(inv @ obj.matrix_world.translation) for name, obj in nodes.items()
                if name.endswith('_top') or name == 'RH:pick'}})
    assert max_position_error < 1e-6, max_position_error
    assert max_quaternion_error < 1e-5, max_quaternion_error
    assert max_fixed_error < 1e-6, max_fixed_error
    assert len([g for g in geometry if g['source_body'].startswith(('LH:', 'RH:'))]) == 34
    return dict(frames_checked=len(data['frames']), recorded_nodes=len(recorded),
                source_geometry_count=len(geometry), max_position_error_m=max_position_error,
                max_quaternion_component_error=max_quaternion_error, max_fixed_matrix_error=max_fixed_error,
                contact_samples=contact_samples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--motion', type=Path, default=ROOT / 'recordings/left_hand_motion.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'blender/source_validation/source_validation.blend')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    args.motion = args.motion.resolve()
    args.output = args.output.resolve()
    build(args)
