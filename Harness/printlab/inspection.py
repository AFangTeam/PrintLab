"""File-only checks via an independently installed upstream MCP server.

No printer credentials, approval, dispatch tools or private patches are provided.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import re
import zipfile
from . import core

VERSION = '1.1.33'


def artifact_model(artifact, job):
    model = job.get('sliced_printer_model')
    if not model:
        if artifact.name.lower().endswith('.3mf'):
            with zipfile.ZipFile(artifact) as archive:
                member = archive.getinfo('Metadata/project_settings.config')
                if member.file_size > 16 * 1024 * 1024:
                    raise core.WorkflowError('Oversized machine configuration')
                model = json.loads(archive.read(member)).get('printer_model')
        else:
            with artifact.open('rb') as stream:
                header = stream.read(1024 * 1024).decode('utf-8', errors='replace')
            match = re.search(r'^;\s*printer_model\s*=\s*([^\r\n]+)', header, re.M)
            model = match[1] if match else None
    from .machine_profiles import model_id
    selected = {'X1 CARBON': 'x1c'}.get(model_id(model), model_id(model).lower().replace(' ', ''))
    if selected not in {'p1s', 'p1p', 'p2s', 'x1c', 'x1e', 'a1', 'a1mini', 'h2d', 'h2s', 'h2c', 'x2d'}:
        raise core.WorkflowError('Independent inspection requires an identified supported printer model')
    return selected


def inspect(jd, job, *, timeout=90):
    from .native import _terminate_group
    # Implementation lives with the package, even when PRINTLAB_ROOT is a test workspace.
    harness = Path(__file__).resolve().parent.parent
    entry = harness.parent / 'Runtime/third-party/bambu-inspector/node_modules/bambu-printer-mcp/dist/index.js'
    node = shutil.which('node')
    if not node or not entry.is_file():
        raise core.WorkflowError('离线检查器未安装。运行 python scripts/install_inspector.py 后重试检查；未发送打印。')
    artifact = core.safe_path(jd, job['artifact'])
    plate = job.get('plate')
    if type(plate) is not int or plate < 1:
        raise core.WorkflowError('检查需要明确的正整数盘号')
    with tempfile.TemporaryDirectory(prefix='PrintLab inspect ') as temporary:
        directory = Path(temporary)
        snapshot = directory / ('artifact' + artifact.suffix)
        shutil.copyfile(artifact, snapshot)
        digest = core.digest(snapshot)
        if digest != job['artifact_sha256']:
            raise core.WorkflowError('打印文件与登记 SHA-256 不符')
        model = artifact_model(snapshot, job)
        # Empty home/cwd prevent dotenv and user runtime configuration leaking in.
        env = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC'}}
        env.update(HOME=temporary, USERPROFILE=temporary, TMP=temporary, TEMP=temporary, TMPDIR=temporary,
                   MCP_TRANSPORT='stdio')
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == 'win32' else {'start_new_session': True}
        process = subprocess.Popen([node, str(harness / 'inspect-mcp.mjs'), str(entry), str(snapshot), str(plate - 1), model],
                                   cwd=temporary, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', **options)
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            _terminate_group(process)
            raise core.WorkflowError('离线检查超时或中断，未发送打印。') from None
        try:
            if len(stdout) > 4 * 1024 * 1024:
                raise ValueError('oversized response')
            receipt = json.loads(stdout)
            if process.returncode or receipt.get('error'):
                raise ValueError(receipt.get('error', 'inspector process failed'))
            if (receipt.get('receipt_version') != '1' or receipt.get('evidence') != 'file-only'
                    or receipt.get('dispatch_authorized') is not False
                    or receipt.get('artifact', {}).get('sha256') != digest
                    or receipt.get('artifact', {}).get('byte_length') != snapshot.stat().st_size
                    or receipt.get('selection', {}).get('bambu_model') != model
                    or receipt.get('selection', {}).get('plate_index') != plate - 1
                    or receipt.get('inspection', {}).get('sha256') != digest):
                raise ValueError('inspection evidence does not match the selected file and plate')
            if core.digest(artifact) != digest:
                raise ValueError('file changed during inspection')
        except (ValueError, TypeError, AttributeError) as error:
            raise core.WorkflowError(f'独立离线检查失败：{error}') from None
        return {'ok': True, 'executed': False, 'phase': 'offline_inspection',
                'inspection': receipt['inspection'], 'receipt': receipt, 'inspector_version': VERSION}


def self_test():
    """Verify the installed public tool with disposable synthetic data, never dispatch."""
    with tempfile.TemporaryDirectory(prefix='PrintLab inspector selftest ') as temporary:
        directory = Path(temporary)
        artifact = directory / 'probe.gcode'
        artifact.write_text(
            '; synthetic self-test; never print\n; printer_model = Bambu Lab X2D\n'
            '; nozzle_diameter = 0.4,0.4\n; nozzle_type = hardened_steel,hardened_steel\n'
            '; filament_type = PETG\n; filament_map = 1\n; physical_extruder_map = 1,0\n'
            'M620 S0A\nT0\nM621 S0A\nM109 T1 S240\nG1 X10 Y10 E1\nM104 S0\n', encoding='utf-8')
        result = inspect(directory, {'artifact':artifact.name, 'artifact_sha256':core.digest(artifact), 'plate':1}, timeout=30)
        return {'available': True, 'version': VERSION, 'verified': 'public MCP file inspection',
                'executed':False, 'scope':'synthetic file only; no printer or official profiles tested'}
