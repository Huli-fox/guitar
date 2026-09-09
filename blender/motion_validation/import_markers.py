import bpy
import json
from pathlib import Path
path = Path(__file__).with_name("event_markers.json")
for marker in list(bpy.context.scene.timeline_markers):
    if marker.name.startswith("Estimated note "):
        bpy.context.scene.timeline_markers.remove(marker)
for item in json.loads(path.read_text(encoding="utf-8")):
    bpy.context.scene.timeline_markers.new(item["name"], frame=item["frame"])
