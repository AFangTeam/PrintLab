"""Install upstream Bambuddy separately and verify isolated reads and material intake."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from printlab import bambuddy, core, native, material_intake

ROOT = Path(__file__).resolve().parent.parent
VERSION = 'v1.2.5.7'
COMMIT = '188df76f8a7342542c0876dac68990ea2a8c8313'


@contextmanager
def temporary_workspace():
    directory = tempfile.TemporaryDirectory(prefix='PrintLab Bambuddy 中文 ')
    try:
        yield directory.name
    finally:
        # Windows can retain SQLite mapped-file handles briefly after taskkill.
        # Keep cleanup mandatory, with a bounded wait for handle release.
        deadline = time.monotonic() + 15
        while True:
            try:
                directory.cleanup()
                break
            except PermissionError:
                if os.name != 'nt' or time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)


def main():
    output = ROOT / 'Runtime/verification'
    output.mkdir(parents=True, exist_ok=True)
    with temporary_workspace() as temporary:
        root = Path(temporary)
        source = root / 'upstream'
        with (output/'bambuddy-install.log').open('w', encoding='utf-8') as log:
            subprocess.run(['git', 'clone', '--depth', '1', '--branch', VERSION,
                            'https://github.com/maziggy/bambuddy.git', str(source)],
                           check=True, stdout=log, stderr=log, timeout=180)
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
            assert commit == COMMIT, 'Upstream tag changed'
            environment = root / 'venv'
            subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True, timeout=60)
            python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(source/'requirements.txt')],
                           check=True, stdout=log, stderr=log, timeout=600)
            with (output/'bambuddy-packages.txt').open('w', encoding='utf-8') as packages:
                subprocess.run([str(python), '-m', 'pip', 'freeze'], check=True, stdout=packages, timeout=30)
            report = probe(source, python, root, output, log)
    report['temporary_data_removed'] = True
    (output/'bambuddy-install.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


def probe(source, python, root, output, log):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    environment = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATA_DIR', 'PYTHONPATH')}
    environment.update(DATA_DIR=str(root/'data'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    process_options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    process = subprocess.Popen([str(python), '-m', 'uvicorn', 'backend.app.main:app',
                                '--host', '127.0.0.1', '--port', str(port), '--loop', 'asyncio'],
                               cwd=source, env=environment, stdout=log, stderr=log, **process_options)
    base = f'http://127.0.0.1:{port}'
    previous_root = core.ROOT
    try:
        with httpx.Client(base_url=base, trust_env=False) as http:
            for attempt in range(120):
                if process.poll() is not None:
                    raise RuntimeError('Bambuddy exited; inspect bambuddy-install.log')
                try:
                    if http.get('/health').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError('Bambuddy startup timed out')
            permissions = ['queue', 'control_printer', 'manage_library', 'manage_inventory',
                           'manage_maintenance', 'manage_archives', 'manage_projects', 'access_cloud',
                           'update_energy_cost', 'send_notifications']
            response = http.post('/api/v1/api-keys/', json={
                'name': 'PrintLab disposable verification', 'can_read_status': True,
                **{'can_'+name: False for name in permissions}})
            response.raise_for_status()
            credential = response.json()
            core.ROOT = root/'workspace'
            core.write_json(core.ROOT/'Runtime/config.json', {'bambuddy_url': base, 'printer_id': None})
            core.write_json(core.ROOT/'Runtime/private/bambuddy.json', {'read_api_key': credential['key']})
            client = bambuddy.Client()
            try:
                paths = ['printers/', 'inventory/spools', 'inventory/assignments', 'queue/', 'archives/', 'print-log/']
                for path in paths:
                    data = client.get(path)
                    rows = data if isinstance(data, list) else data['items']
                    assert rows == [], path
            finally:
                client.close()
            assert bambuddy.inventory()['state'] == 'online'
            response = http.post('/api/v1/api-keys/', json={
                'name': 'PrintLab disposable material intake', 'can_read_status': True,
                **{'can_'+name: name == 'manage_inventory' for name in permissions}})
            response.raise_for_status()
            inventory_credential = response.json()
            core.write_json(core.ROOT/'Runtime/private/bambuddy.json', {
                'read_api_key': credential['key'], 'write_api_key': inventory_credential['key']})
            spool = {'material': 'PLA', 'color_name': 'White', 'rgba': 'FFFFFFFF',
                     'storage_location': 'Isolated test fixture'}
            registered = material_intake.register(spool, 'Disposable fixture, no real spool', 'fixture-1')
            repeated = material_intake.register(spool, 'Disposable fixture, no real spool', 'fixture-1')
            assert repeated['replayed'] and repeated['spool']['id'] == registered['spool']['id']
            assert registered['spool']['actual_remaining_weight'] is None
            assert registered['spool']['quantity_basis'] == 'unknown'
            assert len(bambuddy.inventory()['items']) == 1
            response = http.delete('/api/v1/api-keys/'+str(inventory_credential['id']))
            response.raise_for_status()
            response = http.delete('/api/v1/api-keys/'+str(credential['id']))
            response.raise_for_status()
            return {'ok': True, 'os': sys.platform, 'version': VERSION, 'commit': COMMIT,
                      'read_routes': paths, 'independent_service': True,
                      'credential_created_and_revoked': True, 'printer_contacted': False,
                      'material_intake_created_read_back_and_replayed': True,
                      'frontend_installed': False, 'scope': 'Official source backend and real PrintLab HTTP client'}
    finally:
        core.ROOT = previous_root
        native._terminate_group(process)
        log.write(f"Bambuddy process exit code: {process.returncode}\n")
        log.flush()


if __name__ == '__main__':
    main()
