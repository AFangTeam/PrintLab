"""Verify the actual server and browser using a temporary synthetic project."""
import json
import datetime as dt
import io
from PIL import Image
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main():
    output = ROOT / 'Runtime/verification'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='PrintLab browser 中文 ') as temporary:
        workspace = Path(temporary).resolve()
        for name in ('Context', 'config', 'Templates'):
            shutil.copytree(ROOT / name, workspace / name)
        (workspace / 'Harness/studio').mkdir(parents=True)
        shutil.copytree(ROOT / 'Harness/studio/dist', workspace / 'Harness/studio/dist')
        shutil.copy2(ROOT / 'AGENTS.md', workspace / 'AGENTS.md')
        environment = {**os.environ, 'PRINTLAB_ROOT': str(workspace), 'PYTHONUTF8': '1',
                       'PYTHONPATH': str(ROOT / 'Harness')}
        command = [sys.executable, '-X', 'utf8', '-m', 'printlab.cli']
        created = subprocess.check_output([*command, 'new', 'Windows 中文工作流验收',
                                          '--brief', '验证用途与尺寸记录'], env=environment)
        project = json.loads(created)
        # Synthetic recovered images exercise the real document route and Gallery rendering.
        preview_dir = workspace / 'Library/References/PrintHistory/CloudPreviews'
        preview_dir.mkdir(parents=True)
        image = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(image, format='PNG')
        (preview_dir / 'fixture.png').write_bytes(image.getvalue())
        config_path = workspace / 'Runtime/config.json'
        config = {}
        config['printer_id'] = 2
        config_path.write_text(json.dumps(config), encoding='utf-8')
        rows = [{'id': f'archive-{i}', 'archive_id': i, 'printer_id': 2, 'name': kind,
                 'status': 'completed', 'is_print_event': True,
                 'model_preview': {'kind': kind, 'url': '/api/documents/Library/References/PrintHistory/CloudPreviews/fixture.png'}}
                for i, kind in enumerate(['cloud_plate', 'reference_plate', 'sliced_plate'], 1)]
        cache = workspace / 'Runtime/history/latest.json'
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({'printer_id': 2, 'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                                     'items': rows, 'counts': {'prints': 3}, 'coverage': {'cloud_history_synced': False}}), encoding='utf-8')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        log = (output / 'server.log').open('w', encoding='utf-8')
        process = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'Harness/serve.py'),
                                    'studio', '--port', str(port)], env=environment, stdout=log, stderr=log)
        base = f'http://127.0.0.1:{port}'
        try:
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Server exited before becoming healthy')
                try:
                    with urllib.request.urlopen(base + '/api/health', timeout=1) as response:
                        assert json.load(response)['ok']
                    break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError('Server startup timed out')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                failures = []
                page.on('pageerror', lambda error: failures.append(str(error)))
                page.goto(base)
                page.get_by_role('heading', name='把想法，做成实物。', exact=True).wait_for()
                page.get_by_role('heading', name='我的打印图册', exact=True).scroll_into_view_if_needed()
                page.get_by_text('配置板预览', exact=True).wait_for()
                page.get_by_text('原模型参考', exact=True).wait_for()
                page.get_by_text('切片模型预览', exact=True).wait_for()
                page.wait_for_function("Array.from(document.querySelectorAll('.gallery-cover img')).filter(i => i.complete && i.naturalWidth === 8).length === 3")
                page.screenshot(path=str(output / 'recovered-previews.png'), full_page=True, animations='disabled')
                checked = []
                for route, title in [('onboarding', '配置与队伍'), ('projects', '项目图册'), ('prepared', '待打印'),
                                     ('history', '每一次打印，都在这里。'), ('favorites', '灵感收藏'),
                                     ('shop', '购物清单'), ('library', '资料与经验'), ('device', '设备与材料')]:
                    page.goto(base + '/#/' + route)
                    page.get_by_role('heading', name=title, exact=True).wait_for()
                    checked.append(route)
                page.goto(base + '/#/onboarding')
                page.get_by_role('heading', name='Sarah · 3D 打印顾问', exact=True).wait_for()
                page.get_by_role('heading', name='Mike · 工作流设计师', exact=True).wait_for()
                assert page.get_by_role('button', name='让 Agent 接着配置').count() == 1
                page.get_by_role('button', name='Context/profile.md', exact=True).click()
                page.get_by_role('dialog').wait_for()
                assert '加载失败' not in page.get_by_role('dialog').inner_text()
                page.keyboard.press('Escape')
                page.screenshot(path=str(output / 'onboarding-desktop.png'), full_page=True, animations='disabled')
                page.goto(base + '/#/projects/' + project['id'])
                page.get_by_role('heading', name='Windows 中文工作流验收', exact=True).wait_for()
                assert '验证用途与尺寸记录' in page.locator('main').inner_text()
                page.screenshot(path=str(output / 'project-desktop.png'), full_page=True, animations='disabled')
                page.goto(base + '/#/prepared')
                if sys.platform == 'win32':
                    page.get_by_role('heading', name='Windows 发送通道').wait_for()
                    assert page.get_by_role('button', name='启用发送助手', exact=True).count() == 0
                page.screenshot(path=str(output / 'prepared-desktop.png'), full_page=True, animations='disabled')
                page.set_viewport_size({'width': 390, 'height': 844})
                page.goto(base + '/#/onboarding')
                page.get_by_role('heading', name='配置与队伍', exact=True).wait_for()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(output / 'onboarding-mobile.png'), full_page=True, animations='disabled')
                page.goto(base + '/#/projects')
                page.get_by_role('heading', name='项目图册', exact=True).wait_for()
                page.screenshot(path=str(output / 'projects-mobile.png'), full_page=True, animations='disabled')
                assert failures == [], failures
                browser.close()
            result = {'ok': True, 'os': platform.platform(), 'python': sys.version,
                      'pages': checked, 'unicode_project': True, 'recovered_preview_images': 3, 'browser_errors': failures,
                      'printing': 'synthetic data only'}
            (output / 'browser.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False))
        finally:
            process.terminate()
            process.wait(timeout=20)
            log.close()


if __name__ == '__main__':
    main()
    subprocess.run([sys.executable, str(ROOT / 'scripts/verify_prepared_browser.py')], check=True)
