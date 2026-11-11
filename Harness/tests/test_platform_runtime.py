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
