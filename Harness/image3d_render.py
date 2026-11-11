"""Blender worker: render the actual candidate geometry without colour/texture."""
import bpy
from mathutils import Vector
import json
from pathlib import Path
import sys
import hashlib
import shutil

folder = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
shutil.copy2(__file__, folder / "render.snapshot.py")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.ply_import(filepath=str(folder / "shape-mm.ply"))
mesh = bpy.context.object
mesh.scale = (0.001, 0.001, 0.001)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
mesh.name = "Image3D appearance blank - NOT functional CAD"
for polygon in mesh.data.polygons:
    polygon.use_smooth = True
mat = bpy.data.materials.new("Neutral geometry inspection")
mat.diffuse_color = (0.46, 0.47, 0.49, 1)
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.46, 0.47, 0.49, 1)
bsdf.inputs["Roughness"].default_value = 0.68
mesh.data.materials.clear()
mesh.data.materials.append(mat)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = "MILLIMETERS"
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.display.shading.cavity_type = "BOTH"
scene.display.shading.background_type = "WORLD"
scene.render.resolution_x = 680
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = True
scene.world = bpy.data.worlds.new("Neutral studio")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.91, 0.91, 0.91, 1)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.65
scene.world.color = (0.83, 0.83, 0.83)
scene.view_settings.view_transform = "Standard"
height = mesh.dimensions.z
target = Vector((0, 0, height / 2))
for name, pos, power, size in [
    ("Key", (-height*1.4, -height*2, height*2.6), 800*height**2, height*1.7),
    ("Fill", (height*2, -height, height*1.1), 400*height**2, height*2),
]:
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.shape, data.size = power, "DISK", size
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = pos
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
camera_data = bpy.data.cameras.new("Inspection orthographic camera")
camera = bpy.data.objects.new("Inspection orthographic camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera_data.type = "ORTHO"
camera_data.ortho_scale = height * 1.22
camera_data.clip_end = height * 20
views = {
    "front": (0, -height*3, height/2), "right": (height*3, 0, height/2),
    "back": (0, height*3, height/2), "quarter": (height*1.5, -height*3, height*0.95),
    "top": (0, -height*0.01, height*4),
    "left": (-height*3, 0, height/2),
    "bottom": (0, -height*0.01, -height*3),
    "back_quarter": (-height*1.5, height*3, height*0.95),
}
records = {}
for name, position in views.items():
    camera.location = position
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(folder / f"gray-{name}.png")
    bpy.ops.render.render(write_still=True)
    records[name] = {"position_mm": [v * 1000 for v in position], "target_mm": [v * 1000 for v in target],
                     "projection": "orthographic", "ortho_scale_mm": camera_data.ortho_scale * 1000,
                     "sha256": hashlib.sha256((folder / f"gray-{name}.png").read_bytes()).hexdigest()}
bpy.ops.wm.save_as_mainfile(filepath=str(folder / "candidate.blend"))
(folder / "render-record.json").write_text(json.dumps({
    "mesh_sha256": hashlib.sha256((folder / "shape-mm.ply").read_bytes()).hexdigest(),
    "renderer": bpy.app.version_string, "engine": scene.render.engine, "material": "uniform gray, no texture",
    "view_schema": "eight-view-v2", "view_convention": "quarter is front_quarter; Z-up, front from -Y",
    "render_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "blend_sha256": hashlib.sha256((folder / "candidate.blend").read_bytes()).hexdigest(),
    "view_match": "approximate - concept perspective camera has not been calibrated",
    "views": records,
}, indent=2), encoding="utf-8")
