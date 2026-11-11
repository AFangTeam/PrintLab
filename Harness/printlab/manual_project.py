"""Build a traceable manual-nozzle project from a verified Studio export.

This module only prepares geometry/settings. It never slices, approves or sends.
The caller must retain existing PrintLab lineage, job fingerprint, device and
sliced-G-code gates; preparation alone is not printing authorization.
"""
from __future__ import annotations
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from . import core, project3mf


def select_plate(files: dict, variant: str) -> tuple[dict, int]:
    """Select the reviewed v033 main plate without modifying any mesh payload.

    This is deliberately not an arbitrary object filtering interface. Source
    receipt/build verification is performed by prepare before calling it.
    """
    if variant == 'complete':
        return {}, 4
    if variant not in {'main-without-front', 'front-flat', 'front-flat-single'}:
        raise core.WorkflowError('Unsupported reviewed P009 plate variant')
    ns = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
    ET.register_namespace('', ns[1:-1])
    ET.register_namespace('p', 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06')
    ET.register_namespace('BambuStudio', 'http://schemas.bambulab.com/package/2021')
    model = ET.fromstring(files['3D/3dmodel.model'])
    settings = ET.fromstring(files['Metadata/model_settings.config'])
    build, resources = model.find(ns+'build'), model.find(ns+'resources')
    expected = {'2', '5', '7', '9'}
    if (build is None or resources is None or
            {n.get('objectid') for n in build} != expected or len(build) != 4 or
            {n.get('id') for n in resources} != expected or len(resources) != 4 or
            {n.get('id') for n in settings.findall('object')} != expected):
        raise core.WorkflowError('P009 subset source object identities changed')
    front = settings.find("object[@id='2']")
    if (front.find("metadata[@key='extruder']").get('value') != '2' or
            [n.get('id') for n in front.findall('part')] != ['1']):
        raise core.WorkflowError('P009 front identity or filament changed')
    plates = settings.findall('plate')
    if len(plates) != 1:
        raise core.WorkflowError('P009 subset requires exactly one plate')
    instances = plates[0].findall('model_instance')
    if (len(instances) != 4 or
            {n.find("metadata[@key='object_id']").get('value') for n in instances} != expected):
        raise core.WorkflowError('P009 subset plate instance identities changed')
    keep = {'2'} if variant in {'front-flat', 'front-flat-single'} else {'5', '7', '9'}
    for parent, attr in [(build, 'objectid'), (resources, 'id'), (settings, 'id')]:
        for node in list(parent):
            if node.get(attr) in expected - keep:
                parent.remove(node)
    for node in instances:
        if node.find("metadata[@key='object_id']").get('value') not in keep:
            plates[0].remove(node)
    if variant in {'front-flat', 'front-flat-single'}:
        # Reviewed v033 front is in local XZ. Rotate +90 X, then bed-align.
        import math
        mesh = ET.fromstring(files['3D/Objects/object_1.model'])
        ys = [float(v.get('y')) for v in mesh.iter(ns+'vertex')]
        if not ys or not all(math.isfinite(y) for y in ys):
            raise core.WorkflowError('Invalid front vertex coordinates')
        build[0].set('transform', f'1 0 0 0 0 1 0 -1 0 128 128 {-min(ys)}')
    return {'3D/3dmodel.model': ET.tostring(model, encoding='utf-8', xml_declaration=True),
            'Metadata/model_settings.config': ET.tostring(settings, encoding='utf-8', xml_declaration=True)}, len(keep)


def prepare(p: Path, revision: str, profiles: list[Path], mapping: dict, output: Path) -> dict:
    p = Path(p)
    out = p / 'Exports' / revision
    original = out / 'bambu-project.3mf'
    receipt = core.read_json(out / 'bambu-project.json', {})
    manifest = core.read_json(out / 'build.json', {})
    if manifest.get('verified') is not True:
        raise core.WorkflowError('Manual project requires verified build')
    core.validate_build_lineage(p, revision, manifest)
    if receipt.get('revision') != revision or receipt.get('source_sha256') != core.digest(out / 'model.3mf'):
        raise core.WorkflowError('Manual project source does not match export receipt')
    if receipt.get('result', {}).get('sha256') != core.digest(original):
        raise core.WorkflowError('Manual project export hash differs from receipt')
    expected = {str(Path(f).resolve()): core.digest(Path(f).resolve()) for f in profiles}
    if receipt.get('profiles') != expected:
        raise core.WorkflowError('Manual project profiles differ from export receipt')
    if receipt.get('slicer_sha256') != core.digest(Path(core.config()['slicer_path'])):
        raise core.WorkflowError('Manual project slicer differs from export receipt')
    if receipt.get('bed_type_override') != 'Textured PEI Plate':
        raise core.WorkflowError('Manual project plate type is not verified')
    single = mapping.get('plate_variant') == 'front-flat-single'
    expected_extruders = [1, 1, 1] if single else [1, 1, 0]
    expected_slots = [1, 1, 3] if single else [1, 2, 255]
    if mapping.get('extruder_mapping') != expected_extruders or mapping.get('ams_mapping') != expected_slots:
        raise core.WorkflowError('This guarded route requires exactly the verified X2D P009 material routing')
    if mapping.get('routing_verified') is not True or mapping.get('fts_installed') is not False:
        raise core.WorkflowError('Manual project requires explicitly verified direct routing')
    project3mf.inspect(original, 3)
    with zipfile.ZipFile(original) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any(n.lower().endswith('.gcode') for n in names):
            raise core.WorkflowError('Unexpected executable or duplicate project entry')
        files = {name: z.read(name) for name in names}
    variant = mapping.get('plate_variant', 'complete')
    selected, expected_objects = select_plate(files, variant)
    selected_files = {**files, **selected}
    settings = json.loads(files['Metadata/project_settings.config'])
    if settings.get('filament_ids') != ['GFA01', 'GFA01', 'GFS05'] or settings.get('filament_is_support') != ['0', '0', '1']:
        raise core.WorkflowError('Manual route filament identities are inconsistent')
    model = ET.fromstring(selected_files['Metadata/model_settings.config'])
    plates = model.findall('plate')
    if len(plates) != 1 or len(model.findall('object')) != expected_objects:
        raise core.WorkflowError('Unexpected plate or object count')
    for key, val in [('filament_map_mode', 'Manual'), ('filament_maps', '1 1 1' if single else '1 1 2'), ('filament_volume_maps', '0 0 0')]:
        matches = [m for m in plates[0].findall('metadata') if m.get('key') == key]
        if len(matches) > 1:
            raise core.WorkflowError('Duplicate plate mapping metadata')
        element = matches[0] if matches else ET.SubElement(plates[0], 'metadata', key=key)
        element.set('value', val)
    settings.update(extruder_nozzle_stats=['Standard#1', 'Standard#1'], extruder_nozzle_stats_new=['Standard#1', 'Standard#1'])
    if variant in {'front-flat', 'front-flat-single'}:
        settings['support_filament'] = '2'
    overrides = {'support_filament': '2'} if variant in {'front-flat', 'front-flat-single'} else {}
    if single:
        overrides.update(filament_map=['1', '1', '1'], filament_map_mode='Manual', flush_into_support='0')
        settings.update(overrides)
    replacements = {**selected, 'Metadata/model_settings.config': ET.tostring(model, encoding='utf-8', xml_declaration=True),
                    'Metadata/project_settings.config': json.dumps(settings, ensure_ascii=False).encode()}
    output = Path(output)
    if output.exists():
        raise core.WorkflowError('Refusing to overwrite derived project')
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, replacements.get(name, data))
    with zipfile.ZipFile(output) as z:
        if any(z.read(name) != data for name, data in files.items() if name not in replacements):
            raise core.WorkflowError('Unexpected project content change')
    project3mf.inspect(output, 3)
    return {'source_sha256': core.digest(original), 'derived_sha256': core.digest(output),
            'changed_entries': sorted(replacements), 'model_payload_unchanged': True,
            'expected_objects': expected_objects, 'plate_variant': variant,
            'selected_source_object_ids': ['2'] if variant in {'front-flat', 'front-flat-single'} else ['5', '7', '9'] if variant == 'main-without-front' else ['2', '5', '7', '9'],
            'selected_object_filament_assignments': {'2': 2} if variant in {'front-flat', 'front-flat-single'} else None,
            'process_overrides': overrides,
            'logical_route': [1, 1, 1] if single else [1, 1, 2], 'print_authorized': False}


def validate_output(path: Path, plate: int = 1, *, variant: str = 'complete') -> dict:
    """Reject incomplete, out-of-bounds or differently routed sliced plates."""
    if variant not in {'complete', 'main-without-front', 'front-flat', 'front-flat-single'}:
        raise core.WorkflowError('Unsupported reviewed P009 plate variant')
    expected_objects = 1 if variant in {'front-flat', 'front-flat-single'} else 3 if variant == 'main-without-front' else 4
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('Metadata/slice_info.config'))
        settings = json.loads(z.read('Metadata/project_settings.config'))
    matches = [x for x in root.findall('plate') if any(m.get('key') == 'index' and m.get('value') == str(plate) for m in x.findall('metadata'))]
    if len(matches) != 1:
        raise core.WorkflowError('Manual slice has no unique requested plate')
    selected = matches[0]
    meta = {x.get('key'): x.get('value') for x in selected.findall('metadata')}
    objects = selected.findall('object')
    if len(objects) != expected_objects or any(x.get('skipped') != 'false' for x in objects) or meta.get('outside') != 'false':
        raise core.WorkflowError('Manual slice is incomplete, skipped or outside plate')
    nozzle = {int(n.get('id')): int(n.get('extruder_id')) for n in selected.findall('nozzle')}
    rows = {int(f.get('id')): f for f in selected.findall('filament')}
    single = variant == 'front-flat-single'
    expected_route = {2: 1, 3: 1 if single else 2} if variant in {'front-flat', 'front-flat-single'} else {1: 1, 2: 1, 3: 2}
    if set(rows) != set(expected_route) or {i: nozzle[int(f.get('group_id'))] for i, f in rows.items()} != expected_route:
        raise core.WorkflowError('Manual slice actual nozzle route does not match verified route')
    if rows[3].get('tray_info_idx') != 'GFS05' or rows[3].get('used_for_object') != 'false' or settings.get('filament_is_support') != ['0', '0', '1']:
        raise core.WorkflowError('Manual slice support identity or usage is invalid')
    if any(float(rows[i].get('used_g', '0')) <= 0 for i in rows):
        raise core.WorkflowError('Manual slice has missing material usage')
    if variant in {'front-flat', 'front-flat-single'} and (settings.get('support_filament') != '2' or
            rows[2].get('tray_info_idx') != 'GFA01' or rows[2].get('used_for_object') != 'true'):
        raise core.WorkflowError('Front slice lost the green body or matching support skeleton')
    return {'object_count': expected_objects, 'plate_variant': variant, 'logical_nozzle_map': [1, 1, 1] if single else [1, 1, 2], 'support_id': 'GFS05', 'outside': False}
