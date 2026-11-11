import json
import zipfile
from pathlib import Path
import pytest
from printlab import slicer_guard, core, bambuddy
from test_workflow import workspace, SimulatedBambuddy


def synthetic():
    templates = {key: 'test ' + key for key in slicer_guard.FIELDS}
    settings = {**templates, 'filament_type':['PETG'], 'nozzle_temperature_initial_layer':[245], 'nozzle_temperature':[245]}
    return templates, settings


def test_comments_and_change_template_never_count_as_startup_load(monkeypatch):
    templates, settings = synthetic()
    monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    gcode = '; machine_start_gcode = M620 S0A\\nT0\\nM621 S0A\n; M620 S0A\nM109 S245\n; CHANGE_LAYER\nG1 E1'
    result = slicer_guard.audit(gcode, settings)
    assert not result['ok'] and any('AMS' in issue for issue in result['issues'])


def test_selected_plate_ignores_unused_profiles_but_checks_every_active_temperature(monkeypatch, tmp_path):
    templates, settings = synthetic()
    monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    settings.update(filament_type=['PLA', 'PETG', 'PLA'], filament_map=[1, 1, 2],
                    physical_extruder_map=[1, 0], nozzle_temperature=[220, 245, 210],
                    nozzle_temperature_initial_layer=[220, 245, 210])
    gcode = 'M620 S1A\nT1\nM621 S1A\nM109 S245\n; CHANGE_LAYER\nG1 E1\nM620.17 T0 S210 L2'
    assert slicer_guard.audit(gcode, settings, [2, 3])['ok']
    assert not slicer_guard.audit(gcode, settings)['ok']
    assert not slicer_guard.audit(gcode.replace('S210', 'S205'), settings, [2, 3])['ok']
    assert not slicer_guard.audit(gcode, settings, [3])['ok']
    archive = tmp_path / 'sparse.3mf'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('Metadata/project_settings.config', json.dumps(settings))
        z.writestr('Metadata/plate_1.gcode', gcode)
        z.writestr('Metadata/slice_info.config', '<config><plate><metadata key="index" value="1"/>'
                   '<filament id="2"/><filament id="3"/></plate></config>')
    assert slicer_guard.assert_safe_archive(archive)['ok']
    with pytest.raises(core.WorkflowError):
        slicer_guard.assert_safe_archive(archive, 2)


@pytest.mark.parametrize('commands',[
    'M621 S0A\nT0\nM620 S0A',
    'M620 S0A\nT1\nM621 S0A',
    'M620 S0A\nT0\nM621 S1A',
    'M620 S255A\nT255\nM621 S255A',
])
def test_wrong_or_reordered_initial_load_is_rejected(monkeypatch, commands):
    templates, settings = synthetic();monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    assert not slicer_guard.audit(commands+'\nM109 S245\n; CHANGE_LAYER\nG1 E1', settings)['ok']


def test_earlier_correct_temperature_does_not_hide_later_wrong_start_target(monkeypatch):
    templates, settings = synthetic();monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    prefix='M620 S0A\nT0\nM621 S0A\nM109 S245\n'
    assert slicer_guard.audit(prefix+'; CHANGE_LAYER\nG1 E1',settings)['ok']
    assert not slicer_guard.audit(prefix+'M104 S205\n; CHANGE_LAYER\nG1 E1',settings)['ok']
    for key in slicer_guard.FIELDS:
        assert not slicer_guard.audit(prefix+'; CHANGE_LAYER\nG1 E1',{**settings,key:'simplified'})['ok']


def test_bambu_grouped_standard_temperatures_use_one_variant_per_filament(monkeypatch):
    templates, settings = synthetic()
    monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    settings.update(filament_type=['PETG', 'PETG'],
                    filament_extruder_variant=['Direct Drive Standard', 'Direct Drive High Flow',
                                                'Direct Drive E3D High Flow', 'Bowden Standard',
                                                'Bowden High Flow', 'Bowden E3D High Flow']*2,
                    nozzle_volume_type=['Standard', 'Standard'],
                    nozzle_temperature_initial_layer=[245]*12,
                    nozzle_temperature=[245, 250, 250, 250, 250, 250,
                                        245, 250, 250, 250, 250, 250])
    gcode='M620 S0A\nT0\nM621 S0A\nM109 S245\n; CHANGE_LAYER\nG1 E1\nM620.17 T0 S245 L1'
    assert slicer_guard.audit(gcode, settings)['ok']
    settings['filament_extruder_variant']=['unknown']*12
    assert not slicer_guard.audit(gcode, settings)['ok']


def test_original_incident_and_real_official_candidate_are_distinguished():
    root=Path(__file__).resolve().parents[2]
    old=root/'Project/P005-Beni闪电耳/Print/J20261025-183358-2ac5e7/job.gcode.3mf'
    candidate=root/'Runtime/evidence/native-profile-candidate-20261025-190330/isolated-lab/Project/P005-candidate-offline/Print/J20261025-190538-de848b/job.gcode.3mf'
    if not old.exists() or not candidate.exists():pytest.skip('Local real regression fixtures unavailable')
    bad=slicer_guard.inspect_archive(old);good=slicer_guard.inspect_archive(candidate)
    assert not bad['ok'] and any('AMS' in issue for issue in bad['issues'])
    assert good['ok'] and good['initial_ams_loads'][-1]['line']==944


def test_bad_startup_cannot_be_approved_or_dispatched_even_with_fresh_metadata(workspace):
    p,jd=workspace
    approval=core.approve('P001','Jtest','确认打印',True)
    artifact=jd/'job.gcode.3mf'
    with zipfile.ZipFile(artifact) as archive:members={name:archive.read(name) for name in archive.namelist()}
    members['Metadata/plate_1.gcode']=b'M109 S220\n; CHANGE_LAYER\nG1 E1'
    with zipfile.ZipFile(artifact,'w') as archive:
        for name,value in members.items():archive.writestr(name,value)
    job=core.read_json(jd/'job.json');job['artifact_sha256']=core.digest(artifact);core.write_json(jd/'job.json',job)
    approval['fingerprint']=core.job_fingerprint(p,jd,job);core.write_json(jd/'approval.json',approval)
    device=SimulatedBambuddy()
    with pytest.raises(core.WorkflowError,match='initial AMS'):
        bambuddy.submit('P001','Jtest',True,client_factory=lambda **kwargs:device)
    assert not device.writes and not (jd/'dispatch.json').exists()
    with pytest.raises(core.WorkflowError,match='initial AMS'):
        core.approve('P001','Jtest','确认打印',True)


def test_dual_nozzle_variants_and_inactive_precooling_do_not_mask_wrong_active_heat(monkeypatch):
    templates, settings = synthetic()
    monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    variants=['Direct Drive Standard','Direct Drive High Flow','Direct Drive E3D High Flow','Bowden Standard','Bowden High Flow','Bowden E3D High Flow']
    settings.update(filament_type=['PLA','PETG'],filament_map=['1','2'],physical_extruder_map=['1','0'],
                    extruder_type=['Direct Drive','Bowden'],nozzle_volume_type=['Standard','Standard'],
                    filament_extruder_variant=variants*2,nozzle_temperature_initial_layer=[220]*6+[245]*6,
                    nozzle_temperature=[220]*6+[245,250,250,250,250,250])
    assert slicer_guard.selected_temperature(settings,'nozzle_temperature',1,2)==250
    g='M620 S0A\nT0\nM621 S0A\nM109 S220\nM104 T0 S25 N0\n; CHANGE_LAYER\nG1 E1\nM620.17 T0 S245 L1\nM620 S1A\nM620.10 A1 T270 P250\n'
    assert slicer_guard.audit(g,settings)['ok']
    assert not slicer_guard.audit(g.replace('M109 S220','M109 S205'),settings)['ok']
    assert not slicer_guard.audit(g.replace('; CHANGE_LAYER','M104 T1 S205 N0\n; CHANGE_LAYER'),settings)['ok']
    assert not slicer_guard.audit(g.replace('P250','P205'),settings)['ok']
    assert not slicer_guard.audit(g.replace('M620 S0A','; M620 S0A'),settings)['ok']
    assert not slicer_guard.audit(g,{**settings,'filament_map':['1','3']})['ok']


def test_vendor_new_material_temperature_follows_pending_material_not_a_index():
    g='M620 S4A\nM620.10 A1 T270 P245\nT4\nM621 S4A\nM620 S8A\nM620.10 A0 T270 P245\nM620.10 A1 T230 P210'
    events=slicer_guard.temperature_events(list(slicer_guard.commands(g)),[1,1,0,1,1,1,1,1,0])
    assert [(e['filament_position'],e['nozzle']) for e in events if e['target']==210]==[(8,0)]
    assert all(e['filament_position']==4 for e in events if e['target']==245)
    assert not slicer_guard.temperature_events(list(slicer_guard.commands('M620.10 A1 P210')), [1,0])


def test_real_studio_custom_plate_mapping_and_temperatures():
    path=(Path(__file__).resolve().parents[2] / 'Project/P011-Apple50笔触表面改装/Review/dispatch-20261105/plate1-current.gcode.3mf')
    if not path.exists():pytest.skip('Local Studio custom plate fixture unavailable')
    assert slicer_guard.assert_safe_archive(path)['ok']


def test_plate_mapping_disagreement_is_rejected(tmp_path):
    path=(Path(__file__).resolve().parents[2] / 'Project/P011-Apple50笔触表面改装/Review/dispatch-20261105/plate1-current.gcode.3mf')
    if not path.exists():pytest.skip('Local Studio custom plate fixture unavailable')
    with zipfile.ZipFile(path) as src,zipfile.ZipFile(tmp_path/'bad.3mf','w') as dst:
        for n in src.namelist():
            value=src.read(n)
            if n=='Metadata/plate_1.gcode':value=value.replace(b'; filament_map = 2,1,2',b'; filament_map = 1,1,2')
            dst.writestr(n,value)
    with pytest.raises(core.WorkflowError,match='mappings differ'):
        slicer_guard.assert_safe_archive(tmp_path/'bad.3mf')
