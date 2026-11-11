import datetime as dt
import pytest
from printlab import core,bambuddy,native
from test_workflow import workspace,SimulatedBambuddy


def test_cancelled_failed_state_never_bypasses_upstream_gate_or_uploads(workspace):
    _,jd=workspace
    job=core.read_json(jd/'job.json')
    job['mapping'].update(transport='bambu_native',material='PLA Basic',color='FFFFFFFF')
    core.write_json(jd/'job.json',job)
    core.approve('P001','Jtest','确认打印',True)
    class CancelledDevice(SimulatedBambuddy):
        def get(self,path):
            result=super().get(path)
            if path.startswith('printers/'):
                result.update(state='FAILED',hms_errors=[],awaiting_plate_clear=True)
            return result
    device=CancelledDevice()
    with pytest.raises(core.WorkflowError,match='verified cancellation evidence'):
        native.submit('P001','Jtest',True,client_factory=lambda:device,runner=lambda *args:pytest.fail('upstream must not be bypassed'))
    assert device.writes==[] and not (jd/'dispatch.json').exists()


def test_x2d_missing_external_storage_never_uploads_via_ftps(workspace):
    p,jd=workspace
    card=core.read_json(core.ROOT/'Library/Devices/X2D/device.json');card['model']='X2D'
    core.write_json(core.ROOT/'Library/Devices/X2D/device.json',card)
    core.approve('P001','Jtest','确认打印',True)
    device=SimulatedBambuddy()
    with pytest.raises(core.WorkflowError,match='external storage'):
        bambuddy.submit('P001','Jtest',True,client_factory=lambda **kwargs:device)
    assert device.writes==[] and not (jd/'dispatch.json').exists()


def test_revoked_or_future_approval_cannot_dispatch(workspace):
    _,jd=workspace
    approval=core.approve('P001','Jtest','确认打印',True)
    core.write_json(jd/'approval.json',{**approval,'revoked':True})
    with pytest.raises(core.WorkflowError,match='approval'):
        bambuddy.submit('P001','Jtest',True,client_factory=lambda **kwargs:SimulatedBambuddy())
    core.write_json(jd/'approval.json',{**approval,'approved_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=20)).isoformat()})
    with pytest.raises(core.WorkflowError,match='confirmation'):
        bambuddy.submit('P001','Jtest',True,client_factory=lambda **kwargs:SimulatedBambuddy())
    assert not (jd/'dispatch.json').exists()


def test_pinned_node_or_adapter_changed_is_rejected_before_process(workspace,monkeypatch):
    _,jd=workspace
    node=core.ROOT/'fake-node';node.write_bytes(b'known-node')
    adapter=core.ROOT/'Harness/native-client.mjs';adapter.parent.mkdir();adapter.write_text('known adapter')
    manifest={'node':{'path':str(node),'sha256':core.digest(node)},'files':[{'label':'adapter','path':'Harness/native-client.mjs','sha256':core.digest(adapter)}]}
    core.write_json(core.ROOT/'Harness/native-toolchain.json',manifest)
    monkeypatch.setattr(native.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('must not execute altered tool'))
    node.write_bytes(b'changed-node')
    with pytest.raises(core.WorkflowError,match='Node binary changed'):
        native.run_client(jd,core.read_json(jd/'job.json'),'check')
    node.write_bytes(b'known-node');adapter.write_text('changed adapter')
    with pytest.raises(core.WorkflowError,match='adapter changed'):
        native.run_client(jd,core.read_json(jd/'job.json'),'check')


def test_mixed_ams_external_route_is_nozzle_bound_and_rejects_empty_or_unknown_slots(workspace):
    from test_workflow import ready
    s=ready();s['ams_extruder_map']={'0':1}
    s['vt_tray']=[{'id':255,'tray_type':'PETG','tray_color':'F72323FF'}]
    mapping={'use_ams':True,'ams_mapping':[0,255],'extruder_mapping':[1,0],
             'routing_verified':True,'fts_installed':False,'transport':'bambu_native'}
    bambuddy.validate_ready(s,mapping)
    assert bambuddy.reported_trays(s)[255]['tray_type']=='PETG'
    with pytest.raises(core.WorkflowError,match='physical nozzle'):
        bambuddy.validate_ready(s,{**mapping,'extruder_mapping':[1,1]})
    with pytest.raises(core.WorkflowError,match='missing, empty'):
        bambuddy.validate_ready({**s,'vt_tray':[]},mapping)
    with pytest.raises(core.WorkflowError,match='missing, empty'):
        bambuddy.validate_ready({**s,'vt_tray':[{'id':255,'tray_type':''}]},mapping)
    with pytest.raises(core.WorkflowError,match='duplicate'):
        bambuddy.validate_ready({**s,'vt_tray':s['vt_tray']*2},mapping)


def test_mixed_route_binds_every_material_colour_and_reported_series():
    s={'ams':[{'id':0,'tray':[{'id':2,'tray_type':'PLA','tray_color':'FFFFFFFF','tray_sub_brands':'PLA Basic'}]}],
       'vt_tray':[{'id':255,'tray_type':'PETG','tray_color':'F72323FF','tray_sub_brands':''}]}
    m={'ams_mapping':[2,255],'filament_types':['PLA','PETG'],
       'filament_colours':['FFFFFFFF','F72323FF'],'filament_series':['PLA Basic','']}
    bambuddy.validate_native_filaments(s,m)
    for change in [{'filament_types':['PLA','PLA']},{'filament_colours':['FFFFFFFF','000000FF']},
                   {'filament_series':['PLA Basic','PETG Matte']},{'filament_colours':['FFFFFFFF']}]:
        with pytest.raises(core.WorkflowError):bambuddy.validate_native_filaments(s,{**m,**change})
