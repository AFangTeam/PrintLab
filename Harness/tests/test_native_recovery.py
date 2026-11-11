"""State and subprocess recovery only; no printer transport in this module."""
import os
from pathlib import Path
import sys
import time
import pytest
from printlab import core, native, bambuddy
from test_workflow import workspace
from test_native import native_job, NativeDevice

TASK='checked-01234567-0123-0123-0123-0123456789ab-Jtest'


def setup_dispatch(workspace):
    job=native_job(workspace);job['state']='submitted'
    core.write_json(workspace[1]/'job.json',job)
    core.write_json(workspace[1]/'dispatch.json',{'job_id':'Jtest','transport':'bambu_native','state':'submitted'})
    return job


@pytest.mark.parametrize('raw,progress,layer,expected',[
    ('PREPARE',0,0,'preparing'),('HEATING',0,0,'preparing'),('RUNNING',0,0,'preparing'),
    ('RUNNING',1,1,'printing'),('RUNNING',None,None,'running'),('PAUSE',1,2,'paused'),
    ('FINISH',100,12,'awaiting_physical_review'),('FAILED',12,3,'failed')])
def test_precise_execution_phases(workspace,raw,progress,layer,expected):
    setup_dispatch(workspace)
    client=NativeDevice(raw,TASK)
    original=client.get
    def get(path):
        row=original(path)
        if path.startswith('printers/'):
            row.update(progress=progress,layer_num=layer)
        return row
    client.get=get
    result=native.reconcile('P001','Jtest',client)
    assert result['job_state']==expected
    assert result['fresh'] and result['matching_task']
    assert result['job']['reconciliation']['state']=='current'
    assert not client.writes


def test_pin_remote_uuid_and_stale_data_cannot_finish_job(workspace):
    setup_dispatch(workspace)
    native.reconcile('P001','Jtest',NativeDevice('PREPARE',TASK))
    other=TASK.replace('01234567','11234567',1)
    result=native.reconcile('P001','Jtest',NativeDevice('FINISH',other))
    assert result['job_state']=='preparing' and not result['matching_task']
    assert result['job']['reconciliation']['state']=='unmatched'
    client=NativeDevice('FINISH',TASK);get=client.get
    def stale(path):
        row=get(path);row['last_ams_update']=time.time()-1000;return row
    client.get=stale
    result=native.reconcile('P001','Jtest',client)
    assert result['job_state']=='preparing' and result['job']['reconciliation']['state']=='stale'


def test_restart_observer_finds_native_without_queue_id_and_never_writes_network(workspace):
    setup_dispatch(workspace)
    client=NativeDevice('PREPARE',TASK)
    result=bambuddy.reconcile_active_jobs(client_factory=lambda **kwargs:client)
    assert result==[{'project_id':'P001','job_id':'Jtest','state':'preparing'}]
    assert not client.writes
    result=bambuddy.reconcile_active_jobs(client_factory=lambda **kwargs:NativeDevice('PAUSE',TASK))
    assert result[0]['state']=='paused'


def test_timeout_terminates_child_process_group_and_cleans_environment(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'ROOT',tmp_path)
    monkeypatch.setattr(native.shutil,'which',lambda name:sys.executable)
    (tmp_path/'Harness').mkdir()
    jd=tmp_path/'job';jd.mkdir();(jd/'print.3mf').write_text('not a real print')
    escaped=tmp_path/'escaped'
    # Python stands in for Node and spawns a child that would write a marker if it survived.
    child="import time;from pathlib import Path;time.sleep(0.7);Path(%r).write_text('escaped')"%str(escaped)
    script="import os,subprocess,sys,time\nassert 'NODE_OPTIONS' not in os.environ\nsubprocess.Popen([sys.executable,'-c',%r])\ntime.sleep(4)\n"%child
    (tmp_path/'Harness/native-client.mjs').write_text(script)
    monkeypatch.setenv('NODE_OPTIONS','--pretend-injected')
    job={'artifact':'print.3mf','artifact_sha256':'test','plate':1,'id':'Jtest','mapping':{'ams_mapping':[0]}}
    with pytest.raises(core.WorkflowError,match='process group'):
        native.run_client(jd,job,'check',timeout=0.2)
    time.sleep(0.8)
    assert not escaped.exists()
