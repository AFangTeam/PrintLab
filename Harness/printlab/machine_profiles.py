"""Read the installed official Studio profiles and retain their exact provenance."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

from . import core, platforms, workspace


def single_nozzle_model(value):
    """Models whose single-nozzle official slices are covered by the offline matrix."""
    return model_id(value) in {'A1', 'A1 MINI', 'P1S', 'X1 CARBON'}


def model_id(value):
    name = str(value or '').strip().upper().removeprefix('BAMBU LAB ').strip()
    return {'X1C': 'X1 CARBON', 'A1MINI': 'A1 MINI'}.get(name, name)


def _resolver():
    spec = importlib.util.spec_from_file_location('printlab_profile_resolver',
        Path(__file__).parents[1] / 'resolve_bambu_profiles.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = platforms.profile_directory(core.config()) / 'BBL/machine'
    if not directory.is_dir():
        raise core.WorkflowError('Installed Bambu Studio machine profile directory is unavailable')
    return module.ProfileResolver(directory)


def list_profiles(model=None):
    resolver = _resolver()
    rows = []
    for path in sorted(set(resolver.files.values())):
        row = core.read_json(path)
        if row.get('instantiation') != 'true' or not row.get('printer_model'):
            continue
        if model and model_id(model) != model_id(row['printer_model']):
            continue
        rows.append({'name': row.get('name', path.stem), 'model': row['printer_model'],
                     'nozzle_diameter': row.get('nozzle_diameter'), 'path': str(path)})
    return rows


def read(name):
    resolver = _resolver()
    try:
        settings = resolver.resolve(name)
    except ValueError as exc:
        raise core.WorkflowError(str(exc)) from exc
    if settings.get('instantiation') != 'true' or not settings.get('printer_model'):
        raise core.WorkflowError('Choose an instantiated official machine profile')
    nozzles = settings.get('nozzle_diameter')
    try:
        diameters = [float(value) for value in nozzles]
        if not diameters or any(not math.isfinite(n) or n <= 0 for n in diameters):
            raise ValueError()
    except (TypeError, ValueError):
        raise core.WorkflowError('Official profile has invalid nozzle dimensions') from None
    return {'name': name, 'settings': settings, 'source_files': list(resolver.sources.values()),
            'observed_at': core.now(), 'source': 'Installed official Bambu Studio profiles'}


def for_settings(settings):
    model = settings.get('printer_model')
    try:
        nozzle = [float(value) for value in settings.get('nozzle_diameter', [])]
    except (TypeError, ValueError):
        raise core.WorkflowError('Machine nozzle dimensions are invalid') from None
    if not model or not nozzle:
        raise core.WorkflowError('Machine model and nozzle dimensions are required')
    candidates = []
    for row in list_profiles(model):
        resolved = read(row['name'])
        actual = [float(value) for value in resolved['settings']['nozzle_diameter']]
        if actual == nozzle:
            candidates.append(resolved)
    preferred = [row for row in candidates if row['name'] in
                 {settings.get('name'), settings.get('printer_settings_id')}]
    if len(preferred) == 1:
        return preferred[0]
    if len(candidates) != 1:
        raise core.WorkflowError('Official machine profile is missing or ambiguous for these nozzle dimensions')
    return candidates[0]


def adopt(name, expected_sha256):
    profile = read(name)
    with core.lock('shared-context'):
        path = core.safe_path(core.ROOT, workspace.DOCUMENTS['device'], require_file=False)
        workspace.check_version(path, expected_sha256)
        card = core.read_json(path, {})
        selected = card.get('user_confirmed', {}).get('model') or card.get('model')
        if not selected or model_id(selected) != model_id(profile['settings']['printer_model']):
            raise core.WorkflowError('Official profile must match the selected device model')
        keys = ('printer_model', 'nozzle_diameter', 'printable_area', 'printable_height',
                'bed_exclude_area', 'physical_extruder_map', 'extruder_type')
        card['official_profile'] = {key: value for key, value in profile.items() if key != 'settings'}
        card['official_profile']['capabilities'] = {key: profile['settings'].get(key) for key in keys}
        core.write_json(path, card)
        return workspace.document('device')
