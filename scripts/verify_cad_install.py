"""Independent Text-to-CAD install and real geometry/export smoke test.

Downloads upstream wheels; does not install plugins into any personal Agent app.
Generated geometry lives only in a temporary directory, never in the release.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import venv

ROOT = Path(__file__).resolve().parent.parent
VERSION = '0.11.9'


def main():
    output = ROOT / 'Runtime/verification'
    output.mkdir(parents=True, exist_ok=True)
    bootstrap = ROOT / 'Runtime/third-party/cad-bootstrap'
    python = bootstrap / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(bootstrap)
    subprocess.run([str(python), '-m', 'pip', 'install', 'uv==0.10.7'], check=True, timeout=180)
    with tempfile.TemporaryDirectory(prefix='PrintLab CAD 中文 ') as temporary:
        root = Path(temporary)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        env = {k:v for k,v in os.environ.items() if not k.startswith(('CAD_', 'PRINTLAB_')) and k not in {'PYTHONPATH','VIRTUAL_ENV'}}
        env.update(CAD_STATE_DIR=str(root/'state'), CAD_CACHE_DIR=str(root/'cache'),
                   CAD_LAUNCHER_DIR=str(root/'bin'), CAD_ENGINE_DIR=str(root/'engine'),
                   CAD_ENGINE_PORT=str(port), PYTHONUTF8='1')
        command = [str(python), '-m', 'uv', 'tool', 'run', '--no-config', '--managed-python',
                   '--python', '3.14', '--from', f'cad-server=={VERSION}', 'cad']
        def cad(*args, timeout=600):
            result = subprocess.run([*command,*args], cwd=root, env=env, text=True, encoding='utf-8',
                                    capture_output=True, timeout=timeout)
            # Keep only local diagnostic logs; do not display generated viewer tokens.
            with (output/'cad-install.log').open('a',encoding='utf-8') as log:
                import re
                log.write(re.sub(r'(?i)(token=)[^\s&"<>]+', r'\1[redacted]', result.stdout+result.stderr))
            if result.returncode:
                raise RuntimeError(f'Text-to-CAD {args[0]} failed; see Runtime/verification/cad-install.log')
            return result.stdout
        source = root/'probe.py'
        source.write_text('''import math
import build123d as bd
from cad import model

@model
def installation_probe():
    solid = bd.Box(12,18,4) - bd.Cylinder(2,4)
    assert abs(solid.volume - (12*18*4 - math.pi*2*2*4)) < 0.001
    assert solid.is_valid
    return solid

if __name__ == '__main__':
    document = installation_probe()
    document.export('probe.step')
    document.export('probe.stl')
''', encoding='utf-8')
        engine = None
        engine_log = (output/'cad-engine.log').open('w', encoding='utf-8')
        try:
            cad('telemetry','off')
            cad('update','auto','off')
            engine = subprocess.Popen([*command,'server','--port',str(port)], cwd=root, env=env, stdout=engine_log, stderr=engine_log)
            for attempt in range(120):
                if engine.poll() is not None:
                    raise RuntimeError('Isolated CAD engine exited; see cad-engine.log')
                try:
                    with socket.create_connection(('127.0.0.1',port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.25)
            else:
                raise RuntimeError('Isolated CAD engine startup timed out')
            cad('run',str(source))
            assert (root/'probe.step').stat().st_size > 100
            assert (root/'probe.stl').stat().st_size > 100
            report = {'ok':True, 'cad_server':VERSION, 'geometry':'analytic volume and validity asserted',
                      'exports':['STEP','STL'], 'isolated_state':True, 'agent_plugin_installed':False,
                      'sliced':False, 'printer_contacted':False}
            (output/'cad-install.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
        finally:
            try:
                cad('stop',timeout=60)
            finally:
                if engine and engine.poll() is None:
                    engine.terminate()
                    engine.wait(timeout=30)
                engine_log.close()


if __name__ == '__main__':
    main()
