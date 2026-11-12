"""Explicit shelf of prepared prints and GET-only readiness checks.

Registration is not print authorization. This module never approves, uploads,
reserves a queue slot, changes hardware, or starts a print. A caller must bind a
fresh user action and repeat readiness immediately before actual dispatch.
"""
from __future__ import annotations

import math
import re
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import quote

from . import core, bambuddy, design, native, slicer_guard, materials

REGISTRY = 'Library/Prepared/list.json'
PREPARED_STATES = {'awaiting_approval', 'approved'}


def _registry():
    value = core.read_json(core.ROOT / REGISTRY, {'schema_version': 1, 'items': []})
    if not isinstance(value, dict) or value.get('schema_version') != 1 or not isinstance(value.get('items'), list):
        raise core.WorkflowError('待打印清单格式损坏，请先修复清单')
    return value


def _number(value):
    try:
        if isinstance(value, bool):
            return None
        v = float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def slot_label(slot):
    if slot == 254:
        return '左主外挂'
    if slot == 255:
        return '右辅外挂'
    if type(slot) is int and 0 <= slot < 104:
        return f'{chr(65 + slot // 4)}{slot % 4 + 1}'
    return '槽位待核实'


def _url(pid, relative):
    return f'/api/files/{quote(pid, safe="")}/{quote(relative, safe="/")}'


def _slice_info(jd, job):
    """Use selected plate's used rows; global unused project IDs are not parts."""
    import json
    with zipfile.ZipFile(core.safe_path(jd, job['artifact'])) as z:
        root = ET.fromstring(z.read('Metadata/slice_info.config'))
        settings = json.loads(z.read('Metadata/project_settings.config'))
    plates = [p for p in root.findall('.//plate') if any(
        m.get('key') == 'index' and m.get('value') == str(job.get('plate', 1)) for m in p.findall('metadata'))]
    if len(plates) != 1:
        raise core.WorkflowError('切片缺少唯一板号')
    plate = plates[0]
    meta = {m.get('key'): m.get('value') for m in plate.findall('metadata')}
    rows = [dict(f.attrib) for f in plate.findall('.//filament')]
    ids = [int(row['id']) for row in rows]
    if not rows or len(set(ids)) != len(ids) or any(i < 1 for i in ids):
        raise core.WorkflowError('切片材料编号缺失或重复')
    for row in rows:
        row['id'] = int(row['id'])
        row['used_g'] = _number(row.get('used_g'))
        if row['used_g'] is None or row['used_g'] < 0:
            raise core.WorkflowError('切片缺少每种材料的用量，不能核验剩料')
    total = _number(meta.get('weight'))
    if total is None or total <= 0 or abs(sum(r['used_g'] for r in rows) - total) > max(.1, total * .001):
        raise core.WorkflowError('分材料用量与本盘总用量不一致，需重新检查切片')
    return settings, rows, meta


def _bindings(job, rows):
    mapping = job.get('mapping', {})
    slots = mapping.get('ams_mapping', [])
    extruders = mapping.get('extruder_mapping', [])
    ids = mapping.get('project_filament_ids', list(range(1, len(slots) + 1)))
    if (not slots or len(slots) != len(extruders) or len(ids) != len(slots)
            or any(type(i) is not int or i < 1 for i in ids) or len(set(ids)) != len(ids)
            or any(type(s) is not int or s < 0 for s in slots)):
        raise core.WorkflowError('材料和喷嘴映射不完整')
    if set(ids) != {r['id'] for r in rows}:
        raise core.WorkflowError('任务材料编号与本盘实际使用编号不一致')
    by_id = {r['id']: r for r in rows}
    result = []
    for index, fid in enumerate(ids):
        row = by_id[fid]
        def mapped(key, fallback=None):
            values = mapping.get(key, [])
            return values[index] if isinstance(values, list) and index < len(values) else fallback
        result.append({'filament_id': fid, 'slot': slots[index], 'slot_label': slot_label(slots[index]),
            'extruder': extruders[index], 'required_grams': row['used_g'],
            'material': mapped('filament_types', row.get('type')),
            'series': mapped('filament_series', mapping.get('material') or row.get('type')),
            'color': mapped('filament_colours', mapping.get('color') or row.get('color')),
            'name': mapped('material_display_names', mapped('filament_series', row.get('type'))),
            'profile_id': row.get('tray_info_idx'), 'inventory_id': mapped('inventory_ids'),
            'support_only': row.get('used_for_object') == 'false' and row.get('used_for_support') == 'true'})
    return result


def _entry(pid, jid):
    pid = core.read_json(core.project_path(pid) / 'project.json')['id']
    matches = [r for r in _registry()['items'] if r.get('project_id') == pid and r.get('job_id') == jid and r.get('active', True)]
    if len(matches) != 1:
        raise core.WorkflowError('此任务尚未加入待打印清单，或已移出')
    return matches[0]


def register(pid, jid, *, title=None, parts=None, note=None):
    """Explicitly publish one checked local job to the shelf, never authorize it."""
    p, jd = core.project_path(pid), core.job_path(pid, jid)
    job = core.read_json(jd / 'job.json')
    pid = core.read_json(p / 'project.json')['id']
    if job.get('project_id') != pid or job.get('id') != jid:
        raise core.WorkflowError('任务身份不匹配')
    if job.get('state') not in PREPARED_STATES or (jd / 'dispatch.json').exists():
        raise core.WorkflowError('只能加入尚未发送的已切片任务；不得重复打印旧回执')
    if job.get('trial_only') or core.print_configuration_issues(job):
        raise core.WorkflowError('试切片或配置不完整的任务不能加入待打印清单')
    registration_issue = None
    if core.read_json(p / 'project.json').get('current_revision') != job.get('revision'):
        # A shelf is an inventory of intended work, not a release gate. Preserve
        # a previous component's immutable package visibly, without changing the
        # project revision or inventing a valid current dispatch fingerprint.
        core.validate_3mf(jd / job['artifact'], job.get('plate', 1))
        if core.revision_files(p, job['revision']) != job['source_hashes']:
            raise core.WorkflowError('旧版本源文件已变化，不能登记原打印包')
        for group in ('profile_hashes', 'input_hashes'):
            for rel, expected in job.get(group, {}).items():
                if group == 'input_hashes' and not rel.startswith('Input/'):
                    raise core.WorkflowError('受控切片输入路径不正确')
                if core.digest(core.safe_path(jd, rel)) != expected:
                    raise core.WorkflowError('旧打印包的配置或输入已变化')
        if core.digest(core.safe_path(jd, job['artifact'])) != job.get('artifact_sha256'):
            raise core.WorkflowError('旧版本切片已变化，不能登记原打印包')
        fingerprint = None
        registration_issue = '项目已有新版本；已保留此配件的旧打印包，打印前须重新准备并核验'
    else:
        fingerprint = core.job_fingerprint(p, jd, job)
    _settings, rows, _meta = _slice_info(jd, job)
    _bindings(job, rows)
    if title is not None and (not isinstance(title, str) or not 1 <= len(title.strip()) <= 160):
        raise core.WorkflowError('请输入简短的配件名称')
    if parts is not None and (not isinstance(parts, list) or len(parts) > 50 or any(not isinstance(x, str) or not x.strip() or len(x) > 160 for x in parts)):
        raise core.WorkflowError('配件列表格式不正确')
    if note is not None and (not isinstance(note, str) or len(note) > 1000):
        raise core.WorkflowError('备注过长')
    with core.lock('prepared-catalogue'):
        data = _registry()
        prior = next((r for r in data['items'] if r.get('project_id') == pid and r.get('job_id') == jid), {})
        entry = {'project_id': pid, 'job_id': jid, 'revision': job['revision'],
                 'title': (title or prior.get('title') or core.read_json(p / 'project.json')['name']).strip(),
                 'parts': parts if parts is not None else prior.get('parts', []),
                 'note': note if note is not None else prior.get('note', ''),
                 'fingerprint': fingerprint, 'artifact_sha256': job['artifact_sha256'],
                 'registration_issue': registration_issue,
                 'created_at': prior.get('created_at') or core.now(), 'updated_at': core.now(),
                 'active': True, 'automatic_start': False, 'print_authorized': False}
        data['items'] = [r for r in data['items'] if (r.get('project_id'), r.get('job_id')) != (pid, jid)] + [entry]
        data['updated_at'] = core.now()
        core.write_json(core.ROOT / REGISTRY, data)
    return card(entry)


def card(entry):
    """Cheap shelf card. Does not claim that live conditions are ready."""
    pid, jid = entry['project_id'], entry['job_id']
    base = {k: entry.get(k) for k in ('project_id', 'job_id', 'revision', 'title', 'parts', 'note', 'created_at', 'updated_at', 'registration_issue')}
    base.update(automatic_start=False, live_checked=False, state='prepared', state_label='待核验', print_authorized=False)
    try:
        p, jd = core.project_path(pid), core.job_path(pid, jid)
        job = core.read_json(jd / 'job.json')
        if job.get('state') not in PREPARED_STATES or (jd / 'dispatch.json').exists():
            base.update(state=job.get('state', 'unavailable'), state_label='已发起或已归档')
        if core.read_json(p / 'project.json').get('current_revision') != job.get('revision'):
            base.update(state='stale', state_label='版本已更新，需重新核验')
        settings, rows, meta = _slice_info(jd, job)
        base['materials'] = _bindings(job, rows)
        base['estimates'] = {'prediction_seconds': _number(meta.get('prediction')), 'weight_grams': _number(meta.get('weight')), 'kind': 'slicer_estimate'}
        base['bed_type'] = job.get('requested_bed_type')
        base['printer_id'] = job.get('printer_id')
        base['transport'] = job.get('mapping', {}).get('transport')
        revision = job['revision']
        for key, rel in [('preview_url', f'Preview/{revision}/cover.png'), ('model_url', f'Exports/{revision}/model.glb'),
                         ('artifact_url', f'Print/{jid}/{job["artifact"]}')]:
            try:
                core.safe_path(p, rel)
                base[key] = _url(pid, rel)
            except core.WorkflowError:
                base[key] = None
    except (core.WorkflowError, ValueError, KeyError, TypeError, OSError, ET.ParseError, zipfile.BadZipFile):
        base.update(state='unavailable', state_label='文件或材料记录不可用', materials=[])
    return base


def catalogue():
    data = _registry()
    return {'items': [card(r) for r in data['items'] if r.get('active', True)],
            'updated_at': data.get('updated_at'), 'automatic_start': False}


def _spool_matches(spool, tray, bound):
    if not spool or spool.get('archived_at'):
        return False
    if (str(spool.get('rgba') or '').lstrip('#').upper() != str(tray.get('tray_color') or '').lstrip('#').upper()):
        return False
    family = str(spool.get('material') or '').upper()
    live = str(tray.get('tray_type') or '').upper()
    support = bound.get('profile_id') == 'GFS05' and tray.get('tray_info_idx') == 'GFS05'
    if family != live and not (support and family in {'SUPPORT FOR PLA', 'SUPPORT FOR PLA/PETG'} and live in {'PLA', 'PLA-S'}):
        return False
    subtype = str(spool.get('subtype') or '')
    if subtype and not support and subtype.lower() not in str(tray.get('tray_sub_brands') or '').lower():
        return False
    return True


def quantity_checks(bindings, status, assignments, spools):
    """Aggregate by physical slot, then use fresh RFID % × matched label weight.

    Historical/ledger remaining grams are deliberately never used. A matched
    assignment plus exact expected material/color is needed to lend label weight
    to the currently loaded spool. This is a conservative estimate, not a scale.
    """
    trays = bambuddy.reported_trays(status)
    assigned = {}
    for a in assignments:
        if a.get('printer_id') != status.get('id'):
            continue
        key = (a.get('ams_id'), a.get('tray_id'))
        if key in assigned:
            assigned[key] = None  # Ambiguous current assignment must fail closed.
        else:
            assigned[key] = a.get('spool_id')
    spool_rows = {}
    for spool in spools:
        sid = spool.get('id')
        spool_rows[sid] = None if sid in spool_rows else spool
    grouped = {}
    for bound in bindings:
        slot = bound['slot']
        item = grouped.setdefault(slot, {**bound, 'filament_ids': [], 'required_grams': 0.0})
        item['required_grams'] += bound['required_grams']
        item['filament_ids'].append(bound['filament_id'])
        if any(item.get(k) != bound.get(k) for k in ('extruder', 'material', 'series', 'color', 'inventory_id', 'profile_id')):
            item['binding_conflict'] = True
    seen_spools = {}
    result = []
    for slot, item in grouped.items():
        tray = trays.get(slot, {})
        percent = _number(tray.get('remain'))
        if percent is None or not 0 <= percent <= 100 or materials.slot_state(tray) != 'loaded':
            percent = None
        sid = assigned.get((slot // 4, slot % 4)) if slot < 254 else None
        spool = spool_rows.get(sid)
        match = (sid is not None and (item.get('inventory_id') is None or sid == item['inventory_id'])
                 and _spool_matches(spool, tray, item) and not item.get('binding_conflict'))
        label_weight = _number(spool.get('label_weight')) if spool and match else None
        if label_weight is None or label_weight <= 0:
            label_weight = None
        estimate = percent * label_weight / 100 if percent is not None and label_weight else None
        reserve = max(10.0, item['required_grams'] * .1)
        sufficient = estimate is not None and estimate >= item['required_grams'] + reserve
        row = {k: item.get(k) for k in ('slot', 'slot_label', 'filament_ids', 'material', 'series', 'color', 'name', 'extruder')}
        row.update(required_grams=round(item['required_grams'], 2), reserve_grams=round(reserve, 2),
                   reported_remaining_percent=percent, label_weight_grams=label_weight,
                   estimated_available_grams=round(estimate, 2) if estimate is not None else None,
                   sufficient=sufficient, quantity_basis='device_percent_times_matched_spool_label' if estimate is not None else 'unknown',
                   message='按设备余量估计足够，已留余量' if sufficient else '剩料不足' if estimate is not None else '余量或当前料卷身份未知，不能确认足够',
                   measured=False, inventory_id=sid if match else None)
        if sid is not None and match:
            if sid in seen_spools:
                row.update(sufficient=False, message='同一料卷被分配到多个物理槽位，需核对库存绑定')
                seen_spools[sid].update(sufficient=False, message=row['message'])
            seen_spools[sid] = row
        result.append(row)
    return result


def check(pid, jid, *, client=None, inspector=None):
    """Read-only, approval-free preflight; no optimistic or cached readiness."""
    entry = _entry(pid, jid)
    p, jd = core.project_path(pid), core.job_path(pid, jid)
    job = core.read_json(jd / 'job.json')
    checks, quantities = [], []
    fingerprint, status, inspection, bindings, settings = None, None, None, [], None
    def record(key, label, passed, good, bad):
        checks.append({'id': key, 'label': label, 'status': 'pass' if passed else 'blocked', 'message': good if passed else bad})
    def probe(key, label, fn, good, bad):
        try:
            value = fn()
            record(key, label, True, good, bad)
            return value
        except (Exception,):
            record(key, label, False, good, bad)
            return None
    def integrity():
        if job.get('project_id') != entry['project_id'] or job.get('id') != jid or job.get('state') not in PREPARED_STATES or (jd / 'dispatch.json').exists():
            raise core.WorkflowError('不可重复发送')
        if job.get('trial_only') or core.print_configuration_issues(job):
            raise core.WorkflowError('配置未完成')
        fp = core.job_fingerprint(p, jd, job)
        if fp != entry['fingerprint'] or job.get('artifact_sha256') != entry['artifact_sha256']:
            raise core.WorkflowError('已登记打印包发生变化')
        return fp
    fingerprint = probe('files', '版本与打印文件', integrity, '版本、切片、配置和登记指纹一致', '文件、版本、配置已变化或此任务已尝试发送，请重新准备')
    def design_check():
        result = design.check(entry['project_id'], 'release', job['revision'])
        if result.get('status') not in {'passed', 'not_configured'}:
            raise core.WorkflowError('设计放行未通过')
        return True
    probe('design', '设计与模型检查', design_check, '模型已通过项目的放行检查', '当前模型的放行记录缺失或不匹配')
    def file_checks():
        nonlocal settings, bindings
        # An outdated project revision still has useful immutable slice and
        # material facts. Inspect those independently of the release gate above;
        # never let that independence turn a failed fingerprint into readiness.
        artifact = core.safe_path(jd, job['artifact'])
        if core.digest(artifact) != job.get('artifact_sha256') or job.get('artifact_sha256') != entry.get('artifact_sha256'):
            raise core.WorkflowError('已登记切片发生变化')
        settings, rows, _meta = _slice_info(jd, job)
        bindings = _bindings(job, rows)
        slicer_guard.assert_safe_archive(artifact, job.get('plate', 1))
        value = (inspector or native.run_client)(jd, job, 'inspect')
        if not value or value.get('ok') is not True or value.get('executed') is not False:
            raise core.WorkflowError('独立刀路检查失败')
        return value
    inspection = probe('gcode', '刀路与启动指令', file_checks, '刀路、载料和温度指令检查通过', '刀路、启动指令或用料数据未通过检查')
    own_client = client is None
    try:
        client = client or bambuddy.Client()
        def read_status():
            value = client.get(f"printers/{job['printer_id']}/status")
            if not isinstance(value, dict):
                raise core.WorkflowError('设备返回格式不正确')
            return value
        status = probe('connection', '实时设备连接', read_status, '已读取设备实时状态', '无法读取打印机实时状态')
        if isinstance(status, dict):
            age = bambuddy.telemetry_age(status)
            fresh = status.get('connected') is True and age is not None and -5 <= age <= 30
            record('freshness', '状态新鲜度', fresh, '设备已连接，AMS报告在30秒内', '设备离线，或状态超过30秒/时间未知')
            record('identity', '目标设备', status.get('id') == job.get('printer_id'), '设备编号与打印包一致', '设备编号不匹配，不能打印')
            record('idle', '设备空闲', status.get('state') in {'IDLE', 'FINISH'}, '设备空闲或已结束上一盘', '设备正在工作、暂停或故障中，请等待或处理')
            record('diagnostics', '设备故障', not status.get('hms_errors'), '没有活动故障报告', '设备有活动故障，请先处理')
            temps = status.get('temperatures')
            quiet = (isinstance(temps, dict) and all(k in temps for k in ('bed_target', 'nozzle_target'))
                     and all(_number(v) == 0 for k, v in temps.items() if k.endswith('_target')))
            record('heaters', '加热与其他作业', quiet, '没有正在执行的加热目标', '设备正在加热，或加热状态未知')
            if bindings and fresh:
                def route():
                    # FINISH is conditionally usable only after later explicit plate confirmation.
                    bambuddy.verify_machine_identity(client, job)
                    bambuddy.validate_ready(status, job['mapping'], cleared_finished=True,
                                           printer_model=job.get('sliced_printer_model'))
                    bambuddy.validate_slice_route(jd, job, status)
                    bambuddy.validate_native_filaments(status, job['mapping'])
                    return True
                probe('route', '颜色、材料与供料路线', route, '实际材料、颜色、槽位和喷嘴与切片一致', '材料、颜色或供料路线不符；换槽后须重新核对映射')
                expected = (inspection or {}).get('inspection', {}).get('nozzleDiameters')
                actual = [_number(n.get('nozzle_diameter')) for n in status.get('nozzles', [])]
                nozzle_ok = (isinstance(expected, list) and len(expected) == len(actual) and bool(actual)
                             and all(_number(a) == _number(b) and _number(a) is not None for a, b in zip(expected, actual)))
                expected_types = (inspection or {}).get('inspection', {}).get('nozzleTypes')
                actual_types = [{'HS01': 'hardened_steel', 'SS01': 'stainless_steel'}.get(n.get('nozzle_type')) for n in status.get('nozzles', [])]
                nozzle_ok = nozzle_ok and expected_types == actual_types and all(actual_types)
                record('nozzles', '喷嘴规格', nozzle_ok, '实际喷嘴直径和类型与切片一致', '实际喷嘴规格未知或不符')
                def quantity():
                    assignments, spools = client.get('inventory/assignments'), client.get('inventory/spools')
                    if not isinstance(assignments, list) or not isinstance(spools, list):
                        raise core.WorkflowError('库存返回格式不正确')
                    return quantity_checks(bindings, status, assignments, spools)
                quantities = probe('inventory', '当前料卷身份', quantity, '已读取实际料卷绑定', '无法读取当前料卷绑定和卷重') or []
                record('quantity', '耗材余量', bool(quantities) and all(q['sufficient'] for q in quantities), '各料位预计余量足够，已留10%且至少10克余量', '部分耗材不足或余量未知，请查看材料明细')
            else:
                record('route', '颜色、材料与供料路线', False, '', '文件或实时数据未通过，无法核验供料')
                record('quantity', '耗材余量', False, '', '实时数据不足，无法核验余量')
            physical_plate = core.read_json(core.ROOT / 'Library/Devices/X2D/device.json', {}).get('user_confirmed', {}).get('build_plate_description')
            record('plate_type', '打印板类型', physical_plate == job.get('requested_bed_type') == job.get('curr_bed_type'), '切片与已确认的打印板类型一致，仍需确认板面干净', '切片板型与当前设备卡不一致或未确认')
        def queue_check():
            rows = client.get('queue/')
            if not isinstance(rows, list) or any(r.get('status') in {'pending', 'printing'} for r in rows):
                raise core.WorkflowError('队列占用或状态未知')
            return True
        probe('queue', '其他排队任务', queue_check, '没有其他待打或打印队列', '另有排队/打印任务，或队列状态读取失败')
    except Exception:
        record('device', '设备读取', False, '', '设备接口不可用，未发起任何打印')
    finally:
        if own_client and client:
            client.close()
    probe('active_receipts', '历史发送结果', lambda: (bambuddy.ensure_no_active_dispatches(jd), True)[1], '没有其他活动或结果不明的发送记录', '有其他正在执行或结果不明的记录，需先对账，不能重复发送')
    blockers = [c for c in checks if c['status'] == 'blocked']
    transport = job.get('mapping', {}).get('transport')
    return {'project_id': entry['project_id'], 'job_id': jid, 'fingerprint': fingerprint, 'checked_at': core.now(),
            'ready': not blockers, 'checks': checks, 'blockers': blockers, 'materials': quantities,
            'transport': {'kind': transport, 'developer_mode': (status or {}).get('developer_mode'),
                          'sdcard': (status or {}).get('sdcard'),
                          'independent_dispatch_verified': False,
                          'message': '需由发送适配器另行核验可用性；此结果不代表已能独立发送'},
            'device': {k: (status or {}).get(k) for k in ('id', 'name', 'state', 'current_print')},
            'plate_confirmation_required': True, 'executed': False, 'automatic_start': False,
            'quantity_note': '余量按设备百分比和当前绑定料卷的标称克重估计，可能滞后；不是实称值。'}
