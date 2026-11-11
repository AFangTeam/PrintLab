"""Temporary filesystem fixtures only. No printer or external process execution."""
import datetime as dt
import json
from pathlib import Path
import time
import zipfile
import pytest
from printlab import core, confirmation, three_mf
from test_workflow import workspace

DEVICE={'state':'online','stale':False,'updated_at':'test','printer':{'ams':[{'id':0,'tray':[{'id':0,'tray_type':'PLA','tray_sub_brands':'PLA Basic'}]}]}}


def test_card_remembers_answers_and_structured_quote_needs_no_magic_phrase(workspace):
    p,jd=workspace
    device_path=core.ROOT/'Library/Devices/X2D/device.json'
    data=core.read_json(device_path);data['user_confirmed']['build_plate_description']='Textured PEI Plate';core.write_json(device_path,data)
    event=confirmation.record('P001','Jtest',{'plate_clear':True,'material_loaded':True},'已经清空装好','test-session-A')
    card=confirmation.card('P001','Jtest',DEVICE)
    assert card['known_plate_type']=='Textured PEI Plate'
    assert [v['key'] for v in card['missing']]==['print_authorized']
    event=confirmation.record('P001','Jtest',{'print_authorized':True},'就按这一份下发吧','test-session-B')
    approval=core.approve('P001','Jtest',confirmation_event_id=event['id'])
    assert approval['confirmation']=='就按这一份下发吧'
    assert approval['confirmation_facts']['plate_clear']['source']=='test-session-A'
    assert confirmation.card('P001','Jtest',DEVICE)['can_approve']
    assert not (jd/'dispatch.json').exists()


def test_confirmation_veto_after_old_event_revokes_existing_approval(workspace):
    p,jd=workspace
    event=confirmation.record('P001','Jtest',{'plate_clear':True,'print_authorized':True},'test approval','test')
    core.approve('P001','Jtest',confirmation_event_id=event['id'])
    confirmation.record('P001','Jtest',{'print_authorized':False},'先不要发','later-session')
    assert core.read_json(jd/'job.json')['state']=='awaiting_approval'
    assert core.read_json(jd/'approval.json')['revoked'] is True
    with pytest.raises(core.WorkflowError,match='authorization'):
        core.approve('P001','Jtest',confirmation_event_id=event['id'])


def test_stale_plate_fact_is_not_extended_by_new_print_approval(workspace):
    p,jd=workspace
    old=confirmation.record('P001','Jtest',{'plate_clear':True},'plate clear','test')
    path=jd/'Confirmations'/(old['id']+'.json')
    old['recorded_at']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=31)).isoformat();core.write_json(path,old)
    event=confirmation.record('P001','Jtest',{'print_authorized':True},'go ahead','test')
    with pytest.raises(core.WorkflowError,match='cleared-plate'):
        core.approve('P001','Jtest',confirmation_event_id=event['id'])
    assert 'plate_clear' in [r['key'] for r in confirmation.card('P001','Jtest',DEVICE)['missing']]


def test_new_attempt_is_current_and_dispatched_card_never_reasks(workspace):
    p,jd=workspace
    job=core.read_json(jd/'job.json');job.update(state='printing',created_at='2026-10-25T02:00:00Z');core.write_json(jd/'job.json',job)
    core.write_json(jd/'dispatch.json',{'job_id':'Jtest'})
    old=p/'Print/Jold';core.write_json(old/'job.json',{**job,'id':'Jold','state':'failed','created_at':'2026-10-25T01:00:00Z'})
    card=confirmation.card('P001',device=DEVICE)
    assert card['job_id']=='Jtest' and card['already_dispatched']
    assert not any(m['needs_user'] for m in card['missing'])
    assert core.detail('P001')['current_attempt']['id']=='Jtest'


def test_retry_copies_exact_sliced_bytes_no_approval_and_preserves_old(workspace):
    p,jd=workspace
    job=core.read_json(jd/'job.json');job['state']='failed';core.write_json(jd/'job.json',job)
    core.write_json(jd/'dispatch.json',{'state':'submitted','queue_id':4})
    original={f.name:f.read_bytes() for f in jd.iterdir() if f.is_file()}
    new=core.retry_job('P001','Jtest','Explicit earlier failure; prepare only')
    new_dir=core.job_path('P001',new['id'])
    assert new['state']=='awaiting_approval' and new['retry_of']['job_id']=='Jtest'
    assert (new_dir/new['artifact']).read_bytes()==(jd/job['artifact']).read_bytes()
    assert not (new_dir/'approval.json').exists() and not (new_dir/'dispatch.json').exists()
    assert {f.name:f.read_bytes() for f in jd.iterdir() if f.is_file()}==original


@pytest.mark.parametrize('state',['dispatch_unknown','printing','preparing','paused','submitted','awaiting_approval'])
def test_retry_rejects_active_or_uncertain_attempt(workspace,state):
    p,jd=workspace;job=core.read_json(jd/'job.json');job['state']=state;core.write_json(jd/'job.json',job)
    with pytest.raises(core.WorkflowError,match='Only an explicitly'):
        core.retry_job('P001','Jtest','must not create')
    assert len(list((p/'Print').glob('*/job.json')))==1


def controlled(path,extra=None,paint=False):
    vertices='<vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/><vertex x="0" y="10" z="0"/><vertex x="0" y="0" z="10"/>'
    triangles=''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"'+(' p1="0"' if paint else '')+'/>' for a,b,c in [(0,2,1),(0,1,3),(0,3,2),(1,2,3)])
    objects=''.join(f'<object id="{i}" type="model"><mesh><vertices>{vertices}</vertices><triangles>{triangles}</triangles></mesh></object>' for i in [1,2])
    model=f'<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="millimeter"><resources>{objects}</resources><build><item objectid="1"/><item objectid="2" transform="1 0 0 0 1 0 0 0 1 20 0 0"/></build></model>'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('_rels/.rels','<Relationships><Relationship Target="/3D/3dmodel.model"/></Relationships>')
        z.writestr('3D/3dmodel.model',model)
        z.writestr('Metadata/model_settings.config','<config><object id="1"><metadata key="extruder" value="1"/></object><object id="2"><metadata key="extruder" value="2"/></object></config>')
        if extra:z.writestr(*extra)


def test_controlled_3mf_keeps_explicit_two_filament_objects(tmp_path):
    path=tmp_path/'model.3mf';controlled(path)
    result=three_mf.inspect(path,2)
    assert result['mesh_count']==2 and result['object_filament_assignments']=={'1':1,'2':2}
    with pytest.raises(core.WorkflowError,match='valid explicit'):
        three_mf.inspect(path,1)


@pytest.mark.parametrize('extra',[('Metadata/project_settings.config','{"machine_start_gcode":"M104 S999"}'),('Metadata/plate_1.gcode','M104 S999'),('../secret','bad')])
def test_controlled_3mf_rejects_author_process_settings_and_gcode(tmp_path,extra):
    path=tmp_path/'model.3mf';controlled(path,extra)
    with pytest.raises(core.WorkflowError,match='only reviewed'):
        three_mf.inspect(path,2)


def test_controlled_3mf_rejects_unsupported_triangle_painting(tmp_path):
    path=tmp_path/'model.3mf';controlled(path,paint=True)
    with pytest.raises(core.WorkflowError,match='painting'):
        three_mf.inspect(path,2)


def test_reapproval_retains_original_plate_confirmation_time(workspace):
    p,jd=workspace
    old=confirmation.record('P001','Jtest',{'plate_clear':True},'clear','session A')
    original=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=29)).isoformat()
    old['recorded_at']=original;core.write_json(jd/'Confirmations'/(old['id']+'.json'),old)
    event=confirmation.record('P001','Jtest',{'print_authorized':True},'proceed','session B')
    receipt=core.approve('P001','Jtest',confirmation_event_id=event['id'])
    assert receipt['plate_clear_confirmed_at']==original and receipt['approved_at']==original
    assert receipt['recorded_at']>original


def test_controlled_3mf_input_is_snapshotted_and_bound_without_author_settings(workspace,monkeypatch):
    p,jd=workspace
    model=p/'Exports/v001/model.3mf';controlled(model)
    manifest={'verified':True,'checks':{'watertight':True},
              'source_sha256':{f.relative_to(p).as_posix():core.digest(f) for f in (p/'Design/v001').iterdir()},
              'artifacts':{f'Exports/v001/{f.name}':core.digest(f) for f in [p/'Exports/v001/model.stl',model]}}
    core.write_json(p/'Exports/v001/build.json',manifest)
    machine=p/'machine.json';process=p/'process.json';filament=p/'filament.json';slicer=p/'fake-slicer'
    from printlab import slicer_guard
    core.write_json(machine,{'printer_model':'Bambu Lab X2D',**slicer_guard.official_templates(),'printable_area':[]})
    core.write_json(process,{});core.write_json(filament,{'filament_type':['PLA']});slicer.write_text('never executed')
    cfg=core.read_json(core.ROOT/'Runtime/config.json');cfg['slicer_path']=str(slicer);core.write_json(core.ROOT/'Runtime/config.json',cfg)
    class Result:
        returncode=0;stdout='synthetic slicer';stderr=''
    def fake_run(command,**kwargs):
        assert Path(command[-1]).parts[-2:] == ('Input', 'model.3mf')
        assert Path(command[-1]).read_bytes()==model.read_bytes()
        out=Path(command[command.index('--export-3mf')+1])
        with zipfile.ZipFile(jd/'job.gcode.3mf') as old, zipfile.ZipFile(out,'w') as new:
            for name in old.namelist():
                value=old.read(name)
                if name=='Metadata/slice_info.config':
                    value=value.replace(b'<filament id="1" group_id="0"/>',b'<filament id="1" group_id="0" used_g="2"/><filament id="2" group_id="0" used_g="2"/>')
                elif name == 'Metadata/project_settings.config':
                    settings = json.loads(value)
                    for field in ('filament_type', 'filament_map', 'nozzle_temperature_initial_layer', 'nozzle_temperature'):
                        settings[field] = settings[field] * 2
                    value = json.dumps(settings).encode()
                elif name == 'Metadata/plate_1.gcode':
                    value += b'\nM620 S1A\nT1\nM621 S1A\nM109 S220\nG1 X2 E1\n'
                new.writestr(name,value)
        return Result()
    monkeypatch.setattr(core.subprocess,'run',fake_run)
    job=core.slice_project('P001',str(machine),str(process),[str(filament),str(filament)],mapping={'routing_verified':True,'ams_mapping':[0,1],'extruder_mapping':[0,0],'fts_installed':False},bed_type='Textured PEI Plate',input_3mf='Exports/v001/model.3mf')
    attempt=core.job_path('P001',job['id'])
    assert job['slice_input']['object_filament_assignments']=={'1':1,'2':2}
    assert job['input_hashes']=={'Input/model.3mf':core.digest(model)}
    core.job_fingerprint(p,attempt,job)
    (attempt/'Input/model.3mf').write_bytes(b'tampered')
    with pytest.raises(core.WorkflowError,match='snapshot changed'):
        core.job_fingerprint(p,attempt,job)


def test_retry_replaces_explicit_current_pointer_but_preserves_old_attempt(workspace):
    p,jd=workspace
    job=core.read_json(jd/'job.json');job['state']='failed';core.write_json(jd/'job.json',job)
    project=core.read_json(p/'project.json');project.update(current_job_id='Jtest',status='failed');core.write_json(p/'project.json',project)
    new=core.retry_job('P001','Jtest','Prepare new exact-byte attempt')
    assert core.read_json(p/'project.json')['current_job_id']==new['id']
    assert core.read_json(p/'project.json')['status']=='awaiting_approval'
    assert core.current_attempt(p)['id']==new['id'] and core.read_json(jd/'job.json')['state']=='failed'


@pytest.mark.parametrize('state',['running','staged_requires_reconciliation'])
def test_other_active_attempt_blocks_preparation(workspace,state):
    p,jd=workspace
    job=core.read_json(jd/'job.json');job['state']='failed';core.write_json(jd/'job.json',job)
    core.write_json(p/'Print/Jactive/job.json',{**job,'id':'Jactive','state':state})
    with pytest.raises(core.WorkflowError,match='Another active'):
        core.retry_job('P001','Jtest','blocked')


def test_controlled_3mf_rejects_material_partition_lost_by_slicer(workspace):
    p,jd=workspace
    with pytest.raises(core.WorkflowError,match='material usage differs'):
        three_mf.validate_slice_output(jd/'job.gcode.3mf',{'object_filament_assignments':{'1':1,'2':2}})


def test_old_message_timestamp_cannot_be_replayed_as_fresh_confirmation(workspace):
    past=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1)).isoformat()
    event=confirmation.record('P001','Jtest',{'print_authorized':True,'plate_clear':True},'old quote','old thread',confirmed_at=past)
    with pytest.raises(core.WorkflowError,match='cleared-plate'):
        core.approve('P001','Jtest',confirmation_event_id=event['id'])


def test_retry_preserves_target_project_when_other_projects_follow(workspace,monkeypatch):
    p,jd=workspace
    original_project=core.read_json(p/'project.json')
    original_project.update(summary='target summary',latest_session='Sessions/target.md')
    core.write_json(p/'project.json',original_project)
    other=core.ROOT/'Project/P008-other'
    other_data={'id':'P008','name':'other','slug':'other','current_revision':None,'summary':'must not overwrite target'}
    core.write_json(other/'project.json',other_data)
    monkeypatch.setattr(core,'list_projects',lambda:[original_project,other_data])
    old=core.read_json(jd/'job.json');old['state']='failed';core.write_json(jd/'job.json',old)
    new=core.retry_job('P001','Jtest','repeat original after failure')
    actual=core.read_json(p/'project.json')
    for key,value in original_project.items():
        if key not in {'current_job_id','status','updated_at'}:assert actual[key]==value
    assert actual['current_job_id']==new['id']
    assert core.read_json(other/'project.json')==other_data
    assert core.job_fingerprint(p,core.job_path('P001',new['id']),new)
