import json
from pathlib import Path
import shutil

import pytest
from printlab import cli, core, bambuddy, studio_bridge


def test_project_team_is_copied_and_loaded_by_a_later_context(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2]
    shutil.copytree(source / 'Templates', tmp_path / 'Templates')
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    monkeypatch.setattr(bambuddy, 'inventory', lambda: {'items': []})
    (tmp_path / 'Context').mkdir()
    (tmp_path / 'Context/team.md').write_text('Workspace team entry', encoding='utf-8')
    project = core.new_project('Team test')
    directory = core.project_path(project['id'])
    team = directory / 'Review/team.md'
    assert 'Sara' in team.read_text(encoding='utf-8')
    team.write_text('Mike owns the tool check for this project', encoding='utf-8')
    result = core.context(project['id'])
    assert 'Context/team.md' in result['loaded']
    assert any(d['path'].endswith('/Review/team.md') and 'Mike' in d['text'] for d in result['documents'])


@pytest.mark.parametrize('action', ['build', 'capability', 'permissions'])
def test_documented_studio_bridge_command_dispatches_only_selected_action(action, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(studio_bridge, 'build_helper', lambda: calls.append('build') or Path('/synthetic/Helper.app'))
    monkeypatch.setattr(studio_bridge, 'capability', lambda: calls.append('capability') or {'available': False})
    monkeypatch.setattr(studio_bridge, 'setup_permissions', lambda: calls.append('permissions') or {'requested': True, 'printed': False})
    assert cli.main(['studio-bridge', action]) == 0
    assert calls == [action]
    assert isinstance(json.loads(capsys.readouterr().out), dict)
