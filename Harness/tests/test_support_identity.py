import json
import zipfile
import pytest
from printlab import bambuddy,core


def sliced_route(tmp_path, settings, reported='GFS05'):
    base={'curr_bed_type':'Textured PEI Plate','physical_extruder_map':[1,0], 'filament_type':['PLA'], **settings}
    with zipfile.ZipFile(tmp_path/'job.3mf','w') as z:
        z.writestr('Metadata/project_settings.config',json.dumps(base))
        z.writestr('Metadata/slice_info.config','<config><plate><metadata key="index" value="1"/><nozzle id="0" extruder_id="2"/><filament id="1" group_id="0"/></plate></config>')
    job={'artifact':'job.3mf','plate':1,'requested_bed_type':'Textured PEI Plate','mapping':{'ams_mapping':[255],'extruder_mapping':[0]}}
    status={'ams':[], 'vt_tray':[{'id':255,'tray_type':'PLA','tray_info_idx':reported}]}
    return job,status


def test_official_support_inheriting_pla_is_accepted_with_exact_id(tmp_path):
    job,status=sliced_route(tmp_path,{'filament_id':['GFS05'],'filament_is_support':['1']})
    bambuddy.validate_slice_route(tmp_path,job,status)
    assert status['vt_tray'][0]['tray_type']=='PLA'


@pytest.mark.parametrize('settings,reported',[
    ({'filament_id':['GFL99'],'filament_is_support':['0']},'GFS05'),
    ({'filament_id':['GFS05'],'filament_is_support':['1']},'GFL99'),
    ({'filament_id':['GFS05'],'filament_is_support':['1']},None),
    ({'filament_is_support':['1']},'GFS05'),
    ({'filament_id':['GFS05'],'filament_is_support':['0']},'GFS05'),
])
def test_ordinary_pla_or_unknown_support_identity_cannot_pass(tmp_path,settings,reported):
    job,status=sliced_route(tmp_path,settings,reported)
    with pytest.raises(core.WorkflowError,match='[Ss]upport'):
        bambuddy.validate_slice_route(tmp_path,job,status)


def test_sanitizer_preserves_nonsecret_material_preset_identity():
    raw={'vt_tray':[{'id':255,'tray_info_idx':'GFS05','tray_type':'PLA','tag_uid':'private','tray_uuid':'private'}]}
    tray=bambuddy.sanitize_device(raw)['vt_tray'][0]
    assert tray['tray_info_idx']=='GFS05'
    assert 'tag_uid' not in tray and 'tray_uuid' not in tray


def test_studio_exported_plural_ids_use_the_requested_filament_index():
    settings = {'filament_ids': ['GFA01', 'GFS05'], 'filament_is_support': ['0', '1']}
    bambuddy.validate_support_profile_identity(settings, {'tray_info_idx': 'GFS05'}, 1)
    with pytest.raises(ValueError, match='Support'):
        bambuddy.validate_support_profile_identity(settings, {'tray_info_idx': 'GFS02'}, 1)
    with pytest.raises(ValueError, match='Support'):
        bambuddy.validate_support_profile_identity(settings, {'tray_info_idx': 'GFS05'}, 0)


def test_conflicting_identity_fields_remain_blocked():
    settings = {'filament_ids': ['GFS05'], 'filament_id': ['GFS02'], 'filament_is_support': ['1']}
    with pytest.raises(ValueError, match='conflict'):
        bambuddy.validate_support_profile_identity(settings, {'tray_info_idx': 'GFS05'}, 0)


def test_gfs05_ams_rfid_family_alias_requires_exact_support_identity(tmp_path):
    job, status = sliced_route(tmp_path, {'filament_ids': ['GFS05'], 'filament_is_support': ['1']})
    status['vt_tray'][0]['tray_type'] = 'PLA-S'
    bambuddy.validate_slice_route(tmp_path, job, status)
    status['vt_tray'][0]['tray_info_idx'] = 'GFS02'
    with pytest.raises(core.WorkflowError, match='Support'):
        bambuddy.validate_slice_route(tmp_path, job, status)


def test_ordinary_pla_cannot_use_pla_s_alias(tmp_path):
    job, status = sliced_route(tmp_path, {'filament_ids': ['GFA01'], 'filament_is_support': ['0']}, 'GFA01')
    status['vt_tray'][0]['tray_type'] = 'PLA-S'
    with pytest.raises(core.WorkflowError, match='Loaded material'):
        bambuddy.validate_slice_route(tmp_path, job, status)


def sparse_studio_route(tmp_path):
    settings = {'curr_bed_type': 'Textured PEI Plate', 'physical_extruder_map': [1, 0],
                'filament_type': ['PLA'] * 9, 'filament_ids': ['GFA01'] * 8 + ['GFS05'],
                'filament_is_support': ['0'] * 8 + ['1']}
    settings['filament_type'][2] = 'PETG'
    with zipfile.ZipFile(tmp_path / 'job.3mf', 'w') as z:
        z.writestr('Metadata/project_settings.config', json.dumps(settings))
        z.writestr('Metadata/slice_info.config', '<config><plate><metadata key="index" value="1"/>'
                   '<nozzle id="0" extruder_id="1"/><nozzle id="1" extruder_id="2"/>'
                   '<filament id="3" group_id="0"/><filament id="9" group_id="1"/></plate></config>')
    job = {'artifact': 'job.3mf', 'plate': 1, 'requested_bed_type': 'Textured PEI Plate',
           'mapping': {'transport': 'bambu_studio', 'project_filament_ids': [3, 9],
                       'ams_mapping': [254, 255], 'extruder_mapping': [1, 0]}}
    status = {'ams': [], 'vt_tray': [{'id': 254, 'tray_type': 'PETG', 'tray_info_idx': 'GFG03'},
                                    {'id': 255, 'tray_type': 'PLA', 'tray_info_idx': 'GFS05'}]}
    return job, status


def test_sparse_studio_ids_bind_actual_profile_and_support(tmp_path):
    job, status = sparse_studio_route(tmp_path)
    bambuddy.validate_slice_route(tmp_path, job, status)
    status['vt_tray'][1]['tray_info_idx'] = 'GFS02'
    with pytest.raises(core.WorkflowError, match='Support'):
        bambuddy.validate_slice_route(tmp_path, job, status)


@pytest.mark.parametrize('ids', [[1, 2], [3], [3, 3], [9, 3], [3, 10], [3, True]])
def test_sparse_mapping_rejects_missing_reversed_and_invalid_ids(tmp_path, ids):
    job, status = sparse_studio_route(tmp_path)
    job['mapping']['project_filament_ids'] = ids
    with pytest.raises(core.WorkflowError):
        bambuddy.validate_slice_route(tmp_path, job, status)


def test_sparse_mapping_cannot_enable_native_dispatch(tmp_path):
    job, status = sparse_studio_route(tmp_path)
    job['mapping']['transport'] = 'bambu_native'
    with pytest.raises(core.WorkflowError, match='official Studio'):
        bambuddy.validate_slice_route(tmp_path, job, status)
