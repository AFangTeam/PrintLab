import json

import httpx

from printlab import core, history


def archive(aid=1, **kw):
    return dict(id=aid, printer_id=1, print_name='模型', status='completed',
                started_at='2026-11-01T00:00:00', **kw)


def test_reprints_are_retained_and_archive_is_not_double_counted():
    a = archive()
    runs = [dict(id=1, archive_id=1, printer_id=1, started_at=a['started_at'], status='failed'),
            dict(id=2, archive_id=1, printer_id=1, started_at='2026-11-02T00:00:00', status='completed')]
    result = history.combine([a], runs, [])
    assert len(result) == 2
    assert {x['status'] for x in result} == {'failed', 'completed'}
    assert result[0]['started_at'].endswith('+00:00')
    assert all(x['physical_review'] == 'not_verified' for x in result)


def test_missing_archive_and_import_only_are_kept():
    a = archive(); a.update(started_at=None, status='archived')
    r = dict(id=2, archive_id=None, printer_id=1, status='failed', started_at='2026-11-01T00:00:00')
    items = history.combine([a], [r], [])
    assert len(items) == 2
    assert sum(x['is_print_event'] for x in items) == 1


def test_link_requires_device_and_exact_identity_not_similar_titles():
    job = dict(id='J20261101-123456-abcdef', printer_id=1, archive_ids={2}, project_id='P001', project_name='作品')
    a = archive(); a['print_name'] = 'checked-uuid-J20261101-123456-abcdef'
    assert history.association(a, [job])['project_id'] == 'P001'
    a['printer_id'] = 2
    assert history.association(a, [job])['project_id'] is None
    a.update(printer_id=1, print_name='作品')
    assert history.association(a, [job])['project_id'] is None
    a['id'] = 2
    assert history.association(a, [job])['project_id'] == 'P001'
    conflict = {**job, 'project_id': 'P002'}
    assert history.association(a, [job, conflict])['project_id'] is None


def test_private_telemetry_and_urls_never_escape():
    a = archive(extra_data={'_print_data': {'raw_data': {'design_id': '123', 'access_code': 'SECRET', 'ipcam': {'rtsp_url': 'SECRET'}}}},
                file_path='/private/SECRET.3mf', makerworld_url='javascript:SECRET')
    row = history.normalize(a, None, [])
    assert 'SECRET' not in json.dumps(row)
    assert row['makerworld_url'] == 'https://makerworld.com.cn/zh/models/123'
    assert row['launch_app'] is None


def test_pagination_and_identity_dedup(monkeypatch):
    monkeypatch.setattr(history, 'PAGE_SIZE', 2)
    class Client:
        def get(self, path):
            return [{'id': 1}, {'id': 2}] if 'offset=0' in path else [{'id': 3}]
    assert len(history.pages(Client(), 'archives', 1)) == 3


def test_archive_photo_is_verified_cached_and_rejects_paths(tmp_path, monkeypatch):
    import io
    from PIL import Image
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    image = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(image, format='PNG')
    data = image.getvalue()
    class Http:
        def get(self, path):
            assert path == 'archives/1/photos/photo.png'
            return httpx.Response(200, content=data, request=httpx.Request('GET', 'http://localhost/'))
    class Client:
        http = Http()
    url = history.archive_photo(Client(), {'id': 1, 'photos': ['photo.png']})
    assert (tmp_path / url.removeprefix('/api/documents/')).read_bytes() == data
    class Offline:
        def get(self, path): raise AssertionError('cached image should not be fetched')
    Client.http = Offline()
    assert history.archive_photo(Client(), {'id': 1, 'photos': ['photo.png']}) == url
    assert history.archive_photo(Client(), {'id': 1, 'photos': ['../photo.png']}) is None


def test_model_preview_requires_exact_task_and_uses_requested_plate(tmp_path, monkeypatch):
    import io
    import zipfile
    from PIL import Image
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    pid, jid = 'P001', 'J20261107-110346-b4156a'
    project = tmp_path / 'Project/P001-example'
    core.write_json(project / 'project.json', {'id': pid})
    jd = project / 'Print' / jid
    jd.mkdir(parents=True)
    buf = io.BytesIO()
    Image.new('RGB', (3, 3), 'red').save(buf, format='PNG')
    with zipfile.ZipFile(jd / 'slice.3mf', 'w') as z:
        z.writestr('Metadata/plate_2.png', buf.getvalue())
    job = {'id': jid, 'project_id': pid, 'printer_id': 1, 'archive_ids': set(),
           'artifact': 'slice.3mf', 'plate': 2, 'revision': 'v001'}
    core.write_json(jd / 'job.json', {'id': jid})
    a = archive(); a['print_name'] = jid
    result = history.model_preview(a, [job])
    assert result['job_id'] == jid and result['revision'] == 'v001'
    assert (tmp_path / result['url'].removeprefix('/api/documents/')).read_bytes() == buf.getvalue()
    assert history.model_preview({**a, 'print_name': 'similar name'}, [job]) is None
    assert history.model_preview({**a, 'printer_id': 2}, [job]) is None


def test_cache_survives_network_failure_without_claiming_freshness(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    core.write_json(tmp_path / 'Runtime/config.json', {'printer_id': 1})
    class Client:
        def get(self, path):
            if path.startswith('archives'):
                a = archive(); a['status'] = 'printing'
                return [a]
            if path.startswith('print-log'):
                return {'items': []}
            return {'connected': False, 'state': 'FINISH'}
        def close(self): pass
    result = history.view(force=True, client_factory=Client)
    assert result['counts']['prints'] == 1
    assert result['items'][0]['status'] == 'unresolved'
    class Offline(Client):
        def get(self, path): raise httpx.ConnectError('SECRET endpoint')
    failed = history.view(force=True, client_factory=Offline)
    assert failed['stale'] and failed['state'] == 'unavailable'
    assert failed['items'] == result['items']
    assert 'SECRET' not in json.dumps(failed)
    assert core.read_json(tmp_path / 'Runtime/history/latest.json')['state'] == 'current'


def test_live_status_requires_matching_archive_and_fresh_telemetry(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    core.write_json(tmp_path / 'Runtime/config.json', {'printer_id': 1})
    class Client:
        def get(self, path):
            if path.startswith('archives'):
                a = archive(); a['status'] = 'printing'
                return [a]
            if path.startswith('print-log'): return {'items': []}
            return {'connected': True, 'state': 'PAUSE', 'current_archive_id': 1, 'last_ams_update': time.time(), 'progress': 86}
        def close(self): pass
    row = history.view(force=True, client_factory=Client)['items'][0]
    assert row['status'] == 'paused' and row['progress'] == 86


def test_history_api_has_no_write_route(monkeypatch):
    from fastapi.testclient import TestClient
    from printlab.api import app
    monkeypatch.setattr(history, 'view', lambda: {'items': [], 'stale': False})
    client = TestClient(app)
    assert client.get('/api/history').json() == {'items': [], 'stale': False}
    assert client.post('/api/history').status_code == 405
