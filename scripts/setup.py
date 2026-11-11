"""Install the workbench into this checkout on macOS or Windows."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def run(command, directory=ROOT):
    subprocess.run(command, cwd=directory, check=True)


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11 or newer is required.')
    os.environ['PYTHONUTF8'] = '1'
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not node or not npm:
        raise SystemExit('Install Node.js 22 or newer, including npm, then rerun setup.')
    run([node, '-e', 'if (Number(process.versions.node.split(".")[0]) < 22) process.exit(1)'])
    environment = ROOT / 'Runtime/venv'
    python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.is_file():
        run([sys.executable, '-m', 'venv', str(environment)])
    run([str(python), '-m', 'pip', 'install', '--require-hashes', '-r', 'scripts/requirements.lock'])
    run([str(python), '-m', 'pip', 'install', '--no-deps', '-e', './Harness'])
    npm_command = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', npm] if sys.platform == 'win32' else [npm]
    for arguments in (['ci'], ['run', 'build']):
        run([*npm_command, *arguments], ROOT / 'Harness/studio')
    run([str(python), '-X', 'utf8', 'scripts/init_workspace.py'])
    run([str(python), '-X', 'utf8', 'scripts/install_inspector.py'])
    print('PrintLab installed. Run scripts/start.ps1 on Windows or bash scripts/start.sh on macOS.')


if __name__ == '__main__':
    main()
