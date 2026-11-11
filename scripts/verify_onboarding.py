"""Exercise documented onboarding entry points in a temporary empty workspace."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def run_json(command, workspace, environment):
    result = subprocess.run(command, cwd=workspace, env=environment, text=True,
                            capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return json.loads(result.stdout)


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='PrintLab onboarding ') as temporary:
        workspace = Path(temporary).resolve()
        for name in ('Templates', 'config'):
            shutil.copytree(ROOT / name, workspace / name)
        (workspace / 'Context').mkdir()
        for name in ('workflow.md', 'lessons.md', 'image-to-print.md'):
            shutil.copy2(ROOT / 'Context' / name, workspace / 'Context' / name)
        shutil.copy2(ROOT / 'AGENTS.md', workspace / 'AGENTS.md')
        (workspace / 'scripts').mkdir()
        shutil.copy2(ROOT / 'scripts/init_workspace.py', workspace / 'scripts/init_workspace.py')
        environment = {**os.environ, 'PRINTLAB_ROOT': str(workspace),
                       'PYTHONPATH': str(ROOT / 'Harness'), 'PYTHONUTF8': '1'}
        subprocess.run([sys.executable, str(workspace / 'scripts/init_workspace.py')],
                       env=environment, check=True, capture_output=True, timeout=30)
        command = [sys.executable, '-X', 'utf8', '-m', 'printlab.cli']
        initial = run_json([*command, 'context'], workspace, environment)
        assert initial['missing'] == [], initial['missing']
        assert 'Context/team.md' in initial['loaded']
        assert str(workspace) in (workspace / 'Context/team.md').read_text(encoding="utf-8")
        checks.append('empty_workspace_and_team_initialized')

        project = run_json([*command, 'new', '入门验收挂钩', '--kind', 'functional',
                            '--brief', '验收数据，桌板尺寸待测量', '--summary', '临时入门验收'],
                           workspace, environment)
        pid = project['id']
        directory = workspace / 'Project' / f"{pid}-{project['slug']}"
        team = directory / 'Review/team.md'
        assert team.is_file()
        team.write_text(team.read_text(encoding="utf-8") + '\n验收模拟分工：Sara 核对材料，Mike 检查工具，任务小组整理需求。\n', encoding="utf-8")
        checks.append('project_created_with_team_template')

        first = run_json([*command, 'handoff', pid, '--note',
                          '验收模拟 Sara 交接：材料条件仍待使用者确认。'], workspace, environment)
        resumed = run_json([*command, 'context', pid], workspace, environment)
        contents = {d['path']: d['text'] for d in resumed['documents']}
        prefix = directory.relative_to(workspace).as_posix()
        assert 'Sara' in contents[f'{prefix}/{first["latest_session"]}']
        assert 'Mike' in contents[f'{prefix}/Review/team.md']
        second = run_json([*command, 'handoff', pid, '--note',
                           '验收模拟任务小组接续：已读取 Sara 交接，下一步补齐尺寸。'],
                          workspace, environment)
        final = run_json([*command, 'context', pid], workspace, environment)
        assert f'{prefix}/{second["latest_session"]}' in final['loaded']
        assert (directory / first['latest_session']).is_file()
        assert len(list((workspace / 'Project').iterdir())) == 1
        checks.append('fresh_cli_process_resumes_same_project_and_latest_handoff')

        api_probe = '''
import json
from fastapi.testclient import TestClient
from printlab.api import app
client = TestClient(app, base_url='http://127.0.0.1:8018')
assert client.get('/api/health').json()['ok']
rows = client.get('/api/projects').json()['projects']
assert len(rows) == 1
pid = rows[0]['id']
project = client.get('/api/projects/' + pid).json()
assert '桌板尺寸待测量' in project['brief']
assert any(f['path'] == 'Review/team.md' for f in project['files'])
assert 'Mike' in client.get('/api/files/' + pid + '/Review/team.md').text
assert client.get('/api/device').json()['state'] == 'unconfigured'
assert client.get('/api/prepared').json()['items'] == []
assert client.get('/api/prepared/sender/capability').status_code == 200
print(json.dumps({'ok': True}))
'''
        assert run_json([sys.executable, '-c', api_probe], workspace, environment)['ok']
        checks.append('workbench_api_exposes_project_brief_team_and_unconfigured_device')
        for filename in ('approval.json', 'dispatch.json'):
            assert list(workspace.rglob(filename)) == []
        assert list((directory / 'Print').iterdir()) == []
        checks.append('empty_print_queue_and_no_dispatch_receipt')
    print(json.dumps({'ok': True, 'checks': checks, 'workspace': 'temporary_and_removed',
                      'scope': 'CLI subprocesses and in-process HTTP API; physical tools and host chat creation require local verification'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
