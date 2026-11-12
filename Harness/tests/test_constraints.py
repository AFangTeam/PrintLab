import copy

import pytest

from printlab import bambuddy, constraints, core, workspace


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    monkeypatch.setattr(bambuddy, 'inventory', lambda: {'state': 'unavailable', 'items': []})
    project = core.new_project('用户的支架', brief='适配用户实测桌板，关键尺寸待确认')
    return project['id']


def inventory():
    return {'state': 'online', 'updated_at': core.now(), 'items': [
        {'id': 1, 'material': 'PLA', 'color_name': 'White', 'archived_at': None},
        {'id': 2, 'material': 'PETG', 'color_name': 'Black', 'archived_at': None},
        {'id': 3, 'material': 'ABS', 'archived_at': '2020-01-01'}]}


def test_old_project_context_reports_missing_facts_without_rewriting(project):
    context = core.context(project)
    facts = context['manufacturing_context']
    assert facts['status'] == 'not_recorded'
    assert 'nozzle_diameter_mm' in facts['current']['missing']
    assert not (core.project_path(project) / constraints.CONTRACT).exists()


def test_capture_sources_changes_cas_and_unloaded_inventory(project):
    workspace.update_device({'user_confirmed': {'model': 'A1', 'nozzle_diameter_mm': 0.4,
                             'build_plate_description': 'Textured PEI Plate'}}, 'User message', None)
    first = constraints.capture(project, 'Device and project interview', None, inventory())
    assert first['record']['facts']['device']['model']['value'] == 'A1'
    assert [item['id'] for item in first['record']['facts']['owned_materials']] == [1, 2]
    assert first['record']['facts']['device']['printable_height']['value'] is None
    assert constraints.view(project, inventory())['status'] == 'recorded'
    with pytest.raises(core.WorkflowError, match='changed'):
        constraints.capture(project, 'stale update', None, inventory())
    profile = workspace.document('profile')
    workspace.append_note('profile', '需要更牢固', 'User message', 'profile-1', profile['sha256'])
    changes = constraints.view(project, inventory())
    assert changes['status'] == 'needs_refresh' and 'profile' in changes['changed']
    second = constraints.capture(project, 'Apply updated preference', first['sha256'], inventory())
    assert second['record']['version'] == 2
    archive = core.project_path(project) / 'Review/manufacturing-context-history' / f"{first['sha256']}.json"
    assert core.read_json(archive) == first['record']


def test_offline_refresh_keeps_last_known_inventory(project):
    first = constraints.capture(project, 'observed inventory', None, inventory())
    second = constraints.capture(project, 'offline review', first['sha256'], {'state': 'unavailable', 'items': []})
    assert len(second['record']['facts']['owned_materials']) == 2
    assert second['record']['facts']['material_source']['state'] == 'last_known'
    changed = copy.deepcopy(inventory())
    changed['items'][0]['material'] = 'PETG'
    assert 'owned_materials' in constraints.view(project, changed)['changed']
    changed = copy.deepcopy(inventory())
    changed['items'][0]['remaining_weight'] = 500
    assert not constraints.view(project, changed)['changed']


def test_nonfinite_coordinate_cannot_produce_known_build_space(project):
    workspace.update_device({'user_confirmed': {'model': 'A1',
        'printable_area': ['0x0', '10x0', 'nanx10', '0x10'], 'printable_height': 20}}, 'Fixture', None)
    assert constraints.build_envelope(project)['known'] is False
