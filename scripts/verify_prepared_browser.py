"""Click the real prepared-print UI against real checks and simulated device/GUI edges."""
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest
import uvicorn
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'Harness/tests'))
from test_prepared import setup
from test_public_inspector import configure_prepared
from printlab import bambuddy, core, studio_bridge


def main():
    output = ROOT / 'Runtime/verification'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='PrintLab browser print ') as temporary, pytest.MonkeyPatch.context() as patch:
        workspace = Path(temporary)
        (workspace/'Harness/studio').mkdir(parents=True)
        shutil.copytree(ROOT/'Harness/studio/dist', workspace/'Harness/studio/dist')
        fixture = setup.__wrapped__(workspace, patch)
        configure_prepared(fixture, patch)
        project_dir, job_dir, job, device, *_ = fixture
        preview = Image.new('RGB', (480, 360), '#eaf0e7')
        ImageDraw.Draw(preview).text((40, 170), 'SYNTHETIC TEST - NO PRINT', fill='#26382b')
        preview.save(project_dir/'Preview/v001/cover.png')
        job = core.read_json(job_dir/'job.json')
        job['source_hashes'] = core.revision_files(project_dir, 'v001')
        core.write_json(job_dir/'job.json', job)
        original_get = device.get
        device.close = lambda: None
        def get(path):
            device.live['last_ams_update'] = time.time()
            if path == 'printers/7':
                return {'serial_number':'SYNTHETIC'}
            if path.startswith(('archives/?', 'print-log/?')):
                return []
            return original_get(path)
        device.get = get
        patch.setattr(bambuddy, 'Client', lambda **kwargs: device)
        if sys.platform == 'darwin':
            patch.setattr(studio_bridge, 'capability', lambda *args: {
                'available':True, 'message':'Simulated desktop helper',
                'observation':{'accessibility':True,'screen_capture':True}})
        patch.setattr(studio_bridge, '_open_prepared', lambda *args: (123, {'sha256':'synthetic-screen'}, {}))
        patch.setattr(studio_bridge, '_studio_serial_matches', lambda *args: True)
        sends = []
        def send(command, *args, **kwargs):
            assert command == 'send-once'
            assert not core.read_json(job_dir/'dispatch.json')['command_sent']
            sends.append(command)
            return {'command_sent':True,'executed':False}
        patch.setattr(studio_bridge, '_run', send)
        patch.setattr(bambuddy, 'reconcile', lambda *args, **kwargs: {
            'matching_task':False,'fresh':True,'device_state':'FINISH'})
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port = listener.getsockname()[1]
        patch.setenv('PRINTLAB_STUDIO_PORT',str(port))
        from printlab.api import app
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for attempt in range(100):
                if server.started:
                    break
                if not thread.is_alive():
                    raise RuntimeError('Fixture server exited')
                time.sleep(.1)
            else:
                raise RuntimeError('Fixture server startup timed out')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width':1440,'height':1100})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}/#/prepared')
                page.locator('main img').evaluate('(image) => image.decode()')
                page.get_by_role('button',name='核验设备与材料',exact=True).click()
                if sys.platform == 'darwin':
                    page.get_by_role('heading',name='核验通过',exact=True).wait_for()
                    button = page.get_by_role('button',name='启动打印',exact=True)
                    expect(button).to_be_disabled()
                    page.get_by_role('checkbox').check()
                    expect(button).to_be_enabled()
                    page.screenshot(path=str(output/'prepared-ready.png'),full_page=True)
                    button.click()
                    page.get_by_text('已提交，等待设备确认',exact=True).wait_for(timeout=30000)
                    assert sends == ['send-once']
                    assert core.read_json(job_dir/'official-inspection.json')['receipt']['evidence'] == 'file-only'
                    page.reload()
                    page.get_by_text('已提交，等待设备确认',exact=True).wait_for()
                    assert page.get_by_role('button',name='启动打印',exact=True).count() == 0
                    assert sends == ['send-once']
                else:
                    page.get_by_role('heading',name='暂时不能启动',exact=True).wait_for()
                    assert page.get_by_role('button',name='启动打印',exact=True).count() == 0
                    assert not sends
                page.screenshot(path=str(output/'prepared-result.png'),full_page=True)
                assert not errors, errors
                browser.close()
            report = {'ok':True, 'os':sys.platform, 'real_browser_click':True, 'real_file_inspection':True,
                      'simulated_gui_send_count':len(sends), 'printer_contacted':False, 'browser_errors':errors,
                      'windows_sender_blocked':sys.platform != 'darwin'}
            (output/'prepared-browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
        finally:
            server.should_exit = True
            thread.join(timeout=20)
            assert not thread.is_alive(), 'Fixture server did not stop'


if __name__ == '__main__':
    main()
