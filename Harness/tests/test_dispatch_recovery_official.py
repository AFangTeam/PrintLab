"""No real device calls: recovery and official handoff regression cases."""
import datetime as dt
import json
import time
import zipfile
import pytest
from printlab import core, bambuddy, native, recovery, official
from test_workflow import workspace
from test_native import native_job, NativeDevice


def facts():
    old={'id':'Jold','state':'dispatch_unknown','printer_id':7}
    receipt={'job_id':'Jold','transport':'bambu_native','updated_at':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1)).isoformat(),
             'error':json.dumps({'status':'error','retryable':False,'tool':'print_3mf','message':'Bambu native local print failed (20): native_print result=-26'})}
    approval={'plate_clear':True,'approved_at':core.now()}
    live={'connected':True,'last_ams_update':time.time(),'state':'FINISH','hms_errors':[],
          'temperatures':{'bed_target':0,'nozzle_target':0},'current_print':'job.gcode'}
    return old,receipt,{'printer_id':7},approval,live,[]


def test_settles_only_explicit_signature_failure_after_subsequent_clear():
    assert recovery.settled_rejection(*facts())
    for index, changes in [(0,{'state':'submitted'}),(2,{'printer_id':8}),
        (3,{'revoked':True}),(3,{'approved_at':'2020-01-01T00:00:00+00:00'}),
        (4,{'state':'RUNNING'}),(4,{'connected':False}),(4,{'hms_errors':['error']}),
        (4,{'last_ams_update':time.time()-1000}),(4,{'temperatures':{'bed_target':55}}),
        (4,{'temperatures':{}}),(4,{'current_print':'checked-uuid-Jold'})]:
        args=list(facts());args[index].update(changes)
        assert not recovery.settled_rejection(*args)
    args=list(facts());args[5]=[{'status':'pending'}]
    assert not recovery.settled_rejection(*args)


@pytest.mark.parametrize('message',['timeout native_print result=-26','native_print result=0',
 'Bambu native local print failed (20): native_print result=-4020'])
def test_does_not_guess_from_other_errors(message):
    args=list(facts());error=json.loads(args[1]['error']);error['message']=message
    args[1]['error']=json.dumps(error)
    assert not recovery.settled_rejection(*args)


def test_mode_failure_does_not_create_uncertain_dispatch(workspace):
    native_job(workspace);core.approve('P001','Jtest','确认打印',True)
    dev=NativeDevice();get=dev.get
    def current(path):
        row=get(path)
        if path.startswith('printers/'):row['developer_mode']=False
        return row
    dev.get=current
    with pytest.raises(core.WorkflowError,match='non-developer mode'):
        native.submit('P001','Jtest',True,client_factory=lambda:dev,runner=lambda *a:pytest.fail('No transport probe'))
    assert not (workspace[1]/'dispatch.json').exists() and not dev.writes


def test_official_support_route_still_checks_the_physical_nozzle(workspace):
    from test_workflow import ready
    live=ready();live['vt_tray']=[{'id':255,'tray_type':'PLA'}]
    mapping={'transport':'bambu_studio','use_ams':True,'routing_verified':True,
             'fts_installed':False,'ams_mapping':[255],'extruder_mapping':[0]}
    bambuddy.validate_ready(live,mapping)
    with pytest.raises(core.WorkflowError,match='physical nozzle'):
        bambuddy.validate_ready(live,{**mapping,'extruder_mapping':[1]})


def test_history_recovery_preserves_error_and_never_resends(workspace):
    native_job(workspace)
    approval=core.approve('P001','Jtest','确认打印',True)
    p,jd=workspace
    old_dir=p/'Print/Jold';old_dir.mkdir()
    old,receipt,_,_,live,_=facts()
    old['project_id']='P001'
    core.write_json(old_dir/'job.json',old);core.write_json(old_dir/'dispatch.json',receipt)
    original=(old_dir/'dispatch.json').read_bytes()
    dev=NativeDevice();get=dev.get
    def current(path):
        result=get(path)
        if path.startswith('printers/'):result.update(live)
        return result
    dev.get=current
    result=recovery.before_submit(jd,core.read_json(jd/'job.json'),approval,dev)
    assert result==[{'job_id':'Jold','state':'dispatch_rejected'}]
    assert (old_dir/'dispatch.json').read_bytes()==original
    proof=core.read_json(old_dir/'dispatch-resolution.json')
    assert proof['execution_outcome']=='not_attributed' and proof['retry_authorized'] is False
    assert not dev.writes
    with pytest.raises(core.WorkflowError,match='explicitly failed'):
        core.retry_job('P001','Jold','Must not automatically duplicate the old geometry')


def test_unknown_timeout_remains_blocking_even_when_idle_and_plate_clear(workspace):
    native_job(workspace);approval=core.approve('P001','Jtest','确认打印',True)
    p,jd=workspace;old_dir=p/'Print/Jold';old_dir.mkdir()
    old,receipt,*_=facts();old['project_id']='P001';receipt['error']='Timed out; possible acceptance'
    core.write_json(old_dir/'job.json',old);core.write_json(old_dir/'dispatch.json',receipt)
    dev=NativeDevice()
    with pytest.raises(core.WorkflowError,match='requires reconciliation'):
        recovery.before_submit(jd,core.read_json(jd/'job.json'),approval,dev)
    assert core.read_json(old_dir/'job.json')['state']=='dispatch_unknown' and not dev.writes


def test_official_copy_is_same_gcode_unapproved_and_source_cannot_dispatch(workspace):
    native_job(workspace)
    old=core.read_json(workspace[1]/'job.json')
    with zipfile.ZipFile(workspace[1]/old['artifact'],'a') as z:
        z.writestr('3D/3dmodel.model','<model><resources><object/></resources><build><item/></build></model>')
        z.writestr('Metadata/model_settings.config','<config><object/><plate><model_instance/></plate></config>')
    old['artifact_sha256']=core.digest(workspace[1]/old['artifact']);core.write_json(workspace[1]/'job.json',old)
    job=official.prepare('P001','Jtest');jd=core.job_path('P001',job['id'])
    assert job['state']=='awaiting_approval' and not (jd/'approval.json').exists()
    assert core.read_json(workspace[1]/'job.json')['state']=='superseded'
    with zipfile.ZipFile(workspace[1]/old['artifact']) as a,zipfile.ZipFile(jd/job['artifact']) as b:
        assert a.read('Metadata/plate_1.gcode')==b.read('Metadata/plate_1.gcode')
        assert a.read('Metadata/project_settings.config')==b.read('Metadata/project_settings.config')
    core.approve('P001',job['id'],'确认打印',True)
    dev=NativeDevice()
    r=official.submit('P001',job['id'],True,client_factory=lambda:dev,inspector=lambda *a:{'ok':True})
    assert r['reserved'] and not r['executed'] and not dev.writes
    with pytest.raises(core.WorkflowError):
        official.submit('P001',job['id'],True,client_factory=lambda:dev)
    assert not official.reconcile('P001',job['id'],dev)['matching_task']
    dev.name=job['id']+'.gcode';dev.state='RUNNING'
    assert official.reconcile('P001',job['id'],dev)['matching_task']


def test_embedded_title_requires_new_archive_exact_artifact_and_ui_send(tmp_path):
    artifact = tmp_path/'job.3mf'
    with zipfile.ZipFile(artifact,'w') as z:
        z.writestr('3D/3dmodel.model','<model><metadata name="ProfileTitle">Original title</metadata></model>')
    job={'id':'Jtest','artifact':'job.3mf','artifact_sha256':core.digest(artifact),'printer_id':7,'plate':1}
    receipt={'artifact_sha256':job['artifact_sha256'],'created_at':'2026-11-02T07:38:40+00:00',
             'send_deadline':'2026-11-02T07:39:40+00:00'}
    live={'current_archive_id':24,'current_plate_id':1,'current_print':'Original title'}
    ui={'clicked_send_once':True,'task_name':'Jtest.gcode','at':'2026-11-02T07:39:00+00:00'}
    core.write_json(tmp_path/'official-ui-send.json',ui)
    archive={'id':24,'printer_id':7,'print_name':'Original title','started_at':'2026-11-02T07:39:12'}
    class ReadOnly:
        def get(self,path):
            assert path=='archives/24'
            return archive
    dev=ReadOnly()
    assert official.profile_title_archive_match(tmp_path,job,receipt,live,dev)['archive_id']==24
    terminal_live={**live,'current_archive_id':None,'current_plate_id':None,'state':'FAILED'}
    terminal_receipt={**receipt,'state':'observed','execution_binding':{
        'method':'embedded_profile_title_and_new_archive','archive_id':24}}
    archive['status']='failed'
    assert official.profile_title_archive_match(tmp_path,job,terminal_receipt,terminal_live,dev)['archive_id']==24
    assert official.profile_title_archive_match(tmp_path,job,receipt,terminal_live,dev) is None
    for field, value in [('printer_id',8),('started_at','2026-11-01T07:39:12'),
                         ('started_at','2026-11-02T07:40:12'),('print_name','Different task')]:
        original=archive[field];archive[field]=value
        assert official.profile_title_archive_match(tmp_path,job,receipt,live,dev) is None
        archive[field]=original
    core.write_json(tmp_path/'official-ui-send.json',{**ui,'clicked_send_once':False})
    assert official.profile_title_archive_match(tmp_path,job,receipt,live,dev) is None
    core.write_json(tmp_path/'official-ui-send.json',ui)
    artifact.write_bytes(b'Changed')
    assert official.profile_title_archive_match(tmp_path,job,receipt,live,dev) is None
