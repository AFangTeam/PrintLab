#!/usr/bin/env python3
"""Build real CAD/Blender artifacts; dimensions are mm, GLB and Blender use metres."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import subprocess
import sys
from datetime import datetime, timezone


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blender_worker(args):
    import bpy
    from mathutils import Vector
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    out = Path(args.output)
    if args.worker == 'build':
        namespace = runpy.run_path(args.source)
        params = json.loads(Path(args.params).read_text())
        result = namespace['build'](params)
        objects = [result] if isinstance(result, bpy.types.Object) else list(result)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.source).parent / 'model.blend'))
        bpy.ops.wm.stl_export(filepath=str(out / 'model.stl'), export_selected_objects=True,
                              global_scale=1000.0, apply_modifiers=True)
        bpy.ops.export_scene.gltf(filepath=str(out / 'model.glb'), export_format='GLB',
                                  use_selection=True, export_apply=True)
    else:
        bpy.ops.import_scene.gltf(filepath=str(out / 'model.glb'))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not meshes:
        raise ValueError('No mesh to render')
    points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    centre = (low + high) / 2
    extent = max(high - low)
    mat = bpy.data.materials.new('PrintLab warm clay')
    mat.diffuse_color = (0.53, 0.61, 0.53, 1)
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.studiolight_rotate_z = 0.35
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.display.shading.background_type = 'WORLD'
    scene.world.color = (0.82, 0.81, 0.77)
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    cam_data = bpy.data.cameras.new('Preview camera')
    cam = bpy.data.objects.new('Preview camera', cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = extent * 1.75
    preview = Path(args.preview)
    preview.mkdir(parents=True, exist_ok=True)
    for name, direction in [('cover', (1.5, -2, 1.6)), ('front', (0, -3, 0)),
                            ('right', (3, 0, 0)), ('top', (0, 0, 3))]:
        cam.location = centre + Vector(direction) * max(extent, 0.01)
        cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
        cam_data.clip_start = 0.00001
        cam_data.clip_end = 100
        scene.render.filepath = str(preview / (name + '.png'))
        bpy.ops.render.render(write_still=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project')
    p.add_argument('--revision', default='v001')
    p.add_argument('--engine', choices=['cadquery', 'blender'])
    p.add_argument('--worker', choices=['build', 'render'])
    p.add_argument('--source')
    p.add_argument('--params')
    p.add_argument('--output')
    p.add_argument('--preview')
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    args = p.parse_args(argv)
    if args.worker:
        blender_worker(args)
        return
    if not args.project or not args.engine or not __import__('re').fullmatch(r'v\d{3,}', args.revision):
        p.error('--project, --engine and a vNNN revision are required')
    root = Path(os.environ.get('PRINTLAB_ROOT', Path(__file__).resolve().parent.parent)).expanduser().resolve()
    project = Path(args.project).resolve()
    project.relative_to((root / 'Project').resolve())
    src = project / 'Design' / args.revision
    out = project / 'Exports' / args.revision
    preview = project / 'Preview' / args.revision
    if (out / 'build.json').exists():
        raise ValueError('Revision already built; create a new revision instead of overwriting')
    out.mkdir(parents=True, exist_ok=True)
    preview.mkdir(parents=True, exist_ok=True)
    config = json.loads((root / 'Runtime/config.json').read_text())
    blender = config.get('blender_path')
    if not blender or not Path(blender).is_file():
        raise ValueError('Blender is required for verified model previews')
    params = json.loads((src / 'params.json').read_text())
    inputs = {str(f.relative_to(src)): digest(f) for f in sorted(src.rglob('*'))
              if f.is_file() and f.suffix != '.blend' and '__pycache__' not in f.parts}
    version = {}
    if args.engine == 'cadquery':
        import cadquery as cq
        namespace = runpy.run_path(str(src / 'model.py'))
        model = namespace['build'](params)
        if not isinstance(model, (cq.Workplane, cq.Shape)):
            raise TypeError('CadQuery build(params) must return a Workplane or Shape')
        shape = model.val() if isinstance(model, cq.Workplane) else model
        if not shape.isValid():
            raise ValueError('Invalid CAD solid')
        cq.exporters.export(model, str(out / 'model.step'))
        cq.exporters.export(model, str(out / 'model.stl'), tolerance=0.025, angularTolerance=0.1)
        for name, direction in [('front',(0,-1,0)),('right',(1,0,0)),('top',(0,0,1))]:
            cq.exporters.export(model, str(preview / (name + '.svg')), opt={'projectionDir':direction,'showHidden':False})
        import trimesh
        mesh = trimesh.load(out / 'model.stl', force='mesh')
        presentation = mesh.copy()
        presentation.apply_scale(0.001)
        # STL/CAD is Z-up; glTF viewers and Blender's importer expect Y-up.
        presentation.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
        presentation.export(out / 'model.glb')
        version['cadquery'] = cq.__version__
        worker = 'render'
    else:
        worker = 'build'
    cmd = [blender, '--background', '--factory-startup', '--python-exit-code', '1',
           '--python', str(Path(__file__).resolve()), '--', '--worker', worker,
           '--source', str(src/'model.py'), '--params', str(src/'params.json'),
           '--output', str(out), '--preview', str(preview)]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    (preview / 'render.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError('Blender failed; see ' + str(preview / 'render.log'))
    after_inputs = {str(f.relative_to(src)): digest(f) for f in sorted(src.rglob('*'))
                    if f.is_file() and f.suffix != '.blend' and '__pycache__' not in f.parts}
    if after_inputs != inputs:
        raise RuntimeError('Design inputs changed during build; outputs are not verified. Rebuild a stable revision.')
    import numpy as np
    import trimesh
    mesh = trimesh.load(out / 'model.stl', force='mesh')
    checks = {'finite': bool(np.isfinite(mesh.vertices).all()), 'watertight': bool(mesh.is_watertight),
              'consistent_winding': bool(mesh.is_winding_consistent), 'positive_volume': bool(mesh.volume > 0),
              'nonzero_dimensions': bool((mesh.extents > 0).all()),
              'within_conservative_x2d_volume': bool((mesh.extents <= [235.5,256,256]).all())}
    expected = params.get('expected_dimensions_mm')
    if expected:
        checks['expected_dimensions'] = bool(np.allclose(mesh.extents, expected, atol=0.15))
    version['blender'] = subprocess.check_output([blender,'--version'],text=True).splitlines()[0]
    data = {'engine':args.engine,'revision':args.revision,'built_at':datetime.now(timezone.utc).isoformat(),
            'units':{'parameters':'mm','geometry_engine':'mm' if args.engine == 'cadquery' else 'm','stl':'mm','glb':'m'},'dimensions_mm':[round(float(x),3) for x in mesh.extents],
            'volume_mm3':round(float(mesh.volume),3),'checks':checks,'verified':all(checks.values()),
            'verification_limits':['No full wall-thickness or mechanical load analysis','Physical fit and print quality require a test print'],
            'tools':version,'source_sha256':{str(f.relative_to(project)):digest(f) for f in sorted(src.rglob('*')) if f.is_file() and '__pycache__' not in f.parts},
            'artifacts':{str(f.relative_to(project)):digest(f) for d in [out,preview] for f in sorted(d.glob('*')) if f.is_file()}}
    (out / 'build.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (preview / 'dimensions.json').write_text(json.dumps({'dimensions_mm':data['dimensions_mm'],'checks':checks},indent=2)+'\n')
    print(json.dumps(data,ensure_ascii=False))
    if not data['verified']:
        sys.exit(2)


if __name__ == '__main__':
    main()
