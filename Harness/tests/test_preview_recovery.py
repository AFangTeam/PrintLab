import concurrent.futures
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

from PIL import Image
import pytest

from printlab import cli, core, history, preview_recovery as recovery


def png(color='red'):
    stream = io.BytesIO()
    Image.new('RGB', (3, 3), color).save(stream, format='PNG')
    return stream.getvalue()


def archive(aid=8, pid=2, profile='123', plate=2):
    return {'id': aid, 'printer_id': pid, 'print_name': 'test', 'status': 'completed',
            'extra_data': {'_print_data': {'raw_data': {'profile_id': profile, 'plate_idx': plate}}}}


def client(rows):
    class Client:
        def get(self, route):
            assert route.startswith('archives/') or route.startswith('print-log/')
            return rows if route.startswith('archives/') else []

        def close(self):
            pass
    return Client


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / '工作空间 with spaces'
    root.mkdir()
    monkeypatch.setattr(core, 'ROOT', root)
    core.write_json(root / 'Runtime/config.json', {'printer_id': 2})
    return root


def manifest(root, rows=None, filename='bindings.json'):
    source = root / '预览 来源.png'
    source.write_bytes(png())
    entries = rows if rows is not None else [{'printer_id': 2, 'archive_id': 8, 'profile_id': '123',
                                             'plate': 2, 'file': source.name}]
    path = root / filename
    core.write_json(path, {'schema_version': 1, 'previews': entries})
    return path


def test_manifest_dry_run_apply_repeat_and_history_display(workspace):
    path = manifest(workspace)
    factory = client([archive()])
    report = recovery.recover(manifest=path, client_factory=factory)
    assert report['counts'] == {'ready': 1} and report['written'] == 0
    assert not (workspace / recovery.INDEX).exists()
    assert not (workspace / recovery.IMAGES).exists()
    report = recovery.recover(manifest=path, apply=True, client_factory=factory)
    assert report['written'] == 1
    index_bytes = (workspace / recovery.INDEX).read_bytes()
    assert recovery.recover(manifest=path, apply=True, client_factory=factory)['counts'] == {'existing': 1}
    assert (workspace / recovery.INDEX).read_bytes() == index_bytes
    result = history.view(force=True, client_factory=factory)
    assert result['items'][0]['model_preview']['kind'] == 'reference_plate'
    assert result['coverage']['cloud_history_synced'] is False
    saved = core.read_json(workspace / recovery.INDEX)['2:8']
    (workspace / saved['url'].removeprefix('/api/documents/')).write_bytes(png('blue'))
    assert recovery.saved_preview({'2:8': saved}, archive()) is None
    assert recovery.recover(manifest=path, apply=True, client_factory=factory)['counts'] == {'existing_unavailable': 1}
    assert (workspace / recovery.INDEX).read_bytes() == index_bytes


def test_existing_legacy_and_other_devices_are_preserved(workspace):
    path = manifest(workspace)
    legacy = {'printer_id': 1, 'archive_id': 8, 'kind': 'reference_model', 'archive_name': 'old'}
    core.write_json(workspace / recovery.INDEX, {'8': legacy})
    recovery.recover(manifest=path, apply=True, client_factory=client([archive()]))
    index = core.read_json(workspace / recovery.INDEX)
    assert index['8'] == legacy and index['2:8']['printer_id'] == 2
    assert recovery.saved_preview(index, archive(pid=1)) is None
    with pytest.raises(core.WorkflowError, match='different device'):
        recovery.recover(manifest=path, client_factory=client([archive(pid=3)]))
    # Existing unqualified entries for the selected printer remain authoritative.
    core.write_json(workspace / recovery.INDEX, {'8': index['2:8']})
    before = (workspace / recovery.INDEX).read_bytes()
    assert recovery.recover(manifest=path, apply=True, client_factory=client([archive()]))['written'] == 0
    assert (workspace / recovery.INDEX).read_bytes() == before


def test_3mf_exact_plate_and_missing_identity(workspace):
    source = workspace / '双盘.3mf'
    with zipfile.ZipFile(source, 'w') as package:
        package.writestr('Metadata/plate_1.png', png('blue'))
        package.writestr('Metadata/plate_2.png', png())
    path = manifest(workspace, [{'printer_id': 2, 'archive_id': 8, 'profile_id': '123', 'plate': 2, 'file': source.name}])
    report = recovery.recover(manifest=path, apply=True, client_factory=client([archive(), archive(9, plate=None)]))
    assert report['counts'] == {'missing_identity': 1, 'recovered': 1}
    assert report['items'][0]['sha256'] == recovery.png_digest(png())
    other = archive(10)
    other['extra_data']['_print_data']['raw_data']['plate_id'] = 1
    assert recovery.identity(other) is None


def cache_database(root, entries):
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / 'Cache.db') as conn:
        conn.execute('CREATE TABLE cfurl_cache_response (entry_ID INTEGER, request_key TEXT)')
        conn.execute('CREATE TABLE cfurl_cache_receiver_data (entry_ID INTEGER, isDataOnFS INTEGER, receiver_data BLOB)')
        for number, (url, on_disk, data) in enumerate(entries):
            conn.execute('INSERT INTO cfurl_cache_response VALUES (?, ?)', (number, url))
            conn.execute('INSERT INTO cfurl_cache_receiver_data VALUES (?, ?, ?)', (number, on_disk, data))


URL = 'https://public-cdn.bblmw.com/profiles/123/3mf/Metadata/plate_2.png?signature=PRIVATE'


def test_cfurl_inline_external_file_conflict_and_no_private_url(workspace):
    cache = workspace / 'cache copy'
    cache_database(cache, [(URL, 0, png()), (URL, 1, b'cover.png')])
    (cache / 'fsCachedData').mkdir()
    (cache / 'fsCachedData/cover.png').write_bytes(png())
    report = recovery.recover(cache_dir=cache, client_factory=client([archive()]))
    assert report['counts'] == {'ready': 1}
    assert 'PRIVATE' not in json.dumps(report)
    (cache / 'fsCachedData/cover.png').write_bytes(png('blue'))
    assert recovery.recover(cache_dir=cache, apply=True, client_factory=client([archive()]))['counts'] == {'conflict': 1}
    assert not (workspace / recovery.INDEX).exists()


@pytest.mark.parametrize('blob', [False, True])
def test_webkit_inline_and_blob(workspace, blob):
    cache = workspace / '缓存'
    records = cache / 'WebKit/NetworkCache/Version 17/Records/hash'
    records.mkdir(parents=True)
    record = records / 'entry'
    record.write_bytes(URL.encode() + b'\x00' + (b'' if blob else png()))
    if blob:
        Path(str(record) + '-blob').write_bytes(png())
    report = recovery.recover(cache_dir=cache, apply=True, client_factory=client([archive()]))
    assert report['counts'] == {'recovered': 1}
    assert 'PRIVATE' not in (workspace / recovery.INDEX).read_text()
    assert core.read_json(workspace / recovery.INDEX)['2:8']['kind'] == 'cloud_plate'


def test_missing_cache_malformed_image_and_path_traversal(workspace):
    cache = workspace / 'missing'
    assert recovery.recover(cache_dir=cache, client_factory=client([archive()]))['counts'] == {'not_found': 1}
    (workspace / 'outside.png').write_bytes(png())
    bad_crc = bytearray(png())
    position = bad_crc.index(b'IDAT')
    length = int.from_bytes(bad_crc[position - 4:position], 'big')
    bad_crc[position + 4 + length] ^= 1
    cache_database(cache, [(URL, 1, b'../../outside.png'), (URL, 0, b'broken'), (URL, 0, bytes(bad_crc))])
    report = recovery.recover(cache_dir=cache, client_factory=client([archive()]))
    assert report['counts'] == {'not_found': 1}
    assert report['issues']['unreadable_sources'] == 1 and report['issues']['invalid_images'] == 2


def test_malformed_index_is_never_replaced(workspace):
    path = manifest(workspace)
    index = workspace / recovery.INDEX
    core.write_json(index, [])
    before = index.read_bytes()
    with pytest.raises(core.WorkflowError, match='JSON object'):
        recovery.recover(manifest=path, apply=True, client_factory=client([archive()]))
    assert index.read_bytes() == before


def test_explicit_portable_source_and_cli(workspace, monkeypatch, capsys):
    monkeypatch.setattr(recovery.sys, 'platform', 'win32')
    with pytest.raises(core.WorkflowError, match='--manifest'):
        recovery.recover(client_factory=client([archive()]))
    path = manifest(workspace)
    monkeypatch.setattr(recovery.bambuddy, 'Client', client([archive()]))
    assert cli.main(['history-recover', '--manifest', str(path), '--apply']) == 0
    assert json.loads(capsys.readouterr().out)['written'] == 1


def test_manifest_mismatch_conflict_and_interrupted_write(workspace, monkeypatch):
    base = {'printer_id': 2, 'archive_id': 8, 'profile_id': '123', 'plate': 2, 'file': '预览 来源.png'}
    path = manifest(workspace, [{**base, 'printer_id': 3}, {**base, 'plate': 1}])
    report = recovery.recover(manifest=path, client_factory=client([archive()]))
    assert report['counts'] == {'not_found': 1} and report['issues']['unmatched_manifest_entries'] == 2
    (workspace / 'blue.png').write_bytes(png('blue'))
    path = manifest(workspace, [base, {**base, 'file': 'blue.png'}])
    assert recovery.recover(manifest=path, apply=True, client_factory=client([archive()]))['counts'] == {'conflict': 1}
    path = manifest(workspace)
    original = core.write_json
    def fail(*args):
        raise OSError('simulated interrupted commit')
    monkeypatch.setattr(core, 'write_json', fail)
    with pytest.raises(OSError):
        recovery.recover(manifest=path, apply=True, client_factory=client([archive()]))
    assert not (workspace / recovery.INDEX).exists()
    monkeypatch.setattr(core, 'write_json', original)
    assert recovery.recover(manifest=path, apply=True, client_factory=client([archive()]))['written'] == 1


def test_concurrent_processes_merge_index(workspace):
    path = manifest(workspace)
    script = '''
import sys
from printlab import core, preview_recovery as r
pid = int(sys.argv[2])
class Client:
    def get(self, route):
        return [{'id': 8, 'printer_id': pid, 'extra_data': {'_print_data': {'raw_data': {'profile_id': '123', 'plate_idx': 2}}}}]
    def close(self): pass
r.recover(printer_id=pid, manifest=sys.argv[1], apply=True, client_factory=Client)
'''
    other = manifest(workspace, [{'printer_id': 3, 'archive_id': 8, 'profile_id': '123', 'plate': 2, 'file': '预览 来源.png'}], 'other.json')
    env = dict(os.environ, PRINTLAB_ROOT=str(workspace), PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    def run(pair):
        subprocess.run([sys.executable, '-c', script, str(pair[0]), str(pair[1])], env=env, check=True, timeout=30)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        list(pool.map(run, [(path, 2), (other, 3)]))
    assert set(core.read_json(workspace / recovery.INDEX)) == {'2:8', '3:8'}


def test_normal_cli_entry_point_with_http_archive_source(workspace):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == '/api/v1/archives/?printer_id=2&limit=100&offset=0'
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps([archive()]).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        core.write_json(workspace / 'Runtime/config.json', {'printer_id': 2, 'bambuddy_url': f'http://127.0.0.1:{server.server_port}'})
        core.write_json(workspace / 'Runtime/private/bambuddy.json', {'read_api_key': 'synthetic-test-key'})
        path = manifest(workspace)
        source = Path(__file__).resolve().parents[2]
        command = [str(source / 'Harness/bin/printlab')]
        if sys.platform == 'win32':
            command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(source / 'Harness/bin/printlab.ps1')]
        env = dict(os.environ, PRINTLAB_ROOT=str(workspace))
        for expected in (1, 0):
            completed = subprocess.run([*command, 'history-recover', '--manifest', str(path), '--apply'],
                                       env=env, capture_output=True, text=True, check=True, timeout=30)
            assert json.loads(completed.stdout)['written'] == expected
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_ambiguous_webkit_and_untrusted_url_are_skipped(workspace):
    cache = workspace / 'cache'
    folder = cache / 'WebKit/NetworkCache/Version 18/Records'
    folder.mkdir(parents=True)
    (folder / 'ambiguous').write_bytes(URL.encode() + b'\x00' + URL.replace('123/', '456/').encode() + b'\x00' + png())
    (folder / 'untrusted').write_bytes(URL.replace('public-cdn.bblmw.com', 'example.com').encode() + b'\x00' + png())
    report = recovery.recover(cache_dir=cache, client_factory=client([archive()]))
    assert report['counts'] == {'not_found': 1} and report['issues']['ambiguous_records'] == 1


def test_missing_cache_body_fetch_is_explicit_bounded_and_private(workspace, monkeypatch):
    import contextlib
    import httpx

    cache = workspace / 'cache'
    cache_database(cache, [(URL, 1, b'evicted.png')])
    calls = []
    def stream(method, url, **kwargs):
        calls.append(url)
        assert method == 'GET' and kwargs['follow_redirects'] is False
        return contextlib.nullcontext(httpx.Response(200, content=png(), request=httpx.Request('GET', url)))
    monkeypatch.setattr(recovery.httpx, 'stream', stream)
    assert recovery.recover(cache_dir=cache, client_factory=client([archive()]))['counts'] == {'not_found': 1}
    assert calls == []
    report = recovery.recover(cache_dir=cache, fetch_missing=True, apply=True, client_factory=client([archive()]))
    assert calls == [URL] and report['counts'] == {'recovered': 1}
    assert report['issues']['downloaded_images'] == 1
    assert 'PRIVATE' not in (workspace / recovery.INDEX).read_text() + json.dumps(report)


def test_fetch_rejects_redirect_oversize_and_untrusted_host(monkeypatch):
    import contextlib
    import httpx

    issues = {'downloaded_images': 0, 'failed_downloads': 0}
    responses = [httpx.Response(302, headers={'location': 'https://example.com'}, request=httpx.Request('GET', URL)),
                 httpx.Response(200, content=b'x' * 9, request=httpx.Request('GET', URL))]
    monkeypatch.setattr(recovery, 'MAX_IMAGE', 8)
    monkeypatch.setattr(recovery.httpx, 'stream', lambda *a, **kw: contextlib.nullcontext(responses.pop(0)))
    assert recovery.fetch_image(URL.replace('public-cdn.bblmw.com', 'example.com'), issues) is None
    assert len(responses) == 2
    assert recovery.fetch_image(URL, issues) is None
    assert recovery.fetch_image(URL, issues) is None
    assert issues == {'downloaded_images': 0, 'failed_downloads': 2}
