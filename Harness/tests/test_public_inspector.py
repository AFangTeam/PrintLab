"""Runs the independently installed, unmodified upstream MCP process; no printer."""
import json
from pathlib import Path
import zipfile
import pytest
from printlab import core, native


def artifact(tmp_path, *, temperature=240):
    settings = {'printer_model': 'Bambu Lab X2D', 'nozzle_diameter': ['0.4', '0.4'],
                'nozzle_type': ['hardened_steel', 'hardened_steel'], 'filament_type': ['PETG'],
                'curr_bed_type': 'Textured PEI Plate'}
    gcode = ('; synthetic test data: never dispatch\n; filament_map = 1\n'
             '; physical_extruder_map = 1,0\nM620 S0A\nT0\nM621 S0A\n'
             f'M109 T1 S{temperature}\nM140 S70\nG1 X10 Y10 Z0.2 E1\nM104 S0\nM140 S0\n')
    filename = tmp_path / 'synthetic.gcode.3mf'
    with zipfile.ZipFile(filename, 'w') as archive:
        archive.writestr('Metadata/project_settings.config', json.dumps(settings))
        archive.writestr('Metadata/plate_1.gcode', gcode)
    return {'artifact': filename.name, 'artifact_sha256': core.digest(filename), 'plate': 1}


def test_real_public_mcp_inspector(tmp_path):
    job = artifact(tmp_path)
    result = native.run_client(tmp_path, job, 'inspect', timeout=30)
    assert result['ok'] and result['executed'] is False
    assert result['inspection']['nozzleDiameters'] == [.4, .4]
    assert result['inspection']['sha256'] == job['artifact_sha256']
    assert result['receipt']['dispatch_authorized'] is False


def test_real_inspector_rejects_overheat(tmp_path):
    job = artifact(tmp_path, temperature=400)
    with pytest.raises(core.WorkflowError, match='temperature|Temperature|limit'):
        native.run_client(tmp_path, job, 'inspect', timeout=30)


def test_real_inspector_rejects_wrong_plate(tmp_path):
    job = artifact(tmp_path)
    job['plate'] = 2
    with pytest.raises(core.WorkflowError, match='plate 2'):
        native.run_client(tmp_path, job, 'inspect', timeout=30)


def test_inspector_refuses_changed_artifact_before_launch(tmp_path, monkeypatch):
    job = artifact(tmp_path)
    job['artifact_sha256'] = '0' * 64
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('must not launch'))
    with pytest.raises(core.WorkflowError, match='SHA-256'):
        native.run_client(tmp_path, job, 'inspect')

# Reuse only synthetic workspace/device data; run both real file inspectors.
from test_prepared import setup
from printlab import prepared, slicer_guard
REAL_ARCHIVE_CHECK = slicer_guard.assert_safe_archive


def test_prepared_check_uses_real_public_inspector(setup, monkeypatch):
    p, jd, job, device, unused_inspector, write_archive, settings = setup
    templates = {key: 'synthetic official template ' + key for key in slicer_guard.FIELDS}
    settings.update(templates)
    settings.update(filament_map=[1], printer_model='Bambu Lab X2D', nozzle_diameter=['0.4', '0.4'],
                    nozzle_type=['hardened_steel', 'hardened_steel'],
                    nozzle_temperature=[240], nozzle_temperature_initial_layer=[240])
    write_archive()
    with zipfile.ZipFile(jd / job['artifact']) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents['Metadata/plate_1.gcode'] = (
        '; synthetic: never dispatch\n; filament_map = 1\n; physical_extruder_map = 1,0\n'
        'M620 S0A\nT0\nM621 S0A\nM109 T1 S240\n; CHANGE_LAYER\nG1 X10 Y10 E1\n'
        'M104 S0\nM140 S0\n').encode()
    with zipfile.ZipFile(jd / job['artifact'], 'w') as archive:
        for name, content in contents.items(): archive.writestr(name, content)
    job['artifact_sha256'] = core.digest(jd / job['artifact'])
    core.write_json(jd / 'job.json', job)
    monkeypatch.setattr(slicer_guard, 'assert_safe_archive', REAL_ARCHIVE_CHECK)
    # Only official-profile discovery and live hardware are fixtures.
    monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    REAL_ARCHIVE_CHECK(jd / job['artifact'], 1)
    native.run_client(jd, job, 'inspect')
    prepared.register('P001', 'Jone', title='Synthetic integration')
    report = prepared.check('P001', 'Jone', client=device)
    assert report['ready'], report['blockers']
    assert next(row for row in report['checks'] if row['id'] == 'gcode')['status'] == 'pass'
    assert not (jd / 'approval.json').exists()
    assert not (jd / 'dispatch.json').exists()
