import uuid
import pytest
from fastapi.testclient import TestClient
from printlab import core, prepared, workbench, prepared_api
from printlab.api import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    prepared_api._sessions.clear()
    return TestClient(app, base_url='http://127.0.0.1:8018')

def headers(client):
    token=client.get('/api/prepared/session').json()['csrf_token']
    return {'Origin':'http://127.0.0.1:8018','X-PrintLab-CSRF':token}

def report():
    return {'project_id':'P009','job_id':'J1','fingerprint':'abc','ready':True,'checks':[], 'transport':{'kind':'bambu_studio'},'blockers':[]}

def test_security_origin_cookie_csrf(client,monkeypatch):
    monkeypatch.setattr(prepared,'check',lambda *a,**kw:report())
    monkeypatch.setattr(workbench,'capability',lambda r:{'available':True,'message':'test'})
    assert client.get('/api/prepared/session',headers={'Host':'evil.example'}).status_code==403
    assert client.get('/api/prepared/session',headers={'Origin':'http://evil.example'}).status_code==403
    assert client.post('/api/prepared/P009/J1/check').status_code==403
    h=headers(client)
    assert client.post('/api/prepared/P009/J1/check',headers={**h,'Origin':'http://evil.example'}).status_code==403
    assert client.post('/api/prepared/P009/J1/check',headers=h).json()['check_token']

def test_unavailable_transport_no_ticket(client,monkeypatch):
    monkeypatch.setattr(prepared,'check',lambda *a,**kw:report())
    monkeypatch.setattr(workbench,'capability',lambda r:{'available':False,'message':'not verified'})
    r=client.post('/api/prepared/P009/J1/check',headers=headers(client)).json()
    assert not r['ready'] and 'check_token' not in r

def test_start_requires_true_single_use_and_idempotency(client,monkeypatch):
    monkeypatch.setattr(prepared,'check',lambda *a,**kw:report())
    monkeypatch.setattr(workbench,'capability',lambda r:{'available':True,'message':'test'})
    launches=[]
    monkeypatch.setattr(workbench,'_launch',launches.append)
    h=headers(client)
    token=client.post('/api/prepared/P009/J1/check',headers=h).json()['check_token']
    body={'check_token':token,'plate_clear':False,'request_id':str(uuid.uuid4())}
    assert client.post('/api/prepared/P009/J1/start',headers=h,json=body).status_code==409
    body['plate_clear']='true'
    assert client.post('/api/prepared/P009/J1/start',headers=h,json=body).status_code==422
    body['plate_clear']=True
    r=client.post('/api/prepared/P009/J1/start',headers=h,json=body)
    assert r.status_code==202 and len(launches)==1
    again=client.post('/api/prepared/P009/J1/start',headers=h,json=body)
    assert again.json()['id']==r.json()['id'] and len(launches)==1
    body['request_id']=str(uuid.uuid4())
    assert client.post('/api/prepared/P009/J1/start',headers=h,json=body).status_code==409

def test_stale_ticket_and_other_browser(client,monkeypatch):
    monkeypatch.setattr(prepared,'check',lambda *a,**kw:report())
    monkeypatch.setattr(workbench,'capability',lambda r:{'available':True,'message':'test'})
    h=headers(client)
    token=client.post('/api/prepared/P009/J1/check',headers=h).json()['check_token']
    body={'check_token':token,'plate_clear':True,'request_id':str(uuid.uuid4())}
    second=TestClient(app,base_url='http://127.0.0.1:8018')
    assert second.post('/api/prepared/P009/J1/start',headers=headers(second),json=body).status_code==409
    monkeypatch.setattr(workbench,'_stamp_age',lambda stamp:121)
    assert client.post('/api/prepared/P009/J1/start',headers=h,json=body).status_code==409

def test_second_check_blocks_material_change(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'ROOT',tmp_path)
    monkeypatch.setattr(workbench,'check',lambda *a:{**report(),'ready':False})
    monkeypatch.setattr(workbench.confirmation,'record',lambda *a,**kw:pytest.fail('must not authorize'))
    op={'id':'a'*32,'project_id':'P009','job_id':'J1','fingerprint':'abc','confirmed_at':core.now()}
    workbench._run(op)
    assert core.read_json(workbench._operation_path(op['id']))['state']=='blocked'

def test_permissions_setup_only_after_explicit_same_origin_action(client, monkeypatch):
    from printlab import studio_bridge
    calls=[]
    monkeypatch.setattr(studio_bridge, 'setup_permissions', lambda: calls.append(True) or {'requested':True,'printed':False}, raising=False)
    monkeypatch.setattr(studio_bridge, 'capability', lambda: {'available':False,'message':'missing permission','observation':{'accessibility':False,'screen_capture':False}})
    assert client.get('/api/prepared/sender/capability').json()['setup_required'] is True
    assert calls==[]
    assert client.post('/api/prepared/sender/enable',json={'request_permissions':True}).status_code==403
    h=headers(client)
    assert client.post('/api/prepared/sender/enable',headers=h,json={'request_permissions':False}).status_code==400
    assert client.post('/api/prepared/sender/enable',headers=h,json={'request_permissions':'true'}).status_code==422
    assert calls==[]
    r=client.post('/api/prepared/sender/enable',headers=h,json={'request_permissions':True})
    assert r.json()['printed'] is False and calls==[True]
