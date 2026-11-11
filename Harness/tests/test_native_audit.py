"""Independent audit regressions. Temporary files and synthetic clients only."""
import pytest
from printlab import core, bambuddy, native
from test_workflow import workspace, ready
from test_native import native_job

TASK='checked-01234567-0123-0123-0123-0123456789ab-Jtest'


def test_stale_secondary_task_name_cannot_override_current_main_task(workspace):
    _,jd=workspace
    job=native_job(workspace);job['state']='printing';core.write_json(jd/'job.json',job)
    core.write_json(jd/'dispatch.json',{'job_id':'Jtest','transport':'bambu_native','remote_task':TASK})
    class Device:
        def get(self,path):
            assert path=='printers/7/status'
            return {**ready(),'state':'FINISH','current_print':'a different job','subtask_name':TASK}
    result=native.reconcile('P001','Jtest',Device())
    assert result['matching_task'] is False
    assert core.read_json(jd/'job.json')['state']=='printing'


def test_old_queue_failure_cannot_overwrite_newer_current_native_attempt(workspace):
    p,jd=workspace
    job=core.read_json(jd/'job.json');job.update(state='printing',created_at='2026-10-25T10:00:00+00:00');core.write_json(jd/'job.json',job)
    core.write_json(jd/'dispatch.json',{'queue_id':99,'library_file_id':42})
    newer={**job,'id':'Jnew','state':'preparing','created_at':'2026-10-25T11:00:00+00:00'}
    core.write_json(p/'Print/Jnew/job.json',newer)
    project=core.read_json(p/'project.json');project.update(current_job_id='Jnew',status='preparing');core.write_json(p/'project.json',project)
    class Device:
        def get(self,path):
            if path=='queue/99':return {'id':99,'printer_id':7,'library_file_id':42,'status':'failed'}
            if path=='printers/7/status':return ready()
            raise AssertionError(path)
    bambuddy.reconcile('P001','Jtest',Device())
    assert core.read_json(jd/'job.json')['state']=='failed'
    assert core.read_json(p/'project.json')['current_job_id']=='Jnew'
    assert core.read_json(p/'project.json')['status']=='preparing'


def test_native_reader_io_error_stops_the_spawned_process_group(workspace,monkeypatch):
    _,jd=workspace
    job=native_job(workspace)
    (core.ROOT / 'Harness').mkdir(exist_ok=True)
    (core.ROOT / 'Harness/native-client.mjs').write_text('// Synthetic process fixture')
    class Process:
        pid=999999
        returncode=None
        def communicate(self,*args,**kwargs):raise OSError('Synthetic pipe failure')
        def poll(self):return None
    process=Process();stopped=[]
    monkeypatch.setattr(native.subprocess,'Popen',lambda *a,**k:process)
    monkeypatch.setattr(native.shutil,'which',lambda name:'/synthetic/node')
    monkeypatch.setattr(native,'_terminate_group',lambda p:stopped.append(p))
    with pytest.raises(Exception):native.run_client(jd,job,'print')
    assert stopped==[process]
