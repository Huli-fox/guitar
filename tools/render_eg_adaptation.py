"""Render EG with evaluated skeleton overlays; no changes to saved scene."""
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'blender/eg_adapted'
forward = '--forward' in sys.argv
bpy.ops.wm.open_mainfile(filepath=str(OUT / ('hands_on_EG_forward.blend' if forward else 'hands_on_EG.blend')))
scene = bpy.context.scene
scene.frame_set(120)
bpy.context.view_layer.update()
rig = scene.objects['Hands_Mocap_Source']
for pb in rig.pose.bones:
    head, tail = rig.matrix_world @ pb.head, rig.matrix_world @ pb.tail
    delta = tail-head
    radius = min(delta.length*.09, .009)
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=radius, radius2=0,
                                    depth=delta.length, location=(head+tail)/2)
    obj = bpy.context.object
    obj.rotation_euler = delta.to_track_quat('Z', 'Y').to_euler()
    mat = bpy.data.materials.new('Preview '+pb.name)
    mat.diffuse_color = (.08, .45, 1, 1) if 'Left' in pb.name else ((1, .25, .05, 1) if 'Right' in pb.name else (.65, .65, .65, 1))
    obj.data.materials.append(mat)
camera = bpy.data.objects.new('Preview Camera', bpy.data.cameras.new('Preview Camera'))
scene.collection.objects.link(camera)
scene.camera = camera
camera.data.type = 'ORTHO'
camera.data.clip_start = .001
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.color_type = 'MATERIAL'
scene.display.shading.light = 'STUDIO'
scene.display.shading.show_cavity = True
scene.display.shading.background_type = 'WORLD'
scene.world.color = (.04, .04, .04)
scene.render.resolution_x = 1200
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
left = rig.matrix_world @ rig.pose.bones['mixamorig:LeftHandMiddle2'].head
right = rig.matrix_world @ rig.pose.bones['mixamorig:RightHandIndex2'].head
for name, target, direction, scale in [
    ('overview', Vector((0, -.12, .76)), Vector((.3, -3, .4)), 1.65),
    ('left', left, Vector((.2, -2, 1.4)), .34),
    ('right', right, Vector((.2, -2, 1.4)), .34),
    ('side', Vector((0, -.18, .76)), Vector((3, -.4, .1)), 1.65),
]:
    camera.location = target + direction
    camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
    camera.data.ortho_scale = scale
    scene.render.filepath = str(OUT / f'{"forward_" if forward else ""}{name}_0120.png')
    bpy.ops.render.render(write_still=True)
