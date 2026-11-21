"""Exercise deletion through the real HTTP route with disposable workspace data."""
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
from threading import Event

from fastapi.testclient import TestClient
import pytest

from printlab import bambuddy, core, prepared, project_delete, shop
from printlab.api import app


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    base = 'http://127.0.0.1:8018'
    client = TestClient(app, base_url=base)
    token = client.get('/api/prepared/session').json()['csrf_token']
    return tmp_path, client, {'Origin': base, 'X-PrintLab-CSRF': token}


def delete(client, headers, pid='P001', confirm=None):
    return client.request('DELETE', '/api/projects/' + pid, headers=headers, json={'confirm_id': confirm or pid})


def test_delete_removes_project_and_associations_only(workspace):
    root, client, headers = workspace
    for name in ('Keep', 'Delete'):
        core.new_project(name)
    keep, target = core.project_path('P001'), core.project_path('P002')
    external = root / 'original.3mf'
    external.write_bytes(b'original')
    (target / 'Sources' / 'copy.3mf').write_bytes(external.read_bytes())
    core.write_json(root / prepared.REGISTRY, {'schema_version': 1, 'items': [
        {'project_id': 'P001', 'job_id': 'keep'}, {'project_id': 'P002', 'job_id': 'gone'}]})
    for index, pid in enumerate(('P001', 'P002')):
        shop.confirm(pid, 'make it', 'test', index)
        for kind in ('checks', 'operations'):
            core.write_json(root / 'Runtime/workbench' / kind / f'{pid}.json',
                            {'project_id': pid, 'state': 'blocked'})
        log = root / f'Runtime/evidence/{pid}-v001-build.log'
        log.parent.mkdir(exist_ok=True)
        log.write_text(pid)
        core.write_json(root / f'Runtime/studio-previews/preview-{pid}/source.json',
                        {'source': str(core.project_path(pid) / 'Sources' / 'copy.3mf')})
    item = {'id': 'screw', 'name': 'shared', 'quantity': 2, 'unit': 'pcs', 'category': 'hardware',
            'spec_verified': True, 'specification': {'thread': 'M4'}}
    shop.sync('P001', [item], 2, 'fixture')
    ledger = shop.sync('P002', [item], 3, 'fixture')
    shop.stock(ledger['items'][0]['id'], 5, 1, 'stock', 4)

    result = delete(client, headers, 'P002')
    assert result.status_code == 200, result.text
    assert result.json() == {'deleted': True, 'project_id': 'P002'}
    assert not target.exists() and keep.is_dir() and external.read_bytes() == b'original'
    assert client.get('/api/projects/P002').status_code == 404
    assert core.read_json(root / prepared.REGISTRY)['items'] == [{'project_id': 'P001', 'job_id': 'keep'}]
    remaining = shop.view()
    assert list(remaining['projects']) == ['P001']
    assert remaining['items'][0]['required'] == 2 and remaining['items'][0]['existing'] == 5
    assert remaining['items'][0]['purchased'] == 1 and remaining['version'] == 6
    for name in ('Runtime/workbench/checks/{}.json', 'Runtime/workbench/operations/{}.json',
                 'Runtime/evidence/{}-v001-build.log', 'Runtime/studio-previews/preview-{}'):
        assert (root / name.format('P001')).exists() and not (root / name.format('P002')).exists()
    assert core.new_project('Delete')['id'] == 'P003'
    assert delete(client, headers, 'P002').status_code == 404
    assert core.project_path('P003').is_dir()


def test_deletion_detaches_only_its_saved_inspiration_links(workspace):
    root, client, headers = workspace
    core.new_project('Remove')
    core.new_project('Keep')
    path = root / 'Library/References/favorites.json'
    entries = [
        {'title': 'Shared design', 'related_project_ids': ['P001', 'P002'],
         'local_detail_url': '/accessories/duo-color-proposal.html', 'source_url': 'https://example.org/design'},
        {'title': 'Project detail', 'related_project_ids': ['P001'], 'local_detail_url': '#/projects/P001'},
        {'title': 'Project artifact', 'local_detail_url': headers['Origin'] + '/api/files/P001/Sources/cover.jpg'},
        {'title': 'Other project', 'local_detail_url': '/api/files/P002/Preview/cover.png'},
        {'title': 'Other site', 'local_detail_url': 'https://elsewhere.example/#/projects/P001'},
        {'title': 'Different ID', 'local_detail_url': '#/projects/P0010'},
    ]
    core.write_json(path, {'schema_version': 1, 'version': 3, 'items': entries})
    response = delete(client, headers)
    assert response.status_code == 200, response.text
    result = core.read_json(path)
    assert result['version'] == 4
    assert result['items'] == [
        {**entries[0], 'related_project_ids': ['P002']},
        {'title': 'Project detail', 'related_project_ids': []},
        {'title': 'Project artifact'}, *entries[3:],
    ]


def test_delete_requires_same_origin_session_confirmation_and_exact_identity(workspace):
    root, client, headers = workspace
    core.new_project('MyName')
    folder = core.project_path('P001')
    for values in ({}, {'Origin': headers['Origin']}, {**headers, 'Origin': 'http://elsewhere.invalid'},
                   {**headers, 'Sec-Fetch-Site': 'cross-site'}):
        assert delete(client, values).status_code == 403
    assert delete(TestClient(app, base_url=headers['Origin']), headers).status_code == 403
    assert delete(client, headers, confirm='P002').status_code == 409
    assert delete(client, headers, pid='MyName').status_code == 404
    metadata = core.read_json(folder / 'project.json')
    core.write_json(folder / 'project.json', {**metadata, 'id': 'P999'})
    assert delete(client, headers).status_code == 409
    core.write_json(folder / 'project.json', metadata)
    (root / 'Project/P001-duplicate').mkdir()
    assert delete(client, headers).status_code == 409
    assert (folder / 'project.json').exists()


@pytest.mark.parametrize('state', sorted(bambuddy.ACTIVE_JOB_STATES))
def test_all_attempts_are_checked_even_when_not_current(workspace, state):
    _, client, headers = workspace
    core.new_project('Print')
    folder = core.project_path('P001')
    core.write_json(folder / 'Print/Jold/job.json', {'state': state})
    core.write_json(folder / 'Print/Jnew/job.json', {'state': 'awaiting_approval'})
    assert delete(client, headers).status_code == 409
    assert (folder / 'Print/Jold/job.json').is_file()


def test_deletion_checks_operations_and_receipts(workspace):
    root, client, headers = workspace
    core.new_project('Print')
    folder = core.project_path('P001')
    receipt = folder / 'Print/Jold/dispatch.json'
    core.write_json(receipt, {'state': 'dispatching'})
    assert delete(client, headers).status_code == 409
    core.write_json(receipt.parent / 'job.json', {'id': 'Jold', 'state': 'awaiting_physical_review'})
    op = root / 'Runtime/workbench/operations/job.json'
    for state in ('checking', 'dispatching', 'unknown', 'submitted'):
        core.write_json(op, {'project_id': 'P001', 'job_id': 'Jother', 'state': state})
        assert delete(client, headers).status_code == 409
    core.write_json(op, {'project_id': 'P001', 'job_id': 'Jold', 'state': 'observed'})
    assert delete(client, headers).status_code == 200


def test_symlinks_do_not_expand_the_deleted_tree(workspace):
    root, client, headers = workspace
    core.new_project('Link')
    folder = core.project_path('P001')
    outside = root / 'unrelated'
    outside.mkdir()
    sentinel = outside / 'keep'
    sentinel.write_bytes(b'keep')
    (folder / 'Sources/borrowed').symlink_to(outside, target_is_directory=True)
    linked_parent = root / 'real-projects'
    (root / 'Project').rename(linked_parent)
    (root / 'Project').symlink_to(linked_parent, target_is_directory=True)
    assert delete(client, headers).status_code == 409
    (root / 'Project').unlink()
    linked_parent.rename(root / 'Project')
    assert delete(client, headers).status_code == 200
    assert sentinel.read_bytes() == b'keep'


@pytest.mark.skipif(os.name != 'nt', reason='NTFS directory junction requires Windows')
def test_delete_unlinks_windows_junction_without_touching_its_target(workspace):
    root, client, headers = workspace
    core.new_project('With junction')
    folder = core.project_path('P001')
    library = root / 'Shared model library'
    library.mkdir()
    original = library / 'original.3mf'
    original.write_bytes(b'keep shared geometry')
    junction = folder / 'Borrowed files'
    subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(junction), str(library)],
                   check=True, capture_output=True)
    assert (junction / original.name).read_bytes() == original.read_bytes()
    response = delete(client, headers)
    assert response.status_code == 200, response.text
    assert not folder.exists()
    assert original.read_bytes() == b'keep shared geometry'


@pytest.mark.parametrize('project_status', ['designing', 'printing'])
def test_locked_file_failure_allows_retry_after_restart(workspace, monkeypatch, project_status):
    root, client, headers = workspace
    project = core.new_project('Incomplete')
    target = core.project_path('P001')
    core.write_json(target / 'project.json', {**project, 'status': project_status, 'current_job_id': 'J1'})
    core.write_json(target / 'Print/J1/job.json', {'state': 'completed'})
    core.write_json(target / 'Print/J1/dispatch.json', {'state': 'observed'})
    rmtree = project_delete.shutil.rmtree
    with monkeypatch.context() as patch:
        def fail(path):
            if path.name.startswith('.deleting-'):
                (path / 'Print/J1/job.json').unlink()
                raise PermissionError('locked receipt')
            rmtree(path)
        patch.setattr(project_delete.shutil, 'rmtree', fail)
        assert delete(client, headers).status_code == 409
        assert core.project_path('P001') == target
    fresh = TestClient(app, base_url=headers['Origin'])
    auth = {**headers, 'X-PrintLab-CSRF': fresh.get('/api/prepared/session').json()['csrf_token']}
    assert delete(fresh, auth).status_code == 200
    assert not target.exists()
    assert core.new_project('Incomplete')['id'] == 'P002'


def test_concurrent_project_creation_waits_for_delete(workspace, monkeypatch):
    _, client, headers = workspace
    core.new_project('Original')
    entered, resume = Event(), Event()
    original = project_delete._remove_tree

    def delayed(project, metadata):
        entered.set()
        assert resume.wait(5)
        original(project, metadata)

    monkeypatch.setattr(project_delete, '_remove_tree', delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        remove = pool.submit(delete, client, headers)
        assert entered.wait(5)
        create = pool.submit(core.new_project, 'Original')
        resume.set()
        assert remove.result().status_code == 200
        assert create.result()['id'] == 'P002'


def test_waiting_writer_cannot_recreate_deleted_folder(workspace, monkeypatch):
    from contextlib import contextmanager
    from printlab import publication

    _, client, headers = workspace
    core.new_project('Waiting writer')
    project = core.project_path('P001')
    ready, resume = Event(), Event()
    lock_project = core.project_write_lock

    @contextmanager
    def wait_for_deletion(path):
        ready.set()
        assert resume.wait(10)
        with lock_project(path) as project_id:
            yield project_id

    monkeypatch.setattr(core, 'project_write_lock', wait_for_deletion)
    with ThreadPoolExecutor() as pool:
        writer = pool.submit(publication.init, 'Waiting writer')
        try:
            assert ready.wait(10)
            assert delete(client, headers).status_code == 200
        finally:
            resume.set()
        with pytest.raises(core.WorkflowError):
            writer.result(timeout=10)
    assert not project.exists()


def test_unknown_receipt_requires_matching_resolution(workspace):
    _, client, headers = workspace
    core.new_project('Uncertain')
    old = core.project_path('P001') / 'Print/Jold'
    core.write_json(old / 'job.json', {'state': 'failed'})
    core.write_json(old / 'dispatch.json', {'state': 'unknown', 'queue_id': 52})
    assert delete(client, headers).status_code == 409
    core.write_json(old / 'observation.json', {'queue': {'id': 51, 'status': 'failed'}})
    assert delete(client, headers).status_code == 409
    core.write_json(old / 'observation.json', {'queue': {'id': 52, 'status': 'failed'}})
    assert delete(client, headers).status_code == 200


def test_internal_mount_is_refused_before_cleanup(workspace, monkeypatch):
    root, client, headers = workspace
    core.new_project('Mounted')
    volume = core.project_path('P001') / 'Sources/drive'
    volume.mkdir()
    marker = volume / 'keep'
    marker.write_bytes(b'unchanged')
    monkeypatch.setattr(project_delete.os.path, 'ismount', lambda path: path == volume)
    assert delete(client, headers).status_code == 409
    assert marker.read_bytes() == b'unchanged'
    assert not (root / 'Project/.id-high-water.json').exists()


def test_stale_printing_summary_uses_bound_terminal_job(workspace):
    _, client, headers = workspace
    project = core.new_project('Cancelled first print')
    folder = core.project_path(project['id'])
    core.write_json(folder / 'project.json', {**project, 'current_job_id': 'Jcurrent', 'status': 'printing'})
    core.write_json(folder / 'Print/Jold/job.json', {'state': 'completed'})
    assert delete(client, headers).status_code == 409
    core.write_json(folder / 'Print/Jcurrent/job.json', {'state': 'cancelled'})
    core.write_json(folder / 'Print/Jcurrent/dispatch.json', {'state': 'submitted', 'queue_id': 10})
    assert delete(client, headers).status_code == 200
