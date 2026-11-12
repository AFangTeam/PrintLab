import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from printlab import core, onboarding, workspace
from printlab.api import app


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    return tmp_path


def host(expected=0):
    return onboarding.record_host('Test host', {'local_files': True, 'terminal': True,
        'chat_create': True, 'chat_read': True}, 'Test fixture, simulated host tools', expected)


def test_empty_workspace_is_resumable_and_does_not_claim_live_or_roles(root):
    (root / 'Context').mkdir()
    (root / 'Context/team.md').write_text('Sara 与 Mike 待建立', encoding='utf-8')
    first = onboarding.view()
    assert first['version'] == 0
    assert not first['team_ready'] and not first['printing_verified']
    assert len(first['questions']) == 4
    assert first['device'] is None
    assert not (root / onboarding.STATE).exists()
    response = TestClient(app).get('/api/onboarding')
    assert response.status_code == 200
    assert response.json()['inventory']['state'] == 'unavailable'
    assert list(root.rglob('dispatch.json')) == []


def test_host_and_answers_have_version_checks_and_preserve_existing_profile(root):
    (root / 'Context').mkdir()
    (root / 'Context/profile.md').write_text('我的既有偏好\n', encoding='utf-8')
    host()
    result = onboarding.answer('usage_goals', '做耳机支架', '用户消息 1', 1)
    assert result['version'] == 2
    profile = workspace.document('profile')['text']
    assert '我的既有偏好' in profile and '做耳机支架' in profile
    assert result['answers']['usage_goals']['document'] == 'Context/profile.md'
    with pytest.raises(core.WorkflowError, match='changed'):
        onboarding.answer('cloud_needs', '保留 Handy', '用户消息 2', 1)
    assert 'cloud_needs' not in onboarding.state()['answers']
    with pytest.raises(core.WorkflowError):
        onboarding.record_host('host', {'chat_create': 'yes'}, 'tools', 2)


def test_adopt_existing_sara_requires_host_readback_and_preserves_binding(root):
    receipt = {'request_id': 'existing-sara', 'thread_id': 'existing-thread', 'host_id': 'test',
               'workspace': str(root), 'source': 'Observed existing chat'}
    with pytest.raises(core.WorkflowError, match='Observe'):
        onboarding.record_role('Sara', receipt, 0, adopt=True)
    host()
    adopted = onboarding.record_role('Sara', receipt, 1, adopt=True)
    assert adopted['roles']['sarah']['status'] == 'created'
    assert not onboarding.reserve_role('Sarah', 'new-request', 2)['create_allowed']
    with pytest.raises(core.WorkflowError, match='different chat'):
        onboarding.record_role('Sarah', {**receipt, 'thread_id': 'other'}, 2, adopt=True)


def test_device_facts_and_connection_path_validation(root):
    for confirmed in ({'ams_count': True}, {'nozzle_diameter_mm': -0.4}, {'fts_installed': 'yes'}):
        with pytest.raises(core.WorkflowError):
            workspace.update_device({'user_confirmed': confirmed}, 'User', None)
    target = root / 'other.json'
    core.write_json(target, {'bambuddy_url': 'http://localhost:8017'})
    (root / 'Runtime').mkdir()
    (root / 'Runtime/config.json').symlink_to(target)
    with pytest.raises(core.WorkflowError):
        workspace.configure_connection('http://localhost:8017', 1, core.digest(target))


def test_role_reservation_is_exclusive_and_alias_does_not_duplicate(root):
    host()
    def reserve(request):
        return onboarding.reserve_role('Sara', request, 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(reserve, ['request-one', 'request-two']))
    assert sum(row['create_allowed'] for row in replies) == 1
    assert list(onboarding.state()['roles']) == ['sarah']
    record = onboarding.state()['roles']['sarah']
    assert str(root) in record['prompt'] and '首次回复' in record['prompt']
    retry = onboarding.reserve_role('Sarah', record['request_id'], 0)
    assert retry['create_allowed'] is False
    assert retry['role']['request_id'] == record['request_id']


def test_role_creation_and_greeting_are_separate_and_exact_workspace_bound(root):
    host()
    onboarding.reserve_role('Sarah', 'request-one', 1)
    receipt = {'request_id': 'request-one', 'thread_id': 'actual-thread', 'host_id': 'local',
               'workspace': str(root), 'source': 'simulated create_thread receipt'}
    created = onboarding.record_role('sarah', receipt, 2)
    assert created['roles']['sarah']['status'] == 'created'
    assert not onboarding.view()['team_ready']
    with pytest.raises(core.WorkflowError, match='context'):
        onboarding.record_role('sarah', {**receipt, 'first_reply': '我的设备待配置'}, 3)
    introduced = {**receipt, 'first_reply': '我已读入共同资料，机器待接入。',
                  'context_paths': ['AGENTS.md', 'Context/profile.md', 'Context/workflow.md']}
    value = onboarding.record_role('sarah', introduced, 3)
    assert value['roles']['sarah']['status'] == 'introduced'
    assert onboarding.record_role('sarah', introduced, 3)['version'] == 4
    with pytest.raises(core.WorkflowError, match='workspace'):
        onboarding.record_role('sarah', {**introduced, 'workspace': '/other'}, 4)
    with pytest.raises(core.WorkflowError, match='different chat'):
        onboarding.record_role('sarah', {**introduced, 'thread_id': 'other'}, 4)
    value = onboarding.record_role('sarah', {**receipt, 'source': 'read back again'}, 4)
    assert value['roles']['sarah']['status'] == 'introduced'


def test_capability_missing_does_not_reserve_or_create(root):
    with pytest.raises(core.WorkflowError, match='Host'):
        onboarding.reserve_role('Mike', 'request', 0)
    assert onboarding.state()['roles'] == {}


def test_two_roles_normalize_workspace_paths_and_reach_ready(root):
    host()
    for role in ('Mike', 'Sarah'):
        request = 'test-' + role
        onboarding.reserve_role(role, request, onboarding.state()['version'])
        receipt = {'request_id': request, 'thread_id': request, 'host_id': 'local',
                   'workspace': root.as_posix() + '/.', 'source': 'Simulated host readback',
                   'first_reply': '已读共同状态，设备未配置。',
                   'context_paths': [str(root / 'AGENTS.md'), 'Context\\profile.md', 'Context/workflow.md']}
        onboarding.record_role(role, receipt, onboarding.state()['version'])
    assert onboarding.view()['team_ready'] is True
    with pytest.raises(core.WorkflowError, match='another workspace'):
        onboarding.record_role('Sarah', {**receipt, 'context_paths': ['/other/AGENTS.md']}, onboarding.state()['version'])
    with pytest.raises(core.WorkflowError, match='inside'):
        onboarding.record_role('Sarah', {**receipt, 'context_paths': ['../AGENTS.md']}, onboarding.state()['version'])


def test_failed_host_creation_can_resume_after_absence_evidence(root):
    host()
    onboarding.reserve_role('Mike', 'failed-request', 1)
    with pytest.raises(core.WorkflowError, match='matching'):
        onboarding.release_role('Mike', 'wrong-request', 'Simulated host absence', 2)
    onboarding.release_role('Mike', 'failed-request', 'Simulated host failure and exhaustive request search', 2)
    assert onboarding.reserve_role('Mike', 'retry-request', 3)['create_allowed']
    receipt = {'request_id': 'retry-request', 'thread_id': 'real-host-id', 'host_id': 'local',
               'workspace': str(root), 'source': 'Fixture'}
    onboarding.record_role('Mike', receipt, 4)
    with pytest.raises(core.WorkflowError, match='matching'):
        onboarding.release_role('Mike', 'retry-request', 'Cannot release created chat', 5)


def test_document_updates_conflict_idempotency_and_legacy_text(root):
    first = workspace.append_note('lessons', '待验证的冷却假设', '项目复盘', 'abc', None)
    replay = workspace.append_note('lessons', '待验证的冷却假设', '项目复盘', 'abc', None)
    assert replay['replayed'] and replay['sha256'] == first['sha256']
    with pytest.raises(core.WorkflowError, match='different'):
        workspace.append_note('lessons', '换了结论', '项目复盘', 'abc', first['sha256'])
    with pytest.raises(core.WorkflowError, match='changed'):
        workspace.append_note('lessons', '新记录', '项目复盘', 'def', None)
    second = workspace.append_note('lessons', '新记录', '项目复盘', 'def', first['sha256'])
    assert '待验证的冷却假设' in second['text'] and '新记录' in second['text']
    with pytest.raises(core.WorkflowError):
        workspace.document('../Runtime/private/bambuddy.json')


def test_device_facts_preserve_unrelated_fields_and_reject_secrets(root):
    path = root / workspace.DOCUMENTS['device']
    core.write_json(path, {'schema_version': 1, 'installed': {'legacy': 'preserved'},
                           'user_confirmed': {'fts_installed': False}})
    result = workspace.update_device({'model': 'Other machine', 'user_confirmed': {'ams_count': 1}},
                                     '用户确认', core.digest(path))
    card = json.loads(result['text'])
    assert card['installed']['legacy'] == 'preserved'
    assert card['user_confirmed'] == {'fts_installed': False, 'ams_count': 1}
    with pytest.raises(core.WorkflowError, match='credentials'):
        workspace.update_device({'user_confirmed': {'access_code': 'secret'}}, 'source', result['sha256'])


class DeviceClient:
    def __init__(self):
        self.closed = False

    def get(self, path):
        metadata = {'id': 7, 'name': 'Printer', 'model': 'P1S', 'access_code': 'secret'}
        if path == 'printers/':
            return [metadata]
        if path == 'printers/7':
            return metadata
        assert path == 'printers/7/status'
        return {'id': 7, 'connected': True, 'last_ams_update': time.time(), 'access_code': 'secret'}

    def close(self):
        self.closed = True


def test_discovery_and_adoption_preserve_confirmation_and_strip_secrets(root):
    cfg = workspace.configure_connection('http://127.0.0.1:8000', 7, None)
    assert cfg['printer_id'] == 7
    path = root / workspace.DOCUMENTS['device']
    core.write_json(path, {'schema_version': 1, 'user_confirmed': {'model': 'X2D'}})
    client = DeviceClient()
    result = onboarding.discover(lambda: client)
    assert client.closed and 'secret' not in json.dumps(result)
    result = onboarding.adopt_device(core.digest(path), DeviceClient)
    card = json.loads(result['text'])
    assert card['verification_status'] == 'identity_conflict'
    assert card['user_confirmed']['model'] == 'X2D' and card['observed']['model'] == 'P1S'
    assert 'secret' not in result['text']
    with pytest.raises(core.WorkflowError):
        workspace.configure_connection('http://user:password@localhost', 1, cfg['sha256'])


def test_cli_cross_process_context_and_conflicting_update(root):
    environment = {**os.environ, 'PRINTLAB_ROOT': str(root),
                   'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'PYTHONUTF8': '1'}
    command = [sys.executable, '-m', 'printlab.cli']
    def call(args):
        return subprocess.run([*command, *args], env=environment, capture_output=True, text=True)
    initial = call(['onboarding', 'status'])
    assert json.loads(initial.stdout)['version'] == 0
    updated = call(['workspace', 'note', 'profile', '--text', '喜欢可拆装方案', '--source', '用户消息',
                    '--request-id', 'cli-one', '--expect-sha', 'missing'])
    assert updated.returncode == 0, updated.stderr
    context = call(['context'])
    assert context.returncode == 0, context.stderr
    data = json.loads(context.stdout)
    assert any('喜欢可拆装方案' in doc['text'] for doc in data['documents'])
    assert data['onboarding']['workspace'] == str(root)
    stale = call(['workspace', 'note', 'profile', '--text', '另一项', '--source', '用户消息',
                  '--request-id', 'cli-two', '--expect-sha', 'missing'])
    assert stale.returncode != 0


def test_two_processes_cannot_overwrite_shared_profile_or_create_duplicate_roles(root):
    environment = {**os.environ, 'PRINTLAB_ROOT': str(root),
                   'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'PYTHONUTF8': '1'}
    command = [sys.executable, '-m', 'printlab.cli']
    processes = [subprocess.Popen([*command, 'workspace', 'note', 'profile', '--text', text,
        '--source', 'Simulated simultaneous user updates', '--request-id', str(index), '--expect-sha', 'missing'],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for index, text in enumerate(['喜欢小尺寸', '需要可拆装'])]
    outputs = [process.communicate(timeout=20) for process in processes]
    assert sorted(process.returncode for process in processes) == [0, 2], outputs
    host()
    processes = [subprocess.Popen([*command, 'onboarding', 'reserve-role', 'Mike',
        '--request-id', f'create-{index}', '--expect', '1'], env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for index in range(2)]
    responses = [json.loads(process.communicate(timeout=20)[0]) for process in processes]
    assert sum(response['create_allowed'] for response in responses) == 1
