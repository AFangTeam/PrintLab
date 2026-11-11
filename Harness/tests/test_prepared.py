"""Synthetic prepared-shelf tests: no network and no physical printer writes."""
import copy
import json
import time
import zipfile

import pytest

from printlab import core, prepared, slicer_guard


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    core.write_json(tmp_path / 'Runtime/config.json', {'printer_id': 7})
    core.write_json(tmp_path / 'Library/Devices/X2D/device.json', {'user_confirmed': {
        'fts_installed': False, 'fts_confirmation_quote': 'Synthetic no FTS',
        'fts_confirmation_date': '2026-11-07', 'build_plate_description': 'Textured PEI Plate'}})
    core.new_project('Prepared fixture')
    p = core.project_path('P001')
    for d in ['Design/v001', 'Exports/v001', 'Preview/v001', 'Print/Jone/Profiles']:
        (p / d).mkdir(parents=True, exist_ok=True)
    (p / 'Design/v001/model.py').write_text('# synthetic, never print')
    (p / 'Exports/v001/model.stl').write_text('synthetic')
    (p / 'Preview/v001/cover.png').write_bytes(b'synthetic image')
    core.write_json(p / 'project.json', {**core.read_json(p / 'project.json'), 'current_revision': 'v001'})
    jd = p / 'Print/Jone'
    settings = {'curr_bed_type': 'Textured PEI Plate', 'physical_extruder_map': [1, 0],
                'filament_type': ['PETG'], 'filament_ids': ['GFG00'], 'filament_is_support': ['0']}
    def write_archive(rows=None, weight=50):
        rows = rows or '<filament id="1" group_id="0" type="PETG" tray_info_idx="GFG00" used_g="50" used_for_object="true"/>'
        with zipfile.ZipFile(jd / 'job.gcode.3mf', 'w') as z:
            z.writestr('Metadata/plate_1.gcode', '; SYNTHETIC NEVER EXECUTE\n')
            z.writestr('Metadata/project_settings.config', json.dumps(settings))
            z.writestr('Metadata/slice_info.config', f'<config><plate><metadata key="index" value="1"/><metadata key="weight" value="{weight}"/><metadata key="prediction" value="3600"/><nozzle id="0" extruder_id="1"/>{rows}</plate></config>')
    write_archive()
    j = {'id': 'Jone', 'project_id': 'P001', 'revision': 'v001', 'state': 'awaiting_approval',
         'plate': 1, 'artifact': 'job.gcode.3mf', 'artifact_sha256': core.digest(jd / 'job.gcode.3mf'),
         'source_hashes': core.revision_files(p, 'v001'), 'profile_hashes': {}, 'printer_id': 7,
         'requested_bed_type': 'Textured PEI Plate', 'curr_bed_type': 'Textured PEI Plate', 'trial_only': False,
         'mapping': {'transport': 'bambu_studio', 'use_ams': True, 'ams_mapping': [4], 'extruder_mapping': [1],
                     'routing_verified': True, 'fts_installed': False, 'material': 'PETG Basic', 'color': '97D700FF',
                     'filament_types': ['PETG'], 'filament_colours': ['97D700FF'], 'filament_series': ['PETG Basic'],
                     'inventory_ids': [16]}}
    core.write_json(jd / 'job.json', j)
    monkeypatch.setattr(slicer_guard, 'assert_safe_archive', lambda *args: None)
    live = {'id': 7, 'name': 'Synthetic', 'state': 'FINISH', 'connected': True, 'last_ams_update': time.time(),
            'hms_errors': [], 'awaiting_plate_clear': True, 'developer_mode': False,
            'temperatures': {'bed_target': 0, 'nozzle_target': 0, 'nozzle_2_target': 0},
            'ams_extruder_map': {'1': 1}, 'ams': [{'id': 1, 'tray': [{'id': 0, 'tray_type': 'PETG',
            'tray_info_idx': 'GFG00', 'tray_sub_brands': 'PETG Basic', 'tray_color': '97D700FF',
            'exists': True, 'state': 11, 'remain': 34}]}],
            'nozzles': [{'nozzle_type': 'HS01', 'nozzle_diameter': '.4'}, {'nozzle_type': 'HS01', 'nozzle_diameter': '.4'}]}
    assignments = [{'printer_id': 7, 'ams_id': 1, 'tray_id': 0, 'spool_id': 16}]
    spools = [{'id': 16, 'material': 'PETG', 'subtype': 'Basic', 'rgba': '97D700FF', 'label_weight': 1000,
               'weight_used': 0, 'remaining_weight': 1000}]
    class Client:
        def __init__(self):
            self.live = live
            self.assignments = assignments
            self.spools = spools
            self.queue = []
            self.gets = []
        def get(self, path):
            self.gets.append(path)
            if path == 'printers/7/status': return self.live
            if path == 'queue/': return self.queue
            if path == 'inventory/assignments': return self.assignments
            if path == 'inventory/spools': return self.spools
            raise AssertionError(path)
        def post(self, *a, **kw): raise AssertionError('No device writes allowed')
        def patch(self, *a, **kw): raise AssertionError('No device writes allowed')
    def inspector(*args):
        assert args[-1] == 'inspect'
        return {'ok': True, 'executed': False, 'inspection': {'nozzleDiameters': [.4, .4], 'nozzleTypes': ['hardened_steel', 'hardened_steel']}}
    return p, jd, j, Client(), inspector, write_archive, settings


def ready(setup):
    return prepared.check('P001', 'Jone', client=setup[3], inspector=setup[4])


def reg(setup):
    return prepared.register('P001', 'Jone', title='V1.1 左手柄', parts=['左手柄连滑轨'], note='仅准备；稍后由用户点击打印')


def test_registration_and_check_never_approve_or_send(setup):
    c = reg(setup)
    assert c['materials'][0]['slot_label'] == 'B1'
    assert c['materials'][0]['color'] == '97D700FF'
    assert c['preview_url'] == '/api/files/P001/Preview/v001/cover.png'
    assert c['live_checked'] is False
    report = ready(setup)
    assert report['ready'] is True
    assert report['executed'] is False
    assert report['plate_confirmation_required'] is True
    assert report['transport']['independent_dispatch_verified'] is False
    assert report['materials'][0]['estimated_available_grams'] == 340
    assert report['materials'][0]['reserve_grams'] == 10
    assert not (setup[1] / 'approval.json').exists()
    assert not (setup[1] / 'dispatch.json').exists()
    assert prepared.catalogue()['items'][0]['title'] == 'V1.1 左手柄'


def test_no_automatic_discovery_or_implicit_authorization(setup):
    assert prepared.catalogue()['items'] == []
    with pytest.raises(core.WorkflowError, match='尚未加入'):
        ready(setup)
    reg(setup)
    reg(setup)
    assert len(prepared.catalogue()['items']) == 1


@pytest.mark.parametrize('field,value,blocked', [
    ('connected', False, 'freshness'), ('last_ams_update', 1, 'freshness'),
    ('state', 'RUNNING', 'idle'), ('state', 'PAUSE', 'idle'), ('state', 'FAILED', 'idle'),
    ('hms_errors', [123], 'diagnostics'), ('id', 999, 'identity'),
    ('temperatures', {'bed_target': 60, 'nozzle_target': 0}, 'heaters'),
    ('temperatures', {}, 'heaters'), ('nozzles', [], 'nozzles'),
    ('nozzles', [{'nozzle_type': 'HS01', 'nozzle_diameter': '.6'}] * 2, 'nozzles')])
def test_live_unready_states_fail_closed(setup, field, value, blocked):
    reg(setup); setup[3].live[field] = value
    r = ready(setup)
    assert not r['ready']
    assert blocked in {x['id'] for x in r['blockers']}


def test_null_status_and_unreadable_inventory_fail_closed(setup):
    reg(setup); setup[3].live = None
    assert not ready(setup)['ready']
    assert 'connection' in {x['id'] for x in ready(setup)['blockers']}


def test_changed_source_is_not_ready(setup):
    reg(setup)
    (setup[0] / 'Design/v001/model.py').write_text('modified')
    report = ready(setup)
    assert 'files' in {x['id'] for x in report['blockers']}
    assert report['materials'][0]['estimated_available_grams'] == 340
    assert report['materials'][0]['sufficient'] is True
    assert {x['id']: x['status'] for x in report['checks']}['gcode'] == 'pass'


def test_old_component_can_be_shelved_but_not_released(setup):
    p = setup[0]
    core.write_json(p / 'project.json', {**core.read_json(p / 'project.json'), 'current_revision': 'v002'})
    c = reg(setup)
    assert c['state'] == 'stale'
    assert c['registration_issue']
    assert c['materials'][0]['required_grams'] == 50
    report = ready(setup)
    assert not report['ready']
    assert 'files' in {x['id'] for x in report['blockers']}
    assert report['materials'][0]['estimated_available_grams'] == 340
    assert report['materials'][0]['sufficient'] is True
    assert {x['id']: x['status'] for x in report['checks']}['gcode'] == 'pass'
    assert core.read_json(p / 'project.json')['current_revision'] == 'v002'
    assert not (setup[1] / 'approval.json').exists()


def test_stale_component_registration_still_checks_integrity(setup):
    p = setup[0]
    core.write_json(p / 'project.json', {**core.read_json(p / 'project.json'), 'current_revision': 'v002'})
    (p / 'Design/v001/model.py').write_text('modified')
    with pytest.raises(core.WorkflowError, match='旧版本源文件已变化'):
        reg(setup)


def test_changed_registered_artifact_cannot_report_quantity(setup):
    reg(setup)
    (setup[1] / 'job.gcode.3mf').write_bytes(b'corrupt')
    report = ready(setup)
    assert {'files', 'gcode', 'quantity'} <= {x['id'] for x in report['blockers']}
    assert report['materials'] == []


def test_unknown_send_or_queue_blocks(setup):
    reg(setup)
    setup[3].queue = [{'status': 'pending'}]
    assert 'queue' in {x['id'] for x in ready(setup)['blockers']}
    setup[3].queue = []
    other = setup[0] / 'Print/Jother/job.json'
    core.write_json(other, {'id': 'Jother', 'state': 'dispatch_unknown'})
    assert 'active_receipts' in {x['id'] for x in ready(setup)['blockers']}


def test_dispatched_job_cannot_register_or_check_again(setup):
    reg(setup)
    core.write_json(setup[1] / 'dispatch.json', {'state': 'unknown'})
    with pytest.raises(core.WorkflowError): reg(setup)
    assert not ready(setup)['ready']


@pytest.mark.parametrize('remain,estimate', [(0, 0), (-1, None), (None, None), (101, None), (5, 50)])
def test_insufficient_and_unknown_never_borrow_ledger_full_spool(setup, remain, estimate):
    reg(setup)
    setup[3].live['ams'][0]['tray'][0]['remain'] = remain
    r = ready(setup)
    assert not r['ready']
    assert r['materials'][0]['estimated_available_grams'] == estimate
    assert r['materials'][0]['sufficient'] is False


def test_wrong_color_or_moved_spool_does_not_remap(setup):
    reg(setup)
    setup[3].live['ams'][0]['tray'][0]['tray_color'] = 'FFFFFFFF'
    r = ready(setup)
    assert 'route' in {x['id'] for x in r['blockers']}
    assert not r['materials'][0]['sufficient']
    assert core.read_json(setup[1] / 'job.json')['mapping']['ams_mapping'] == [4]


def test_inventory_identity_and_label_weight_required(setup):
    reg(setup); setup[3].assignments[0]['spool_id'] = 99
    assert ready(setup)['materials'][0]['estimated_available_grams'] is None
    setup[3].assignments[0]['spool_id'] = 16; setup[3].spools[0]['label_weight'] = None
    assert ready(setup)['materials'][0]['estimated_available_grams'] is None


def test_per_slot_usage_aggregates_before_reserve(setup):
    bindings = [{'slot': 4, 'slot_label': 'B1', 'filament_id': i, 'required_grams': weight,
                 'material': 'PETG', 'series': 'PETG Basic', 'color': '97D700FF', 'extruder': 1,
                 'inventory_id': 16, 'profile_id': 'GFG00'} for i, weight in [(1, 180), (2, 140)]]
    r = prepared.quantity_checks(bindings, setup[3].live, setup[3].assignments, setup[3].spools)
    assert len(r) == 1
    assert r[0]['required_grams'] == 320
    assert r[0]['reserve_grams'] == 32
    assert r[0]['estimated_available_grams'] == 340
    assert not r[0]['sufficient']


def test_sparse_ids_and_source_color_do_not_override_approved_color(setup):
    p, jd, j, _c, _i, write_archive, settings = setup
    settings['filament_type'] = ['PLA', 'PETG']
    settings['filament_ids'] = ['GFA00', 'GFG00']
    settings['filament_is_support'] = ['0', '0']
    write_archive('<filament id="2" group_id="0" type="PETG" color="#FFFFFF" tray_info_idx="GFG00" used_g="50"/>')
    j['mapping']['project_filament_ids'] = [2]
    j['artifact_sha256'] = core.digest(jd / 'job.gcode.3mf')
    core.write_json(jd / 'job.json', j)
    c = reg(setup)
    assert c['materials'][0]['filament_id'] == 2
    assert c['materials'][0]['color'] == '97D700FF'
    assert ready(setup)['ready']


def test_per_material_usage_must_match_plate_total(setup):
    p, jd, j, _, _, write_archive, _ = setup
    write_archive(weight=100)
    j['artifact_sha256'] = core.digest(jd / 'job.gcode.3mf'); core.write_json(jd / 'job.json', j)
    with pytest.raises(core.WorkflowError, match='总用量不一致'): reg(setup)
