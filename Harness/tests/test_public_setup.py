"""Public distribution portability and first-run regressions."""
import importlib.util
from pathlib import Path
import shutil
import sys
from printlab import platforms
import pytest

from printlab import core, history, native, studio_bridge

SOURCE = Path(__file__).resolve().parents[2]


def test_initializer_preserves_local_data_and_uses_new_root(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('init_workspace', SOURCE / 'scripts/init_workspace.py')
    initializer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(initializer)
    monkeypatch.setattr(initializer, 'ROOT', tmp_path)
    shutil.copytree(SOURCE / 'config', tmp_path / 'config')
    initializer.main()
    config = tmp_path / 'Runtime/config.json'
    assert core.read_json(config)['cad_python'] == str(platforms.venv_python(tmp_path / 'Runtime/venv'))
    private = tmp_path / 'Runtime/private/bambuddy.json'
    if sys.platform != 'win32':
        assert private.stat().st_mode & 0o777 == 0o600
    config.write_text('{"printer_id": 42}')
    profile = tmp_path / 'Context/profile.md'
    profile.write_text('My local choices')
    initializer.main()
    assert core.read_json(config) == {'printer_id': 42}
    assert profile.read_text() == 'My local choices'
    assert list((tmp_path / 'Project').iterdir()) == []


def test_studio_display_name_comes_from_local_configuration(monkeypatch):
    monkeypatch.setattr(core, 'config', lambda: {'studio_printer_name': '  My Printer  '})
    assert studio_bridge.display_name() == 'My Printer'
    monkeypatch.setattr(core, 'config', lambda: {})
    with pytest.raises(core.WorkflowError, match='studio_printer_name'):
        studio_bridge.display_name()


def test_uninstalled_native_adapter_fails_before_creating_a_process(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    def unexpected(*args, **kwargs):
        pytest.fail('An uninstalled adapter must never create a process')
    monkeypatch.setattr(native.subprocess, 'Popen', unexpected)
    with pytest.raises(core.WorkflowError, match='docs/PRINTING.md'):
        native.run_client(tmp_path, {}, 'print')


def test_unconfigured_history_has_no_connection_error_or_network_call(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    def unexpected():
        pytest.fail('An unconfigured workspace must never contact a printer')
    result = history.view(client_factory=unexpected)
    assert result['state'] == 'unconfigured'
    assert result['stale'] is False
    assert result['items'] == []


def test_custom_port_keeps_same_origin_validation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from printlab.api import app
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    monkeypatch.setenv('PRINTLAB_STUDIO_PORT', '18018')
    client = TestClient(app, base_url='http://127.0.0.1:18018')
    assert client.get('/api/prepared/session').status_code == 200
    assert client.get('/api/prepared/session', headers={'Host': 'evil.example:18018'}).status_code == 403
    assert client.get('/api/prepared/session', headers={'Origin': 'http://localhost:18018'}).status_code == 403


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS sender adapter')
def test_missing_sender_is_reported_as_unavailable(monkeypatch):
    def missing(*args, **kwargs):
        raise core.WorkflowError('发送助手未安装')
    monkeypatch.setattr(studio_bridge, '_run', missing)
    result = studio_bridge.capability()
    assert result['available'] is False
    assert result['message'] == '发送助手未安装'
