import pytest

from printlab import constraints, core, machine_profiles, slicer_guard, workspace


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    base = tmp_path / 'official/BBL/machine'
    core.write_json(tmp_path / 'Runtime/config.json', {'slicer_profiles_path': str(tmp_path / 'official')})
    core.write_json(base / 'base.json', {'name': 'base', 'printable_area': ['0x0', '10x0', '10x20', '0x20'],
        'printable_height': '30', 'nozzle_diameter': ['0.4'], 'physical_extruder_map': ['0'],
        **{key: 'official ' + key for key in slicer_guard.FIELDS}})
    core.write_json(base / 'Bambu Lab A1 0.4 nozzle.json', {'name': 'Bambu Lab A1 0.4 nozzle',
        'instantiation': 'true', 'inherits': 'base', 'printer_model': 'Bambu Lab A1'})
    return base


def test_inherited_capabilities_keep_sources_and_actual_nozzle_unknown(profiles):
    workspace.update_device({'user_confirmed': {'model': 'A1'}}, 'User', None)
    listed = machine_profiles.list_profiles('A1')
    assert len(listed) == 1
    first = workspace.document('device')
    result = machine_profiles.adopt(listed[0]['name'], first['sha256'])
    assert result['sha256'] != first['sha256']
    project = core.new_project('Fixture')
    facts = constraints.current(project['id'], {'state': 'unavailable'})
    assert facts['device']['printable_height']['value'] == '30'
    assert facts['device']['printable_height']['basis'] == 'official_configuration'
    assert facts['device']['nozzle_diameter_mm']['value'] is None
    assert len(facts['official_profile']['source_files']) == 2
    saved = constraints.capture(project['id'], 'Fixture', None, {'state': 'unavailable'})
    core.write_json(profiles / 'base.json', {'name': 'base', 'printable_height': '31'})
    assert constraints.view(project['id'], {'state': 'unavailable'})['changed'] == ['official_profile_sources']
    assert saved['record']['facts']['device']['printable_height']['value'] == '30'


def test_profile_cannot_supply_another_devices_dimensions(profiles):
    workspace.update_device({'model': 'P1S'}, 'User', None)
    with pytest.raises(core.WorkflowError, match='match'):
        machine_profiles.adopt('Bambu Lab A1 0.4 nozzle', workspace.document('device')['sha256'])


def test_machine_template_integrity_and_unambiguous_nozzle_choice(profiles):
    resolved = machine_profiles.read('Bambu Lab A1 0.4 nozzle')
    assert not slicer_guard.template_issues(resolved['settings'])
    changed = {**resolved['settings'], 'machine_start_gcode': 'simplified'}
    assert any('machine_start_gcode' in issue for issue in slicer_guard.template_issues(changed))
    with pytest.raises(core.WorkflowError, match='missing or ambiguous'):
        machine_profiles.for_settings({**resolved['settings'], 'nozzle_diameter': ['0.6']})
    assert machine_profiles.model_id('Bambu Lab X1 Carbon') == machine_profiles.model_id('X1C')


def test_unknown_machine_does_not_fall_back_to_x2d():
    assert slicer_guard.template_issues({}) == ['Machine profile must identify its target printer model']
