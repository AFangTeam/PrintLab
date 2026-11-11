"""Exercise host-specific behavior on the actual CI operating system."""
import json
import os
from pathlib import Path
import subprocess
import sys

from printlab import core, platforms


def test_lock_excludes_another_process(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    probe = '''
import portalocker, sys
with open(sys.argv[1], 'a') as stream:
    try:
        portalocker.lock(stream, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.exceptions.LockException:
        sys.exit(7)
    portalocker.unlock(stream)
'''
    path = tmp_path / 'Runtime/locks/concurrent.lock'
    with core.lock('concurrent'):
        result = subprocess.run([sys.executable, '-c', probe, str(path)], timeout=15)
        assert result.returncode == 7
    assert subprocess.run([sys.executable, '-c', probe, str(path)], timeout=15).returncode == 0


def test_private_directory_and_unicode_roundtrip(tmp_path):
    directory = tmp_path / '私人资料 space'
    platforms.protect_directory(directory)
    file = directory / '凭据.json'
    core.write_json(file, {'说明': '中文数据'})
    assert core.read_json(file) == {'说明': '中文数据'}
    if sys.platform == 'win32':
        command = '$a=Get-Acl -LiteralPath $env:PRINTLAB_TEST_PRIVATE; ConvertTo-Json -InputObject @($a.AreAccessRulesProtected, @($a.Access | ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value })) -Compress'
        result = subprocess.check_output(['powershell', '-NoProfile', '-Command', command], text=True, env={**os.environ, 'PRINTLAB_TEST_PRIVATE': str(directory)})
        protected, identities = json.loads(result)
        assert protected is True
        assert 'S-1-5-18' in identities
        assert len(identities) == 2
    else:
        assert directory.stat().st_mode & 0o777 == 0o700


def test_host_virtual_environment_path(tmp_path):
    expected = 'Scripts/python.exe' if sys.platform == 'win32' else 'bin/python'
    assert platforms.venv_python(tmp_path) == tmp_path / expected


def test_windows_documented_launchers():
    import socket
    import time
    import urllib.request
    import pytest

    if sys.platform != 'win32':
        pytest.skip('Windows PowerShell entry points')
    root = Path(__file__).resolve().parents[2]
    cli = root / 'Harness/bin/printlab.ps1'
    result = subprocess.check_output(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                      '-File', str(cli), 'context'], cwd=root, timeout=30)
    assert json.loads(result)['missing'] == []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                '-File', str(root / 'scripts/start.ps1'), '--port', str(port)],
                               cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for attempt in range(100):
            assert process.poll() is None, 'PowerShell server exited early'
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                    assert json.load(response)['ok']
                break
            except OSError:
                time.sleep(.2)
        else:
            pytest.fail('PowerShell server failed to become healthy')
    finally:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        process.wait(timeout=15)
