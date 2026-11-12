"""Project design facts derived from the user's shared workspace and inventory."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from . import bambuddy, core, workspace


CONTRACT = 'Review/manufacturing-context.json'
PROJECT_INPUTS = ('brief.md', 'decisions.md', 'Review/design-target.json')
DEVICE_FIELDS = {
    'model': ('model', 'model'),
    'nozzle_diameter_mm': ('nozzle_diameter_mm', 'nozzle_diameter_mm'),
    'nozzle_type': ('nozzle_type', 'nozzle_type'),
    'build_plate': ('build_plate_description', 'build_plate'),
    'owned_build_plates': ('owned_build_plates', 'owned_build_plates'),
    'printable_area': ('printable_area', 'printable_area'),
    'printable_height': ('printable_height', 'printable_height'),
    'feeding_description': ('feeding_description', 'feeding_description'),
    'ams_count': ('ams_count', 'ams_count'),
    'fts_installed': ('fts_installed', 'fts_installed'),
}


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _file(root, relative):
    path = core.safe_path(root, relative, require_file=False)
    return {'path': relative, 'sha256': core.digest(path) if path.is_file() else None}


def current(pid, inventory=None):
    project = core.project_path(pid)
    card_path = core.safe_path(core.ROOT, workspace.DOCUMENTS['device'], require_file=False)
    card = core.read_json(card_path, {})
    confirmed, installed = card.get('user_confirmed', {}), card.get('installed', {})
    official = card.get('official_profile', {})
    from .machine_profiles import model_id
    profile_matches = bool(official and model_id(official.get('capabilities', {}).get('printer_model')) ==
                           model_id(confirmed.get('model') or card.get('model')))
    device = {}
    for output, (confirmed_key, installed_key) in DEVICE_FIELDS.items():
        value = confirmed.get(confirmed_key)
        basis = 'user_confirmed'
        if value is None:
            value, basis = installed.get(installed_key), 'recorded_installation'
        if value is None and output == 'model':
            value, basis = card.get('model'), 'device_card'
        if value is None and profile_matches and output in {'printable_area', 'printable_height'}:
            value = official.get('capabilities', {}).get(output)
            basis = 'official_configuration'
        device[output] = {'value': value, 'basis': basis if value is not None else 'unknown',
                          'source': workspace.DOCUMENTS['device']}
    inventory = inventory if inventory is not None else bambuddy.inventory()
    owned = [{key: item.get(key) for key in ('id', 'brand', 'material', 'subtype', 'color_name',
              'rgba', 'material_number', 'storage_location', 'possible_duplicate_ids')}
             for item in inventory.get('items', []) if not item.get('archived_at')]
    owned.sort(key=lambda item: str(item.get('id')))
    cfg = workspace.connection()
    inputs = {name: _file(core.ROOT, workspace.DOCUMENTS[name]) for name in ('profile', 'taste', 'device')}
    inputs.update({name: _file(project, name) for name in PROJECT_INPUTS})
    material_source = {'state': inventory.get('state'), 'observed_at': inventory.get('updated_at'),
                       'sha256': _hash(owned) if inventory.get('state') == 'online' else None}
    missing = [key for key in ('model', 'nozzle_diameter_mm', 'build_plate', 'printable_area', 'printable_height')
               if device[key]['value'] is None]
    if inventory.get('state') != 'online':
        missing.append('owned_materials')
    profile_changed = any(not Path(row['path']).is_file() or core.digest(Path(row['path'])) != row['sha256']
                          for row in official.get('source_files', []))
    if profile_changed:
        missing.append('official_profile_changed')
    if official and not profile_matches:
        missing.append('official_profile_model_mismatch')
    return {'project_id': core.read_json(project / 'project.json')['id'], 'device': device,
            'target': {key: cfg[key] for key in ('printer_id', 'bambuddy_url')},
            'device_verification': card.get('verification_status', 'unconfigured'),
            'official_profile': official, 'official_profile_changed': profile_changed,
            'owned_materials': owned, 'material_source': material_source, 'inputs': inputs,
            'missing': missing, 'scope': 'Design planning facts; refresh live device and material routes before printing'}


def view(pid, inventory=None):
    path = core.safe_path(core.project_path(pid), CONTRACT, require_file=False)
    saved = core.read_json(path, None)
    live = current(pid, inventory)
    changed = []
    if saved:
        if live['official_profile_changed']:
            changed.append('official_profile_sources')
        for name, row in live['inputs'].items():
            if row != saved['facts']['inputs'].get(name):
                changed.append(name)
        if saved['facts']['target'] != live['target']:
            changed.append('target_printer')
        previous_materials = saved['facts']['material_source'].get('sha256')
        if live['material_source']['sha256'] is not None and previous_materials != live['material_source']['sha256']:
            changed.append('owned_materials')
    return {'status': 'not_recorded' if saved is None else 'needs_refresh' if changed else 'recorded',
            'snapshot_sha256': core.digest(path) if path.is_file() else None,
            'changed': changed, 'current': live, 'snapshot': saved,
            'material_refresh_available': live['material_source']['state'] == 'online'}


def capture(pid, source, expected_sha256, inventory=None):
    source = workspace.required_text(source, 'Design context source')
    project = core.project_path(pid)
    project_id = core.read_json(project / 'project.json')['id']
    with core.lock(project_id):
        path = core.safe_path(project, CONTRACT, require_file=False)
        workspace.check_version(path, expected_sha256)
        facts = current(pid, inventory)
        previous = core.read_json(path, {})
        # An unavailable service cannot erase the last observed inventory snapshot.
        if facts['material_source']['state'] != 'online' and previous.get('facts'):
            facts['owned_materials'] = previous['facts']['owned_materials']
            facts['material_source'] = {**previous['facts']['material_source'], 'state': 'last_known'}
        version = previous.get('version', 0) + 1
        record = {'schema_version': 1, 'version': version, 'captured_at': core.now(),
                  'source': source, 'facts': facts, 'previous_sha256': expected_sha256}
        if path.is_file():
            archive = project / 'Review/manufacturing-context-history' / f'{expected_sha256}.json'
            if not archive.exists():
                core.write_json(archive, previous)
        core.write_json(path, record)
        return {'path': CONTRACT, 'sha256': core.digest(path), 'record': record}


def build_envelope(pid):
    """Read the configured dimensional envelope without contacting a device."""
    facts = current(pid, {'state': 'unavailable', 'items': []})
    area = facts['device']['printable_area']['value']
    height = facts['device']['printable_height']['value']
    if area is None or height is None or facts['official_profile_changed']:
        return {'known': False, 'reason': '当前设备打印空间缺少有效来源，需在切片前核对'}
    try:
        points = [[float(n) for n in point.strip().split('x')] for point in area]
        if len(points) < 3 or any(len(point) != 2 or any(not math.isfinite(n) for n in point) for point in points):
            raise ValueError()
        dimensions = [max(point[i] for point in points) - min(point[i] for point in points) for i in (0, 1)]
        dimensions.append(float(height))
        if any(not math.isfinite(n) or n <= 0 for n in dimensions):
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        return {'known': False, 'reason': '设备打印空间格式无效，需要核对实际官方配置'}
    return {'known': True, 'dimensions_mm': dimensions, 'model': facts['device']['model']['value'],
            'source': facts['inputs']['device'],
            'scope': 'Axis-aligned envelope only; slicing checks placement, exclusion regions and the actual toolpath'}
