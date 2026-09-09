"""Render front/oblique bone previews without modifying the saved armature."""
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'blender/hand_mocap_tpose'
bpy.ops.wm.open_mainfile(filepath=str(OUT / 'hands_mocap.blend'))
scene = bpy.context.scene
scene.frame_set(120)
bpy.context.view_layer.update()
rig = scene.objects['Hands_Mocap_Source']
for bone in rig.pose.bones:
    head, tail = bone.head.copy(), bone.tail.copy()
    delta = tail - head
    color = (0.12, .45, .9, 1) if 'Left' in bone.name else ((1, .35, .10, 1) if 'Right' in bone.name else (.6, .6, .6, 1))
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=min(delta.length * .12, .022),
                                    radius2=0, depth=delta.length, location=(head + tail) / 2)
    obj = bpy.context.object
    obj.rotation_euler = delta.to_track_quat('Z', 'Y').to_euler()
    obj.color = color
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6,
                                       radius=min(delta.length * .09, .011), location=head)
    bpy.context.object.color = color
camera = bpy.data.objects.new('Preview Camera', bpy.data.cameras.new('Preview Camera'))
scene.collection.objects.link(camera)
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 1.5
scene.camera = camera
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.color_type = 'OBJECT'
scene.display.shading.light = 'STUDIO'
scene.display.shading.show_shadows = True
scene.display.shading.background_type = 'WORLD'
scene.world.color = (.04, .04, .04)
scene.render.resolution_x = 900
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
target = Vector((.2, -.10, .77))
for view, eye in [('front', Vector((.2, 3, .77))), ('oblique', Vector((2, 3, 1.3)))]:
    camera.location = eye
    camera.rotation_euler = (target - eye).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(OUT / f'corrected_{view}_0120.png')
    bpy.ops.render.render(write_still=True)
