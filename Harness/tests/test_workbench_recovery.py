"""Recovery and concurrency checks use only temporary files and simulated device results."""
import sys
import types
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from printlab import core, prepared_api, workbench
from printlab.api import app

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    return tmp_path

def op(opid, state):
    return {'id': opid, 'state': state, 'project_id': 'P009', 'job_id': 'J1',
            'owner': 'owner', 'request_id': str(uuid.uuid4()), 'created_at': core.now()}

def test_persistent_session_survives_server_memory_reset(isolated):
    client = TestClient(app, base_url='http://127.0.0.1:8018')
    token = client.get('/api/prepared/session').json()['csrf_token']
    sid = client.cookies['printlab_session']
    record = op('a'*32, 'unknown')
    record['owner'] = sid
    core.write_json(workbench._operation_path(record['id']), record)
    prepared_api._sessions.clear()
    second = TestClient(app, base_url='http://127.0.0.1:8018')
    second.cookies.set('printlab_session', sid)
    assert second.get('/api/prepared/session').json()['csrf_token'] == token
    assert second.get('/api/prepared/operations/' + record['id']).json()['state'] == 'unknown'
    if __import__('sys').platform != 'win32':
        assert (isolated / 'Runtime/private/workbench-sessions.json').stat().st_mode & 0o777 == 0o600

def test_boot_recovery_fails_closed(isolated):
    checking, dispatching = op('a'*32, 'checking'), op('b'*32, 'dispatching')
    for record in (checking, dispatching):
        core.write_json(workbench._operation_path(record['id']), record)
    workbench.recover_operations()
    assert core.read_json(workbench._operation_path(checking['id']))['state'] == 'blocked'
    assert core.read_json(workbench._operation_path(dispatching['id']))['state'] == 'unknown'

def test_send_exception_without_receipt_is_unknown(isolated, monkeypatch):
    record = op('c'*32, 'checking')
    record.update(fingerprint='fingerprint', confirmed_at=core.now())
    monkeypatch.setattr(workbench, 'check', lambda *a, **kw: {'ready': True, 'fingerprint': 'fingerprint'})
    monkeypatch.setattr(workbench.confirmation, 'record', lambda *a, **kw: {'id': 'confirmation'})
    monkeypatch.setattr(core, 'approve', lambda *a, **kw: None)
    monkeypatch.setattr(core, 'job_path', lambda *a: isolated / 'job')
    def fail(*args):
        raise RuntimeError('simulated exception after send began')
    from printlab import studio_bridge
    monkeypatch.setattr(studio_bridge, 'dispatch', fail)
    workbench._run(record)
    assert not (isolated / 'job/dispatch.json').exists()
    assert core.read_json(workbench._operation_path(record['id']))['state'] == 'unknown'

def test_concurrent_same_request_launches_once(isolated, monkeypatch):
    monkeypatch.setattr(workbench.prepared, 'check', lambda *a, **kw: {'project_id':'P009','fingerprint':'fp','checks':[], 'transport':{'kind':'bambu_studio'}})
    monkeypatch.setattr(workbench, 'capability', lambda r: {'available':True, 'message':'simulated'})
    token = workbench.check('P009','J1',owner='owner')['check_token']
    barrier, launches = Barrier(2), []
    rid = str(uuid.uuid4())
    def submit():
        barrier.wait()
        return workbench.start('P009','J1',owner='owner',check_token=token,plate_clear=True,request_id=rid,launch=launches.append)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:submit(), range(2)))
    assert len(launches) == 1
    assert results[0]['id'] == results[1]['id']

def test_unknown_readback_needs_fresh_exact_match(isolated, monkeypatch):
    record = op('d'*32, 'unknown')
    core.write_json(workbench._operation_path(record['id']), record)
    job = isolated / 'job'
    core.write_json(job / 'dispatch.json', {'simulated': True})
    monkeypatch.setattr(core, 'job_path', lambda *a: job)
    for result in ({'matching_task':False,'fresh':True}, {'matching_task':True,'fresh':False}):
        monkeypatch.setattr(workbench.bambuddy, 'reconcile', lambda *a, result=result: result)
        assert workbench.reconcile_operation(record['id'],'other-owner')['state'] == 'unknown'
    monkeypatch.setattr(workbench.bambuddy, 'reconcile', lambda *a: {'matching_task':True,'fresh':True,'device_state':'RUNNING'})
    matched = workbench.reconcile_operation(record['id'],'other-owner')
    assert matched['state'] == 'observed'
    assert '首层' in matched['message']


def test_readback_error_after_click_stays_unknown(isolated, monkeypatch):
    from printlab import studio_bridge
    record = op('e'*32, 'checking')
    record.update(fingerprint='fingerprint', confirmed_at=core.now())
    monkeypatch.setattr(workbench, 'check', lambda *a, **kw: {'ready': True, 'fingerprint': 'fingerprint'})
    monkeypatch.setattr(workbench.confirmation, 'record', lambda *a, **kw: {'id': 'confirmation'})
    monkeypatch.setattr(core, 'approve', lambda *a, **kw: None)
    monkeypatch.setattr(core, 'job_path', lambda *a: isolated / 'job')
    monkeypatch.setattr(studio_bridge, 'dispatch', lambda *a: {'command_sent': True, 'executed': True})
    def fail(*a):
        raise RuntimeError('simulated readback failure')
    monkeypatch.setattr(workbench.bambuddy, 'reconcile', fail)
    workbench._run(record)
    assert core.read_json(workbench._operation_path(record['id']))['state'] == 'unknown'
