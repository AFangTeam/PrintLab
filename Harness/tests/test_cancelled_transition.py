import datetime as dt
import pytest
from printlab import core, cancelled_transition, bambuddy
from test_workflow import workspace, ready

REMOTE='checked-01234567-0123-0123-0123-0123456789ab-Jold'


def recorded(workspace):
    p,jd=workspace
    job=core.read_json(jd/'job.json')
    old=p/'Print/Jold'
    core.write_json(old/'job.json',{**job,'id':'Jold','state':'failed'})
    core.write_json(old/'dispatch.json',{'remote_task':REMOTE})
    core.write_json(old/'native-observation.json',{'at':core.now(),'matching_task':True,'fresh':True,'remote_task':REMOTE,'device':{'id':7,'current_print':REMOTE,'state':'FAILED','hms_errors':[]}})
    core.write_json(p/'Evidence/stop.json',{'structuredContent':{'status':'success','route':'bambu:///local','command':'stop'}})
    core.write_json(jd/'repair-lineage.json',{'repair_for':'Jold'})
    return cancelled_transition.register('P001','Jold','Evidence/stop.json')


def test_real_stop_receipt_required_and_record_is_immutable(workspace):
    p,jd=workspace;record=recorded(workspace)
    assert record['previous_task']==REMOTE
    with pytest.raises(core.WorkflowError,match='already recorded'):
        cancelled_transition.register('P001','Jold','Evidence/stop.json')
    core.write_json(p/'Evidence/pause.json',{'structuredContent':{'status':'success','route':'bambu:///local','command':'pause'}})
    with pytest.raises(core.WorkflowError,match='successful'):
        cancelled_transition.register('P001','Jold','Evidence/pause.json')


def test_only_exact_approved_replacement_has_failed_transition(workspace):
    p,jd=workspace;recorded(workspace)
    approval=core.approve('P001','Jtest','确认打印',True)
    proof=cancelled_transition.clearance(p,jd,core.read_json(jd/'job.json'),approval)
    assert proof['newJobId']=='Jtest' and proof['fileSha256']==core.digest(jd/'job.gcode.3mf')
    status={**ready(),'state':'FAILED','current_print':REMOTE,'hms_errors':[]}
    assert cancelled_transition.matches_live(status,proof)
    bambuddy.validate_ready(status,core.read_json(jd/'job.json')['mapping'],cleared_finished=True,cancelled_reprint=proof)
    for change in [{'current_print':'another'},{'hms_errors':[{'code':1}]},{'state':'RUNNING'},{'print_error':6}]:
        assert not cancelled_transition.matches_live({**status,**change},proof)


def test_expired_approval_or_changed_cancel_evidence_never_allows_failed(workspace):
    p,jd=workspace;recorded(workspace)
    approval=core.approve('P001','Jtest','确认打印',True);job=core.read_json(jd/'job.json')
    assert cancelled_transition.clearance(p,jd,job,None) is None
    expired={**approval,'approved_at':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=31)).isoformat()}
    assert cancelled_transition.clearance(p,jd,job,expired) is None
    core.write_json(p/'Evidence/stop.json',{'structuredContent':{'status':'success','command':'resume'}})
    with pytest.raises(core.WorkflowError,match='evidence changed'):
        cancelled_transition.clearance(p,jd,job,approval)


def test_wrong_cancelled_task_never_registers(workspace):
    p,jd=workspace;recorded(workspace)
    path=p/'Print/Jold/cancel-confirmation.json';path.unlink()
    observation=core.read_json(p/'Print/Jold/native-observation.json');observation['device']['current_print']='another'
    core.write_json(p/'Print/Jold/native-observation.json',observation)
    with pytest.raises(core.WorkflowError,match='matching FAILED'):
        cancelled_transition.register('P001','Jold','Evidence/stop.json')
