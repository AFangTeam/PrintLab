"""Exercise the reported missing-privilege failure on an actual Windows kernel."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows access-control API')
@pytest.mark.parametrize('extra_aces', [False, True])
def test_initialization_without_security_privilege(tmp_path, extra_aces):
    # A child process removes SeSecurityPrivilege from its token permanently.
    # Its PowerShell children inherit that token, even on an elevated CI runner.
    # This reproduces the relevant ordinary-user constraint without modifying
    # the runner account, and tests the real initialization with existing data.
    probe = r'''
import ctypes
from ctypes import wintypes
import json, os
from pathlib import Path
import runpy, shutil, subprocess, sys

advapi = ctypes.WinDLL('advapi32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
class LUID(ctypes.Structure):
    _fields_ = [('LowPart', wintypes.DWORD), ('HighPart', wintypes.LONG)]
class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [('PrivilegeCount', wintypes.DWORD), ('Luid', LUID), ('Attributes', wintypes.DWORD)]
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
advapi.AdjustTokenPrivileges.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(TOKEN_PRIVILEGES), wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
token = wintypes.HANDLE()
assert advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x20 | 0x8, ctypes.byref(token))
try:
    privileges = TOKEN_PRIVILEGES()
    privileges.PrivilegeCount = 1
    privileges.Attributes = 4  # SE_PRIVILEGE_REMOVED, not merely disabled
    assert advapi.LookupPrivilegeValueW(None, 'SeSecurityPrivilege', ctypes.byref(privileges.Luid))
    assert advapi.AdjustTokenPrivileges(token, False, ctypes.byref(privileges), 0, None, None)
    assert ctypes.get_last_error() in (0, 1300)  # already absent is fine
finally:
    kernel.CloseHandle(token)

root = Path(sys.argv[1])
source = Path(sys.argv[2])
shutil.copytree(source / 'config', root / 'config')
directory = root / 'Runtime/private'
directory.mkdir(parents=True)
secret = directory / 'existing.json'
secret.write_text('{"existing":true}', encoding='utf-8')
sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True, encoding='ascii', errors='replace')
import csv
sid = next(csv.reader(sid.splitlines()))[1]
env = {**os.environ, 'PRINTLAB_PRIVATE_PATH': str(directory),
       'PRINTLAB_PRIVATE_DACL': f'D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)'}
if sys.argv[3] == 'True':
    subprocess.run(['icacls', str(directory), '/grant', '*S-1-1-0:(OI)(CI)R', '*S-1-5-32-544:(OI)(CI)F'], check=True, capture_output=True)
# Prove that the original call fails under this same token and filesystem.
legacy = '$ErrorActionPreference="Stop"; $a=New-Object System.Security.AccessControl.DirectorySecurity; $a.SetSecurityDescriptorSddlForm($env:PRINTLAB_PRIVATE_DACL); [System.IO.Directory]::SetAccessControl($env:PRINTLAB_PRIVATE_PATH,$a)'
result = subprocess.run(['powershell', '-NoProfile', '-Command', legacy], env=env, capture_output=True)
assert result.returncode != 0, 'Legacy defect was not reproduced'
assert b'SeSecurityPrivilege' in result.stderr, result.stderr

module = runpy.run_path(str(source / 'scripts/init_workspace.py'))
initialize = module['main']
initialize.__globals__['ROOT'] = root
initialize()
config = (root / 'Runtime/config.json').read_bytes()
initialize()
assert (root / 'Runtime/config.json').read_bytes() == config
assert secret.read_text(encoding='utf-8') == '{"existing":true}'
assert (root / 'Context/profile.md').is_file()
command = '$a=[System.IO.Directory]::GetAccessControl($env:PRINTLAB_PRIVATE_PATH); ConvertTo-Json -Compress -InputObject @($a.AreAccessRulesProtected, @($a.Access | ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }))'
result = subprocess.check_output(['powershell', '-NoProfile', '-Command', command], env=env, text=True)
protected, identities = json.loads(result)
assert protected is True
assert sorted(identities) == sorted([sid, 'S-1-5-18']), identities
print(json.dumps({'legacy_failure_reproduced': True, 'initialized_twice': True, 'extra_aces_removed': True}))
'''
    source = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-c', probe, str(tmp_path / 'workspace 中文'),
                             str(source), str(extra_aces)],
                            env={**os.environ, 'PYTHONPATH': str(source / 'Harness')},
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['legacy_failure_reproduced']


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows locale defaults')
def test_reported_unicode_reads_without_utf8_mode():
    source = Path(__file__).resolve().parents[2]
    result = subprocess.run([
        sys.executable, '-X', 'utf8=0', '-m', 'pytest', '-q',
        'Harness/tests/test_agent_policy.py', 'Harness/tests/test_onboarding_cli.py',
    ], cwd=source, env={**os.environ, 'PYTHONUTF8': '0'},
       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
