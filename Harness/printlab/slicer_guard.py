"""Offline official-template and executable startup checks for Bambu Studio slices."""
import importlib.util
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from . import core, platforms

FIELDS = ('machine_start_gcode', 'machine_end_gcode', 'change_filament_gcode',
          'layer_change_gcode', 'time_lapse_gcode')
OFFICIAL_MACHINE = None  # Optional override for isolated verification fixtures.


def official_templates():
    spec = importlib.util.spec_from_file_location('printlab_official_resolver', Path(__file__).parents[1] / 'resolve_bambu_profiles.py')
    resolver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolver)
    machine = OFFICIAL_MACHINE or platforms.profile_directory(core.config()) / 'BBL/machine/Bambu Lab X2D 0.4 nozzle.json'
    values = resolver.ProfileResolver(machine.parent).resolve(machine.stem)
    return {key: values[key] for key in FIELDS}


def template_issues(settings):
    from . import machine_profiles
    model = machine_profiles.model_id(settings.get('printer_model'))
    if not model:
        return ['Machine profile must identify its target printer model']
    if model == 'X2D':
        expected = official_templates()
    else:
        profile = machine_profiles.for_settings(settings)
        expected = {key: profile['settings'][key] for key in FIELDS}
    return [f'{model} official {key} differs or is missing' for key in FIELDS
            if settings.get(key) != expected[key]]


def commands(gcode):
    for index, line in enumerate(gcode.splitlines(), 1):
        text = re.sub(r'\([^)]*\)', '', line).split(';', 1)[0].strip()
        text = re.sub(r'^N\d+\s*', '', text, flags=re.I)
        match = re.match(r'^([GMT]\d+(?:\.\d+)?)(?=\s|[A-Z+-]|$)', text, re.I)
        if match:
            params = {key.upper(): float(value) for key, value in re.findall(r'([A-Z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))', text[match.end():], re.I)}
            yield index, match[1].upper(), params


def selected_temperature(settings, field, slot, count):
    """Read the active Standard variant from Bambu's per-filament arrays.

    Bambu Studio 02.08.02.61 serializes each filament's six nozzle variants
    consecutively in project_settings. Indexing the second array element as
    filament 2 reads an unused variant of filament 1 instead. For a compact
    one-value-per-filament archive, preserve the original direct indexing.
    Unknown variant layouts remain rejected by the caller.
    """
    raw = settings.get(field)
    if not isinstance(raw, list) or count < 1:
        return None
    if len(raw) == count:
        index = slot
    elif len(raw) % count == 0:
        variants = settings.get('filament_extruder_variant')
        nozzle_types = settings.get('nozzle_volume_type')
        if (not isinstance(variants, list) or len(variants) != len(raw)
                or not isinstance(nozzle_types, list) or not nozzle_types
                or any(v != 'Standard' for v in nozzle_types)):
            return None
        group_size = len(raw) // count
        group_start = slot * group_size
        # filament_map is 1-based logical extruder selection; extruder_type and
        # nozzle_volume_type are in that logical order, not firmware order.
        mapping, extruders = settings.get('filament_map'), settings.get('extruder_type')
        if mapping is not None or extruders is not None:
            try:
                logical = int(mapping[slot]) - 1
                if logical < 0 or str(logical + 1) != str(mapping[slot]):
                    return None
                variant = extruders[logical] + ' ' + nozzle_types[logical]
            except (IndexError, TypeError, ValueError):
                return None
        else:
            variant = 'Direct Drive Standard'  # legacy single-nozzle archives
        matches = [group_start + offset for offset, name in enumerate(variants[group_start:group_start+group_size])
                   if name == variant]
        if len(matches) != 1:
            return None
        index = matches[0]
    else:
        return None
    try:
        value = float(raw[index])
        return value if value > 0 else None
    except (IndexError, TypeError, ValueError):
        return None


def filament_nozzles(settings, count):
    if 'filament_map' not in settings and 'physical_extruder_map' not in settings:
        return [0] * count  # older single-nozzle archives
    logical, physical = settings.get('filament_map'), settings.get('physical_extruder_map')
    try:
        if len(logical) != count or sorted(map(int, physical)) != list(range(len(physical))):
            return None
        result = [int(physical[int(value) - 1]) for value in logical
                  if str(int(value)) == str(value) and 1 <= int(value) <= len(physical)]
        return result if len(result) == count else None
    except (TypeError, ValueError, IndexError):
        return None


def temperature_events(events, nozzles):
    """Executable temperatures, including X2D's official vendor load commands."""
    output, active = [], 0 if len(nozzles) == 1 else None
    pending = None
    for line, code, p in events:
        if code == 'M620':
            value = p.get('S')
            pending = int(value) if value in range(len(nozzles)) else None
        if re.fullmatch(r'T\d+', code):
            value = int(code[1:]); active = value if value < len(nozzles) else None
        if code == 'M621' and p.get('S') in range(len(nozzles)):
            active = int(p['S'])
        slot = active
        nozzle = None
        if slot is not None:
            nozzle = nozzles[slot]
        elif len(set(nozzles)) == 1:
            nozzle = nozzles[0]
        keys = []
        if code in {'M104', 'M109'}:
            keys = ['S', 'R']
            nozzle = p.get('T', p.get('N', nozzle))
            if 'T' in p or 'N' in p:
                slot = next((i for i, n in enumerate(nozzles) if n == nozzle), None)
        elif code == 'M620.10':
            # A0/A1 mean old/new material, not project filament positions.
            # The preceding M620 S selects the new material (possibly ID 8).
            slot = pending if p.get('A') == 1 else active if p.get('A') == 0 else None
            keys = ['T', 'P'] if slot is not None else []
            nozzle = nozzles[slot] if slot is not None else None
        elif code == 'M620.17':
            keys = ['S']; slot = p.get('L', active); nozzle = p.get('T')
        elif code in {'G150', 'G383', 'G383.3', 'M620.13', 'M620.1'}:
            keys = ['T']
        # M620.15 C is a cooling parameter, not a matching deposition target.
        for key in keys:
            if key in p:
                output.append({'line': line, 'command': code, 'target': p[key],
                               'filament_position': slot, 'nozzle': nozzle})
    return output


def audit(gcode, settings, active_filament_ids=None):
    issues = template_issues(settings)
    lines = gcode.splitlines()
    boundary = next((i for i, line in enumerate(lines, 1) if line.strip() == '; CHANGE_LAYER'), None)
    events = list(commands(gcode))
    if boundary is None:
        issues.append('Missing supported first-layer boundary; manual review required')
    start = [event for event in events if boundary is not None and event[0] < boundary]
    count = len(settings.get('filament_type', []))
    slots = list(range(count)) if active_filament_ids is None else [i - 1 for i in active_filament_ids]
    if not slots or len(set(slots)) != len(slots) or any(i < 0 or i >= count for i in slots):
        raise ValueError('Invalid active filament IDs in selected plate')
    for _, code, params in events:
        value = params.get('S')
        if code in {'M620', 'M621'} and value is not None and 0 <= value < count and value not in slots:
            issues.append('Executable filament load is missing from selected plate metadata')
    nozzles = filament_nozzles(settings, count)
    if nozzles is None:
        issues.append('Missing or ambiguous physical filament/nozzle mapping')
        nozzles = [None] * count
    temperatures = temperature_events(events, nozzles)
    for slot in slots:
        for field in ('nozzle_temperature_initial_layer', 'nozzle_temperature'):
            declared = selected_temperature(settings, field, slot, count)
            matches = [e for e in temperatures if e['target'] == declared
                       and e['filament_position'] in (None, slot)
                       and e['nozzle'] in (None, nozzles[slot])]
            if declared is None or declared <= 0 or not matches:
                issues.append(f'Declared {field} for filament {slot + 1} lacks an executable nozzle target')
    selected = None
    tool = None
    loads = []
    for line, code, params in start:
        slot = params.get('S')
        if code == 'M620' and slot is not None:
            selected = int(slot) if slot.is_integer() and 0 <= slot < count else None
            tool = None
        elif re.fullmatch(r'T\d+', code):
            tool = int(code[1:])
        elif code == 'M621' and selected is not None and slot == selected and tool == selected:
            loads.append({'filament_position': selected, 'line': line})
    if not loads:
        issues.append('Missing executable initial AMS M620 -> T -> M621 load sequence before first layer')
    active = loads[-1]['filament_position'] if loads else None
    targets = []
    if active is not None:
        target = selected_temperature(settings, 'nozzle_temperature_initial_layer', active, count)
        heat = [(e['line'], e['target']) for e in temperatures if boundary is not None
                and e['line'] < boundary and e['command'] in {'M104', 'M109'}
                and e['nozzle'] == nozzles[active]]
        waits = [(e['line'], e['target']) for e in temperatures if boundary is not None
                 and e['line'] < boundary and e['command'] == 'M109'
                 and e['nozzle'] == nozzles[active]]
        # A 245 target followed by 205 is not a valid 245 startup. Flush-only targets do not count.
        if target is None or target <= 0 or not heat or heat[-1][1] != target or not waits or waits[-1][1] != target:
            issues.append('Last executable nozzle target and wait before first layer must match its declared material temperature')
        targets = [{'line': line, 'target': value} for line, value in heat]
    return {'ok': not issues, 'issues': issues, 'first_layer_line': boundary, 'initial_ams_loads': loads,
            'startup_nozzle_targets': targets, 'scope': 'Offline command and official-template checks; physical feeding/extrusion remains unverified'}


def inspect_archive(path, plate=1):
    with zipfile.ZipFile(path) as archive:
        key = f'Metadata/plate_{plate}.gcode'
        for entry in (key, 'Metadata/project_settings.config'):
            if archive.getinfo(entry).file_size > 96 * 1024 * 1024:
                raise ValueError('Oversized sliced archive member')
        active = None
        gcode = archive.read(key).decode('utf-8')
        settings = json.loads(archive.read('Metadata/project_settings.config'))
        if 'Metadata/slice_info.config' in archive.namelist():
            try:
                root = ET.fromstring(archive.read('Metadata/slice_info.config'))
                plates = [p for p in root.findall('.//plate') if any(
                    m.get('key') == 'index' and m.get('value') == str(plate) for m in p.findall('metadata'))]
                if len(plates) != 1:
                    raise ValueError('Selected plate metadata is missing or ambiguous')
                active = [int(f.attrib['id']) for f in plates[0].findall('.//filament')]
                maps = [m.get('value') for m in plates[0].findall('metadata') if m.get('key') == 'filament_maps']
                if maps:
                    # Studio retains the global Auto preference in project
                    # settings while each plate and executable header carry
                    # the actual custom grouping. Require both to agree.
                    if len(maps) != 1:
                        raise ValueError('Ambiguous selected-plate filament mapping')
                    logical = maps[0].split()
                    headers = re.findall(r'^; filament_map = ([^\r\n]+)$', gcode, re.M)
                    if len(headers) != 1 or headers[0].split(',') != logical:
                        raise ValueError('Selected-plate and G-code filament mappings differ')
                    effective = {**settings, 'filament_map': logical}
                    if filament_nozzles(effective, len(settings.get('filament_type', []))) is None:
                        raise ValueError('Invalid selected-plate filament mapping')
                    groups = {int(n.get('id')): int(n.get('extruder_id')) for n in plates[0].findall('.//nozzle')}
                    for f in plates[0].findall('.//filament'):
                        if int(logical[int(f.get('id')) - 1]) != groups[int(f.get('group_id'))]:
                            raise ValueError('Selected-plate nozzle table differs from filament mapping')
                    settings = effective
            except ET.ParseError as exc:
                raise ValueError('Invalid slice metadata XML') from exc
        return audit(gcode, settings, active)


def assert_safe_archive(path, plate=1):
    from .core import WorkflowError
    try:
        result = inspect_archive(path, plate)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        raise WorkflowError('Bambu offline startup inspection failed: ' + str(exc)) from exc
    if not result['ok']:
        raise WorkflowError('Bambu offline startup rejected: ' + '; '.join(result['issues']))
    return result
