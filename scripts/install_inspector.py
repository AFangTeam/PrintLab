"""Download the separate upstream inspector from npm; never copy its source into PrintLab."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not npm:
        raise SystemExit('Install Node.js 22+ including npm, then rerun this command.')
    prefix = ROOT / 'Runtime/third-party/bambu-inspector'
    prefix.mkdir(parents=True, exist_ok=True)
    for name in ('package.json', 'package-lock.json'):
        shutil.copy2(ROOT / 'scripts/inspector-dependencies' / name, prefix / name)
    command = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', npm] if sys.platform == 'win32' else [npm]
    subprocess.run([*command, 'ci', '--prefix', str(prefix)], check=True)
    print('Independent inspector installed: bambu-printer-mcp 1.1.33 (GPL-2.0). No device connection or print attempted.')


if __name__ == '__main__':
    main()
