"""Export a Bambu Studio project from a reviewed geometry-only 3MF.

The controlled core file remains the slicer's trusted input. This separate
artifact is for opening/editing in Studio; it is never a print approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from . import core, three_mf


def inspect(path: Path, filament_count: int | None = None) -> dict:
    """Reject the geometry-only package that triggers Studio's config warning."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            required = {'3D/3dmodel.model', 'Metadata/model_settings.config',
                        'Metadata/project_settings.config'}
            if not required <= names:
                raise core.WorkflowError('3MF lacks a complete Bambu Studio project configuration')
            if any(name.endswith('.gcode') for name in names):
                raise core.WorkflowError('An editable project must not contain sliced G-code')
            settings = json.loads(z.read('Metadata/project_settings.config'))
            model = ET.fromstring(z.read('3D/3dmodel.model'))
            model_settings = ET.fromstring(z.read('Metadata/model_settings.config'))
            if not model.findall('.//{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}item'):
                raise core.WorkflowError('Native 3MF has no model build item')
            filaments = settings.get('filament_settings_id')
            if not isinstance(filaments, list) or not filaments:
                raise core.WorkflowError('Native 3MF has no filament presets')
            if filament_count is not None and len(filaments) != filament_count:
                raise core.WorkflowError('Native 3MF lost a filament assignment')
            colours = settings.get('filament_colour')
            if not isinstance(colours, list) or len(colours) != len(filaments):
                raise core.WorkflowError('Native 3MF has incomplete filament colours')
            assignments = []
            for obj in model_settings.findall('./object'):
                object_extruder = next((m.get('value') for m in obj.findall('./metadata')
                                        if m.get('key') == 'extruder'), None)
                parts = obj.findall('./part')
                for part in parts or [obj]:
                    extruder = next((m.get('value') for m in part.findall('./metadata')
                                     if m.get('key') == 'extruder'), object_extruder)
                    try:
                        assignments.append(int(extruder))
                    except (TypeError, ValueError):
                        raise core.WorkflowError('Native 3MF lost a valid part-to-filament assignment')
            if not assignments or any(x < 1 or x > len(filaments) for x in assignments):
                raise core.WorkflowError('Native 3MF lost a valid part-to-filament assignment')
            if 'X2D' not in str(settings.get('printer_model', '')).upper():
                raise core.WorkflowError('Native 3MF is not configured for X2D')
            return {'path': str(path), 'sha256': core.digest(path), 'printer_model': settings['printer_model'],
                    'bed_type': settings.get('curr_bed_type'), 'filaments': filaments,
                    'sliced': False, 'studio_project_config_present': True}
    except (zipfile.BadZipFile, KeyError, ET.ParseError, json.JSONDecodeError) as exc:
        raise core.WorkflowError('Invalid Bambu Studio project 3MF') from exc


def export(pid, revision, machine, process, filaments, bed_type):
    p = core.project_path(pid)
    revision = revision or core.read_json(p / 'project.json').get('current_revision')
    if not revision or not filaments:
        raise core.WorkflowError('Verified revision and filament profiles are required')
    from . import design
    design.require_if_configured(pid, "release", revision=revision)
    out_dir = p / 'Exports' / revision
    manifest = core.read_json(out_dir / 'build.json', {})
    if manifest.get('verified') is not True:
        raise core.WorkflowError('Export requires a verified model build')
    core.validate_build_lineage(p, revision, manifest)
    source = out_dir / 'model.3mf'
    if manifest.get('artifacts', {}).get(f'Exports/{revision}/model.3mf') != core.digest(source):
        raise core.WorkflowError('Core 3MF must match the verified build manifest')
    source_info = three_mf.inspect(source, len(filaments))
    profiles = [Path(x).resolve() for x in [machine, process, *filaments]]
    for path in profiles:
        data = core.read_json(path)
        if not isinstance(data, dict) or data.get('inherits') or data.get('include'):
            raise core.WorkflowError('Export requires complete resolved profiles')
    if 'X2D' not in str(core.read_json(profiles[0]).get('printer_model', '')).upper():
        raise core.WorkflowError('Machine profile must target X2D')
    slicer = Path(core.config().get('slicer_path', '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'))
    if not slicer.is_file():
        raise core.WorkflowError('Bambu Studio executable not available')
    output = out_dir / 'bambu-project.3mf'
    receipt = out_dir / 'bambu-project.json'
    if output.exists() or receipt.exists():
        raise core.WorkflowError('Native project already exists; create a new revision')
    temporary = out_dir / '.bambu-project-building.3mf'
    with core.lock(core.read_json(p / 'project.json')['id']):
        core.validate_build_lineage(p, revision, manifest)
        try:
            with tempfile.TemporaryDirectory(prefix='printlab-project-') as tmp:
                selected_process = Path(tmp) / 'process.json'
                data = core.read_json(profiles[1])
                data['curr_bed_type'] = bed_type
                core.write_json(selected_process, data)
                command = [str(slicer), '--load-settings', ';'.join(map(str, [profiles[0], selected_process])),
                           '--load-filaments', ';'.join(map(str, profiles[2:])),
                           '--export-3mf', str(temporary), str(source)]
                run = subprocess.run(command, capture_output=True, text=True, timeout=300)
            if run.returncode or not temporary.is_file():
                raise core.WorkflowError('Bambu Studio could not export the full project')
            result = inspect(temporary, len(filaments))
            if result['bed_type'] != bed_type:
                raise core.WorkflowError('Bambu Studio did not preserve the selected build plate')
            core.validate_build_lineage(p, revision, manifest)
            temporary.rename(output)
            result['path'] = str(output)
            record = {'revision': revision, 'created_at': core.now(), 'source_sha256': core.digest(source),
                      'source_geometry': source_info, 'profiles': {str(f): core.digest(f) for f in profiles},
                      'slicer_sha256': core.digest(slicer), 'bed_type_override': bed_type, 'result': result,
                      'purpose': 'editable Bambu Studio project; not sliced or approved for printing'}
            core.write_json(receipt, record)
            return result
        finally:
            temporary.unlink(missing_ok=True)
