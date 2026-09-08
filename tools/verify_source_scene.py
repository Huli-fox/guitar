"""Check the saved .blend without rebuilding it.

blender --background blender/source_validation/source_validation.blend \
    --python-exit-code 1 --python tools/verify_source_scene.py
"""
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]


def source_vertices(path):
    if path.suffix == '.obj':
        lines = path.read_text().splitlines()
        vertices = [tuple(map(float, line.split()[1:4]))
                    for line in lines if line.startswith('v ')]
        # The two neck files share unused vertices. Blender drops vertices that
        # are not referenced by faces; compare the actual surface geometry.
        indices = {int(item.split('/')[0])-1 for line in lines if line.startswith('f ')
                   for item in line.split()[1:]}
        return [vertices[i] for i in indices]
    raw = path.read_bytes()
    count = struct.unpack_from('<I', raw, 80)[0]
    if len(raw) == 84 + count * 50:
        return [struct.unpack_from('<3f', raw, 84 + face * 50 + 12 + vertex * 12)
                for face in range(count) for vertex in range(3)]
    return [tuple(map(float, line.split()[1:4])) for line in raw.decode().splitlines()
            if line.strip().startswith('vertex ')]


def main():
    scene = bpy.context.scene
    data = json.loads(Path(scene['motion_file']).read_text(encoding='utf-8'))
    assert scene.render.fps == data['fps']
    assert (scene.frame_start, scene.frame_end) == (0, 599)
    assert len([o for o in scene.objects if o.type == 'CAMERA']) == 3
    assert len([o for o in scene.objects if o.name.startswith('String ')]) == 6
    assert not any(o.library for o in scene.objects), 'External linked objects'
    assert not any(o.constraints for o in scene.objects), 'Unexpected runtime constraints'
    for frame_id in (0, 1, 120, 203, 565, 570, 571, 599):
        scene.frame_set(frame_id)
        bpy.context.view_layer.update()
        for name, state in data['frames'][frame_id]['links'].items():
            obj = bpy.data.objects[name]
            assert (obj.matrix_world.translation - Vector(state['position'])).length < 1e-6
            q = state['quaternion']
            expected = Quaternion((q[3], q[0], q[1], q[2])).normalized()
            assert abs(obj.matrix_world.to_quaternion().dot(expected)) > 1 - 1e-6
        # Independent fixed-offset check using the XML rather than cached builder specs.
        for filename in ('left_hand_guitar.xml', 'right_hand.xml'):
            root = ET.parse(ROOT / 'assets' / filename).getroot()
            for parent in root.iter('body'):
                for child in parent.findall('body'):
                    if child.get('name', '').endswith('_top') or child.get('name') == 'RH:pick':
                        local = Vector(tuple(map(float, child.get('pos').split())))
                        expected = bpy.data.objects[parent.get('name')].matrix_world @ local
                        assert (bpy.data.objects[child.get('name')].matrix_world.translation-expected).length < 1e-6
    meshes_checked = 0
    for filename in ('left_hand_guitar.xml', 'right_hand.xml'):
        source = ROOT / 'assets' / filename
        root = ET.parse(source).getroot()
        definitions = {m.get('name'): m for m in root.findall('asset/mesh')}
        for body in root.iter('body'):
            for index, geom in enumerate(body.findall('geom')):
                if geom.get('type') != 'mesh':
                    continue
                obj = bpy.data.objects[f"Source {body.get('name')} {index}"]
                mesh = definitions[geom.get('mesh')]
                vertices = source_vertices(source.parent / mesh.get('file'))
                # Import axis conversion, units and re-centering must not alter raw bounds.
                for axis in range(3):
                    for reduce in (min, max):
                        expected = reduce(v[axis] for v in vertices)
                        actual = reduce(v.co[axis] for v in obj.data.vertices)
                        assert abs(expected - actual) < 1e-6, (obj.name, axis, expected, actual)
                expected_scale = tuple(map(float, mesh.get('scale', '1 1 1').split()))
                assert (obj.scale - Vector(expected_scale)).length < 1e-6
                assert (obj.location - Vector(tuple(map(float, geom.get('pos', '0 0 0').split())))).length < 1e-6
                meshes_checked += 1
    assert meshes_checked == 36
    print(f'SAVED SCENE VERIFIED: 8 frames, 32 recorded nodes, fixed contact offsets, {meshes_checked} raw mesh bounds/scales/offsets')


if __name__ == '__main__':
    main()
