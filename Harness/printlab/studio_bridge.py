"""Session-independent, fail-closed bridge to official Bambu Studio.

The UI adapter is deliberately limited to the locally validated Chinese Studio
build, one main-nozzle AMS filament, and one Textured PEI plate. It preserves an
existing Studio project by opening a separate instance. No default probe opens
windows, reserves a job, or sends a command. A Send click is evidence of dispatch,
not evidence that the printer accepted or started the job.
"""
from __future__ import annotations

import datetime as dt
import json
import hashlib
import re
import subprocess
import time
import os
import plistlib
import shutil
import tempfile
import uuid
import sys
from pathlib import Path

from . import core, bambuddy, official

STUDIO_VERSION = '02.08.02.61'
BUNDLE = '/Applications/BambuStudio.app'
# This display identity is verified alongside the selected serial, not used as a serial.
def display_name():
    value = core.config().get('studio_printer_name')
    if not isinstance(value, str) or not value.strip():
        raise core.WorkflowError('请在 Runtime/config.json 设置 Studio 中显示的打印机名称 studio_printer_name')
    return value.strip()


class BeforeSendError(core.WorkflowError):
    """The final-click helper was never invoked; no print command was attempted."""
    verified_not_sent = True
    command_sent = False


HELPER_BUNDLE_ID = 'com.afang.printlab.studio-bridge'
HELPER_APP_NAME = 'PrintLab发送助手'


def _bundle_path():
    return Path('/Applications') / (HELPER_APP_NAME + '.app')


def _helper_path():
    return _bundle_path() / 'Contents/MacOS/StudioBridge'


def _build_manifest_path():
    return core.ROOT / 'Runtime/macos-build/studio-bridge-build.json'


def build_helper():
    """Build and install a dedicated local app; never requests privacy permission."""
    if sys.platform != "darwin":
        raise core.WorkflowError("发送助手构建需要 macOS。Windows 使用 docs/WINDOWS.md 中的官方 Studio 流程。")
    source = core.ROOT / 'Harness/macos/StudioBridge.swift'
    build_root = core.ROOT / 'Runtime/macos-build'
    build_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='studio-bridge-build-', dir=build_root) as temporary:
        built = Path(temporary) / (HELPER_APP_NAME + '.app')
        executable = built / 'Contents/MacOS/StudioBridge'
        executable.parent.mkdir(parents=True)
        resources = built / 'Contents/Resources'; resources.mkdir()
        subprocess.run(['/usr/bin/swiftc', str(source), '-o', str(executable)], check=True, capture_output=True, timeout=90)
        info={'CFBundleIdentifier':HELPER_BUNDLE_ID,'CFBundleName':HELPER_APP_NAME,'CFBundleDisplayName':HELPER_APP_NAME,
              'CFBundleExecutable':'StudioBridge','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.0',
              'CFBundleVersion':'1','LSMinimumSystemVersion':'14.0','LSUIElement':True,'NSHighResolutionCapable':True,
              'NSPrincipalClass':'NSApplication','NSHumanReadableCopyright':'PrintLab 本机发送桥，不包含账号或打印机凭据'}
        icon=core.ROOT/'Harness/macos/Assets/PrintLab.icns'
        if icon.is_file():
            shutil.copy2(icon,resources/'PrintLab.icns');info['CFBundleIconFile']='PrintLab'
        (built/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        subprocess.run(['/usr/bin/codesign','--force','--sign','-','--identifier',HELPER_BUNDLE_ID,
                        '-r',f'=designated => identifier "{HELPER_BUNDLE_ID}"',str(built)],check=True,capture_output=True,timeout=20)
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(built)],check=True,capture_output=True,timeout=20)
        installed=_bundle_path()
        if installed.exists():
            backup=build_root/('StudioBridge.previous-'+uuid.uuid4().hex[:8]+'.app')
            shutil.move(str(installed),backup)
        shutil.copytree(built,installed)
    core.write_json(_build_manifest_path(), {'source_sha256':core.digest(source),'binary_sha256':core.digest(_helper_path()),
        'info_sha256':core.digest(_bundle_path()/'Contents/Info.plist'),'bundle_id':HELPER_BUNDLE_ID,'app_path':str(_bundle_path()),'built_at':core.now()})
    return _bundle_path()


def _verify_bundle():
    manifest=core.read_json(_build_manifest_path(),{})
    source=core.ROOT/'Harness/macos/StudioBridge.swift'
    if (not _helper_path().is_file() or manifest.get('source_sha256') != core.digest(source)
            or manifest.get('binary_sha256') != core.digest(_helper_path())
            or manifest.get('info_sha256') != core.digest(_bundle_path()/'Contents/Info.plist')
            or manifest.get('bundle_id') != HELPER_BUNDLE_ID):
        raise core.WorkflowError('PrintLab发送助手未安装或发生变化，需要重新构建和验证')
    subprocess.run(['/usr/bin/codesign','--verify','--strict',str(_bundle_path())],check=True,capture_output=True,timeout=10)


def _run(*args, timeout=20):
    """Launch through LS so TCC belongs to the helper app, never uvicorn/Python."""
    _verify_bundle()
    ipc_root=core.ROOT/'Runtime/studio-bridge-ipc'
    ipc_root.mkdir(parents=True,exist_ok=True);ipc_root.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix='request-',dir=ipc_root) as temporary:
        private=Path(temporary);private.chmod(0o700)
        request=private/'request.json';response=private/'response.json'
        request_id=str(uuid.uuid4())
        payload=json.dumps({'request_id':request_id,'created_at':time.time(),'args':list(map(str,args))})
        fd=os.open(request,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(payload)
        process = subprocess.run(['/usr/bin/open','-n','-W','-a',str(_bundle_path()),'--args','--ipc',str(request),str(response)],
                                 check=False,capture_output=True,text=True,timeout=timeout)
        try:data=json.loads(response.read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError):
            detail = (process.stderr or '').strip()[:600]
            raise core.WorkflowError(f'发送助手没有返回有效回执（退出码 {process.returncode}）{": " + detail if detail else ""}') from None
        if not isinstance(data, dict):raise core.WorkflowError('发送助手回执格式无效')
        if data.get('request_id') != request_id:raise core.WorkflowError('发送助手回执不属于本次请求')
        if data.get('ok') is not True:raise core.WorkflowError(data.get('error','发送助手执行失败'))
        if process.returncode:raise core.WorkflowError(f'发送助手异常退出（退出码 {process.returncode}），执行结果仍需核实')
        return data


def setup_permissions():
    """Explicit user-only setup action. Do not call from capability or preflight.

    Launching requests the OS dialogs; it does not grant permission or print.
    The caller should later re-run capability to observe the user's OS choices.
    """
    if sys.platform != 'darwin':
        raise core.WorkflowError('此发送助手使用 macOS 系统接口。Windows 请按 docs/WINDOWS.md 交接到官方 Studio。')
    _verify_bundle()
    subprocess.run(['/usr/bin/open','-n','-a',str(_bundle_path()),'--args','request-permissions'],
                   check=True,capture_output=True,text=True,timeout=10)
    return {'requested':True,'printed':False,'granted':None,'requires_recheck':True,
            'app_name':HELPER_APP_NAME,'app_path':str(_bundle_path()),'bundle_id':HELPER_BUNDLE_ID,
            'message':'系统将为 PrintLab发送助手 请求辅助功能和屏幕读取权限；授权后回到工作台重新核验。'}


def _job_supported(job):
    m = job.get('mapping', {})
    reasons = []
    if m.get('transport') != 'bambu_studio': reasons.append('需要官方 Studio 发送副本')
    if job.get('plate') != 1: reasons.append('脚本当前仅验证单盘 plate 1')
    if m.get('use_ams') is not True or len(m.get('ams_mapping', [])) != 1: reasons.append('脚本当前仅验证单主料 AMS 路线')
    slots = m.get('ams_mapping', [])
    if len(slots) != 1 or type(slots[0]) is not int or not 0 <= slots[0] <= 7: reasons.append('AMS 槽位不在已验证范围 A1–B4')
    if m.get('extruder_mapping') != [1]: reasons.append('脚本当前仅验证左主喷嘴')
    if len(m.get('filament_types', [])) != 1 or m['filament_types'][0] not in {'PETG', 'PLA'}: reasons.append('脚本当前仅验证单种 PLA/PETG')
    if job.get('curr_bed_type') != 'Textured PEI Plate': reasons.append('脚本当前仅验证纹理 PEI 板')
    if job.get('sliced_printer_model') not in {'Bambu Lab X2D', 'X2D'}: reasons.append('脚本当前仅验证 X2D')
    return reasons


def capability(pid=None, jid=None):
    """Read-only live capability, optionally constrained to an exact job."""
    if sys.platform != 'darwin':
        message = 'Windows 使用官方 Bambu Studio 交接流程。核对具体任务并记录批准后，在 Studio 中确认发送，步骤见 docs/WINDOWS.md。'
        return {'available': False, 'setup_supported': False, 'message': message,
                'blockers': [message], 'transport': 'bambu_studio_manual'}
    blockers = []
    try:
        observed = _run('probe', timeout=10)
        if observed.get('helper_bundle_id') != HELPER_BUNDLE_ID: blockers.append('发送助手未通过专用 App 身份运行')
        if observed.get('studio_version') != STUDIO_VERSION: blockers.append('Studio 版本变更，需重新验证界面适配器')
        if not observed.get('accessibility'): blockers.append('PrintLab发送助手 尚未获得辅助功能权限')
        if not observed.get('screen_capture'): blockers.append('PrintLab发送助手 尚未获得屏幕读取权限')
        if not observed.get('session_on_console') or observed.get('screen_locked'): blockers.append('需要本机已登录且未锁屏的桌面会话')
        if pid is not None and jid is not None:
            job = core.read_json(core.job_path(pid,jid)/'job.json')
            blockers.extend(_job_supported(job))
            if (core.job_path(pid,jid)/'HOLD-DO-NOT-PRINT.md').exists(): blockers.append('该任务仍保留暂缓打印标记；需新的启动要求后解除，本轮不打印')
        return {'available': not blockers, 'message': '可通过本机 Studio 脚本发送；发送前仍逐项核验窗口和具体任务' if not blockers else '；'.join(blockers),
                'blockers': blockers, 'transport': 'bambu_studio_script', 'observation': observed,
                'limitations': ['仅已验证的中文 Studio 版本', '仅 X2D 单主料 AMS、左主喷嘴、纹理 PEI 单盘', '需要已登录且未锁屏桌面', '发送成功仍需设备读回，不自动重发']}
    except (core.WorkflowError, OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'available': False, 'message': str(exc), 'blockers': [str(exc)], 'transport': 'bambu_studio_script'}


def _studio_serial_matches(printer):
    config = Path.home() / 'Library/Application Support/BambuStudio/BambuStudio.conf'
    selected = core.read_json(config, {}).get('app', {}).get('user_last_selected_machine')
    return bool(printer.get('serial_number')) and selected == printer['serial_number']


def _green(token):
    # Ignore a neighboring selected button's border touching OCR bounding boxes.
    return token.get('green_pixels', 0) >= 60 and .15 < token.get('green_center_x', -1) < .85


def validate_snapshot(shot, job):
    """Pure validation, also exercised with observations from the real unsent dialog."""
    if shot.get('title') != '发送打印任务' or shot.get('active') is not True: raise core.WorkflowError('Studio 发送窗口不是当前活动窗口')
    bounds = shot.get('bounds', {})
    ratio_x = shot.get('width', 0) / max(bounds.get('Width', 0), 1)
    ratio_y = shot.get('height', 0) / max(bounds.get('Height', 0), 1)
    if not 0.9 <= ratio_x <= 3 or abs(ratio_x-ratio_y) > .02: raise core.WorkflowError('窗口截图与当前实际尺寸不一致')
    tokens = shot.get('tokens', [])
    texts = [t.get('text','') for t in tokens]
    if {'允许', '不允许', '打开系统设置'} & set(texts):
        raise core.WorkflowError('系统弹窗遮挡发送窗口，请先处理系统提示再继续')
    expected = job['id'] + '.gcode'
    jobs = [s.rstrip(' /') for s in texts if re.match(r'^J\d{8}-\d{6}-[a-z0-9]+\.gcode', s)]
    if jobs != [expected]: raise core.WorkflowError('发送窗口任务名不唯一或不匹配')
    if texts.count(display_name()) != 1 or texts.count('Bambu Lab X2D 0.4/0.4mm') != 1: raise core.WorkflowError('发送窗口打印机或喷嘴配置不匹配')
    m = job['mapping']; slot = m['ams_mapping'][0]
    wanted_slot = chr(ord('A')+slot//4) + str(slot%4+1)
    shown_slots = [(re.sub(r'[Vv∨▼⌄]+$', '',t['text']),t) for t in tokens if re.fullmatch(r'[A-D][1-4][Vv∨▼⌄]*', t['text'])]
    if len(shown_slots) != 1 or shown_slots[0][0] != wanted_slot or shown_slots[0][1]['x'] >= .5: raise core.WorkflowError('AMS 槽位或主辅喷嘴不匹配')
    materials = [t for t in tokens if t['text'] in {'PLA','PETG','ABS','ASA','TPU','PA','PC','Sup.PLA','Support'}]
    if len(materials) != 1 or materials[0]['text'] != m['filament_types'][0] or materials[0]['x'] >= .5: raise core.WorkflowError('窗口材料或喷嘴分组不匹配')
    if texts.count('PEI') != 1: raise core.WorkflowError('发送窗口未识别 PEI 板')
    for label, selected, side in [('延时摄影','关闭','left'),('动态流量校准','打开','left'),('自动热床调平','打开','right'),('喷嘴偏移校准','关闭','right')]:
        rows = [t for t in tokens if t['text'].startswith(label)]
        if len(rows) != 1: raise core.WorkflowError(f'无法核验{label}选项')
        row = rows[0]
        options = [t for t in tokens if abs(t['y']-row['y']) < .025 and (t['x'] < .5) == (side=='left') and selected in t['text'] and _green(t)]
        # Vision sometimes joins 自动 + 打开. Green text must be in the second half.
        options = [t for t in options if t['text'] == selected or (t['text']=='自动打开' and selected=='打开' and t['green_center_x']>.60)]
        if len(options) != 1: raise core.WorkflowError(f'{label}未处于要求的{selected}状态')
    sends = [t for t in tokens if t['text']=='发送' and t.get('confidence',0)>=.5 and _green(t) and t['y']>.85]
    if len(sends) != 1: raise core.WorkflowError('未识别唯一可用的发送按钮')
    return {'job_id':job['id'], 'display_name':display_name(), 'slot':wanted_slot, 'filament':m['filament_types'][0], 'snapshot_sha256':shot['sha256'], 'options_verified':True}


def _open_prepared(pid,jid):
    """Reversible GUI preparation. No approval, reservation, or Send click."""
    jd = core.job_path(pid,jid); job = core.read_json(jd/'job.json')
    cap = capability(pid,jid)
    if not cap['available']: raise core.WorkflowError(cap['message'])
    before = {i['pid'] for i in cap['observation'].get('instances',[])}
    artifact = core.safe_path(jd,job['artifact'])
    if core.digest(artifact) != job['artifact_sha256']: raise core.WorkflowError('Artifact changed')
    subprocess.run(['/usr/bin/open','-n','-a',BUNDLE,'--args',str(artifact)], check=True, timeout=10)
    target = None
    deadline = time.monotonic()+40
    while time.monotonic()<deadline:
        probe = _run('probe')
        matches = [i for i in probe.get('instances',[]) if i['pid'] not in before and any(w['title']==jid+'.gcode' for w in i['windows'])]
        if len(matches)==1:
            target=matches[0]['pid']; break
        if len(matches)>1: raise core.WorkflowError('Multiple new Studio instances; refusing to choose')
        time.sleep(.5)
    if target is None: raise core.WorkflowError('Studio did not load the exact job; no print sent')
    _run('open-panel',target,jid+'.gcode')
    time.sleep(1)
    shot = _run('inspect-panel',target,'发送打印任务')
    try:
        proof = validate_snapshot(shot,job)
    except core.WorkflowError as exc:
        # Only the timelapse setting is changed by this adapter. Other failures
        # must remain visible before any preparation click is attempted.
        if str(exc) != '延时摄影未处于要求的关闭状态':
            raise
        shot = _run('prepare-options',target,jid+'.gcode')
        proof = validate_snapshot(shot,job)
    return target,shot,proof


def _dispatch_impl(pid,jid,phase):
    """Send exactly once after the workbench created bound approval.

    Parent must retain its prepared-operation lock throughout this call. The
    bridge additionally owns a process-wide GUI lock. official.submit owns the
    printer ledger lock and reserves the task before the one-shot helper runs.
    """
    jd=core.job_path(pid,jid);job=core.read_json(jd/'job.json')
    if (jd/'HOLD-DO-NOT-PRINT.md').exists(): raise core.WorkflowError('This prepared job is on hold')
    if (jd/'dispatch.json').exists() or (jd/'studio-send-claimed.json').exists(): raise core.WorkflowError('Existing dispatch evidence must be reconciled; never retry automatically')
    with core.lock('studio-bridge'):
        if (jd/'dispatch.json').exists() or (jd/'studio-send-claimed.json').exists():
            raise core.WorkflowError('Existing dispatch evidence must be reconciled; never retry automatically')
        # Read-only preflight before changing application state.
        official.submit(pid,jid,execute=False)
        target,shot,proof=_open_prepared(pid,jid)
        client=bambuddy.Client()
        try:
            printer=client.get(f"printers/{job['printer_id']}")
            if not _studio_serial_matches(printer): raise core.WorkflowError('Studio selected serial does not match the approved printer')
        finally: client.close()
        core.write_json(jd/'studio-script-verification.json',{'at':core.now(), **proof, 'selected_serial_matches_printer':True,'serial_source':'Studio user_last_selected_machine plus exact dialog display identity','final_send_tested':False})
        # All lengthy GUI setup finishes before the 60-second reservation.
        phase['reservation_entered']=True
        reserved=official.submit(pid,jid,execute=True)
        if not reserved.get('reserved'): raise core.WorkflowError('Official reservation was not created')
        receipt=core.read_json(jd/'dispatch.json')
        request={'pid':target,'job_id':jid,'receipt_path':str(jd/'dispatch.json'),'artifact_path':str(jd/job['artifact']),
                 'artifact_sha256':job['artifact_sha256'],'fingerprint':receipt['fingerprint'],'snapshot_sha256':shot['sha256'],
                 'selected_serial_sha256':hashlib.sha256(printer['serial_number'].encode()).hexdigest()}
        core.write_json(jd/'studio-send-request.json',request)
        with core.lock('printer'):
            receipt=core.read_json(jd/'dispatch.json')
            try:
                phase['final_helper_invoked']=True
                result=_run('send-once',jd/'studio-send-request.json',timeout=20)
                if result.get('command_sent') is not True: raise core.WorkflowError('No verified single Send click')
                core.write_json(jd/'official-ui-send.json',{'at':core.now(),'clicked_send_once':True,'task_name':jid+'.gcode','executor':'local-studio-script','snapshot_sha256':shot['sha256']})
                receipt.update(command_sent=True,ui_send_at=core.now())
                core.write_json(jd/'dispatch.json',receipt)
                return {**result,'transport':'bambu_studio','printer_accepted':False,'next':'reconcile exact task; no automatic retry'}
            except Exception:
                # Reservation or claim may have reached the UI. Preserve uncertainty.
                # Keep existing positive observation if another reconciler completed
                # between reservation and acquiring this lock.
                if receipt.get('state') != 'observed':
                    receipt.update(state='dispatch_unknown',updated_at=core.now(),reconciliation_required=True)
                    core.write_json(jd/'dispatch.json',receipt)
                    job.update(state='dispatch_unknown',updated_at=core.now());core.write_json(jd/'job.json',job)
                raise



def dispatch(pid,jid):
    if sys.platform != 'darwin':
        raise BeforeSendError('请按 docs/WINDOWS.md 使用官方 Studio 交接流程')
    phase={'final_helper_invoked':False,'reservation_entered':False}
    try:
        return _dispatch_impl(pid,jid,phase)
    except Exception as exc:
        if not phase['final_helper_invoked'] and not phase['reservation_entered']:
            raise BeforeSendError(str(exc)) from exc
        raise
