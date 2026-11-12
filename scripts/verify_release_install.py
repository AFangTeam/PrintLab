"""Build a tracked-source release ZIP and install it in a fresh Unicode directory.

Invoked by cloud onboarding. It does not connect to any printer or reuse private data.
The ZIP is kept as a CI artifact so the tested bytes can be inspected/downloaded.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    output = ROOT / 'Runtime/verification'
    output.mkdir(parents=True, exist_ok=True)
    bundle = output / 'PrintLab.zip'
    subprocess.run(['git', 'archive', '--format=zip', '--prefix=PrintLab/', '-o', str(bundle), 'HEAD'], cwd=ROOT, check=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    env = {k:v for k,v in os.environ.items() if k not in {'PRINTLAB_ROOT','PYTHONPATH','VIRTUAL_ENV'}}
    env['PRINTLAB_SKIP_RELEASE_CHECK'] = '1'
    env['PYTHONUTF8'] = '1'
    with tempfile.TemporaryDirectory(prefix='PrintLab 发布 ZIP ') as temporary:
        target = Path(temporary) / 'PrintLab'
        with zipfile.ZipFile(bundle) as archive:
            assert all(n.startswith('PrintLab/') and '..' not in Path(n).parts for n in archive.namelist())
            assert not any(n.startswith(('PrintLab/Runtime/','PrintLab/Project/')) for n in archive.namelist())
            required = {'Harness/printlab/preview_recovery.py', 'Harness/tools/recover_studio_covers.py',
                        'docs/PREVIEW_RECOVERY.md', 'Harness/tests/test_preview_recovery.py'}
            assert required <= {name.removeprefix('PrintLab/') for name in archive.namelist()}
            assert not any('/PrintHistory/' in name or name.endswith(('.3mf', '.stl', '.step', '.blend'))
                           or '/node_modules/' in name or '/vendor/' in name for name in archive.namelist())
            archive.extractall(temporary)
            if sys.platform != 'win32':
                for info in archive.infolist():
                    if not info.is_dir():
                        (Path(temporary) / info.filename).chmod((info.external_attr >> 16) & 0o777 or 0o644)
        subprocess.run([sys.executable, 'scripts/setup.py'], cwd=target, env=env, check=True, timeout=600)
        python = target / ('Runtime/venv/Scripts/python.exe' if sys.platform == 'win32' else 'Runtime/venv/bin/python')
        cli = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(target / 'Harness/bin/printlab.ps1')] if sys.platform == 'win32' else [str(target / 'Harness/bin/printlab')]
        subprocess.run([*cli, 'context'], cwd=target, env=env, check=True, timeout=60, stdout=subprocess.DEVNULL)
        # Real default inspector, not an injected successful return.
        subprocess.run([str(python), '-m', 'pytest', 'Harness/tests/test_public_inspector.py', 'Harness/tests/test_preview_recovery.py', '-q'],
                       cwd=target, env=env, check=True, timeout=180)
        subprocess.run([str(python), 'scripts/verify_onboarding.py'], cwd=target, env=env, check=True, timeout=120)
        config = target / 'Runtime/config.json'
        original = config.read_bytes()
        subprocess.run([str(python), 'scripts/init_workspace.py'], cwd=target, env=env, check=True, timeout=60)
        assert config.read_bytes() == original
        assert (target / '.agents/skills/printlab/SKILL.md').is_file()
        result = {'ok':True, 'commit':commit, 'zip_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
                  'fresh_environment':True, 'unicode_path':True, 'configuration_preserved':True,
                  'real_offline_inspector':True, 'printer_contacted':False,
                  'scope':'ZIP installation, CLI onboarding and real inspection; GUI/device boundaries simulated'}
        (output / 'release-install.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))


if __name__ == '__main__':
    main()
