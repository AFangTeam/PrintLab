"""No network: native dispatch guards, uncertain outcomes, and task attribution."""
import pytest
from printlab import core, bambuddy, native
from test_workflow import workspace, ready, SimulatedBambuddy


def native_job(workspace):
    _, jd = workspace
    job = core.read_json(jd / 'job.json')
    job['mapping'].update(transport='bambu_native', material='PLA Basic', color='FFFFFFFF')
    core.write_json(jd / 'job.json', job)
    return job


class NativeDevice(SimulatedBambuddy):
    def __init__(self, state='FINISH', name='previous job'):
        super().__init__(); self.state=state; self.name=name; self.empty=False
    def get(self, path):
        if path.startswith('printers/'):
            s=ready(); s.update(state=self.state, awaiting_plate_clear=True, current_print=self.name)
            s['ams'][0]['tray'][0].update(tray_color='FFFFFFFF',tray_sub_brands='PLA Basic',exists=not self.empty)
            return s
        return super().get(path)


def test_finished_requires_current_bound_approval(workspace):
    native_job(workspace)
    with pytest.raises(core.WorkflowError, match='approved'):
        native.submit('P001','Jtest',True,client_factory=lambda:NativeDevice(),runner=lambda *a:pytest.fail('must not dispatch'))
    core.approve('P001','Jtest','确认打印；板已清空',True)
    calls=[]
    result=native.submit('P001','Jtest',False,client_factory=lambda:NativeDevice(),runner=lambda *a:calls.append(a[2]))
    assert result['executed'] is False and calls==['check']
    assert not (workspace[1]/'dispatch.json').exists()


def test_empty_tray_and_wrong_colour_never_dispatch(workspace):
    native_job(workspace);core.approve('P001','Jtest','确认打印；板已清空',True)
    d=NativeDevice();d.empty=True
    with pytest.raises(core.WorkflowError,match='empty'):
        native.submit('P001','Jtest',True,client_factory=lambda:d,runner=lambda *a:pytest.fail('no runner'))
    job=core.read_json(workspace[1]/'job.json');job['mapping']['color']='D6001CFF';core.write_json(workspace[1]/'job.json',job)
    core.approve('P001','Jtest','确认打印；板已清空',True)
    with pytest.raises(core.WorkflowError,match='colour'):
        native.submit('P001','Jtest',True,client_factory=lambda:NativeDevice(),runner=lambda *a:pytest.fail('no runner'))


def test_timeout_is_durable_and_no_retry(workspace):
    native_job(workspace);core.approve('P001','Jtest','确认打印；板已清空',True)
    calls=[]
    def runner(jd,job,mode,approval=None):
        calls.append(mode)
        if mode=='print':
            assert core.read_json(jd/'dispatch.json')['state']=='start_requested'
            raise TimeoutError('unknown')
        return {'ok':True}
    with pytest.raises(core.WorkflowError,match='reconciliation'):
        native.submit('P001','Jtest',True,client_factory=lambda:NativeDevice(),runner=runner)
    assert core.read_json(workspace[1]/'job.json')['state']=='dispatch_unknown'
    with pytest.raises(core.WorkflowError):
        native.submit('P001','Jtest',True,client_factory=lambda:NativeDevice(),runner=runner)
    assert calls==['check','print']


def test_unrelated_finished_job_is_not_completion(workspace):
    job=native_job(workspace);job['state']='submitted';core.write_json(workspace[1]/'job.json',job)
    core.write_json(workspace[1]/'dispatch.json',{'job_id':'Jtest','transport':'bambu_native'})
    r=native.reconcile('P001','Jtest',NativeDevice())
    assert not r['matching_task'] and r['job_state']=='submitted'
    r=native.reconcile('P001','Jtest',NativeDevice('RUNNING','checked-01234567-0123-0123-0123-0123456789ab-Jtest'))
    assert r['matching_task'] and r['job_state']=='running'  # No layer/progress proof in this fixture.
