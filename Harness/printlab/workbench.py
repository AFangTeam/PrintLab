"""Session-independent prepared-print control. No scheduling or automatic retries."""
from __future__ import annotations
import datetime as dt
import hashlib
import re
import secrets
import threading
from . import core, prepared, confirmation, bambuddy

TTL = 120
TERMINAL = {'blocked', 'observed', 'submitted', 'unknown'}

def _base():
    return core.ROOT / 'Runtime/workbench'

def _stamp_age(stamp):
    try:
        return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return float('inf')

def recover_operations():
    """On service boot, never resume a worker or replay an external action."""
    with core.lock('workbench-start'):
        for path in (_base() / 'operations').glob('*.json'):
            op = core.read_json(path)
            if op.get('state') in {'checking', 'dispatching'}:
                op.update(state='unknown' if op['state'] == 'dispatching' else 'blocked',
                    message='服务曾重启；发送结果需核对，不会重发' if op['state'] == 'dispatching' else '核验被服务重启中断，未发送；可重新核验',
                    updated_at=core.now())
                core.write_json(path, op)

def latest_operation(pid, jid):
    rows = [core.read_json(f) for f in (_base() / 'operations').glob('*.json')]
    rows = [x for x in rows if (x.get('project_id'), x.get('job_id')) == (pid, jid)]
    return _public(max(rows, key=lambda x: x['created_at'])) if rows else None

def capability(report):
    kind = report.get('transport', {}).get('kind')
    if kind == 'bambu_studio':
        try:
            from . import studio_bridge
            result = studio_bridge.capability(report.get('project_id'), report.get('job_id'))
            result.pop('observation', None)
            return result
        except (ImportError, AttributeError):
            return {'available': False, 'kind': kind, 'message': '官方 Studio 独立发送脚本尚未验证，当前只能保存和核验待打印件'}
    # Keep native mode changes out of this feature; a new transport needs its own review.
    return {'available': False, 'kind': kind, 'message': '这个打印包尚未准备独立发送通道'}

def check(pid, jid, *, owner=None):
    result = prepared.check(pid, jid)
    transport = capability(result)
    result['transport'].update(transport)
    result['checks'].append({'id': 'sender', 'label': '独立发送通道',
        'status': 'pass' if transport.get('available') is True else 'blocked', 'message': transport['message']})
    result['blockers'] = [x for x in result['checks'] if x['status'] == 'blocked']
    result['ready'] = not result['blockers']
    if result['ready'] and owner:
        token = secrets.token_urlsafe(32)
        expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=TTL)
        ticket = {'project_id': result['project_id'], 'job_id': jid, 'fingerprint': result['fingerprint'],
                  'created_at': core.now(), 'owner': owner, 'consumed': False}
        core.write_json(_base() / 'checks' / (hashlib.sha256(token.encode()).hexdigest() + '.json'), ticket)
        result.update(check_token=token, expires_at=expires.isoformat())
    return result

def _operation_path(opid):
    if not re.fullmatch(r'[a-f0-9]{32}', opid):
        raise core.WorkflowError('操作编号无效')
    return _base() / 'operations' / (opid + '.json')

def _public(value):
    return {k: v for k, v in value.items() if k not in {'owner', 'request_id'}}

def operation(opid, owner):
    value = core.read_json(_operation_path(opid))
    if not value:
        raise core.WorkflowError('没有找到工作台打印操作')
    return _public(value)

def reconcile_operation(opid, owner):
    """Read device evidence only; never retry a send or clear an unknown by guess."""
    path = _operation_path(opid)
    with core.lock('workbench-start'):
        op = core.read_json(path)
        if not op:
            raise core.WorkflowError('没有找到工作台打印操作')
        if op.get('state') not in {'unknown', 'submitted', 'observed'}:
            return _public(op)
        jd = core.job_path(op['project_id'], op['job_id'])
        if (jd / 'dispatch.json').exists():
            try:
                observed = bambuddy.reconcile(op['project_id'], op['job_id'])
                op['observation'] = {k: observed.get(k) for k in ('matching_task', 'fresh', 'device_state')}
                if observed.get('matching_task') and observed.get('fresh'):
                    op.update(state='observed', message='设备已读回匹配任务；首层与实物仍需检查')
                else:
                    op['message'] = '尚未匹配到这次任务，保留原记录；不会重复发送'
            except Exception:
                op['message'] = '暂时无法核对设备，保留原记录；不会重复发送'
        op['updated_at'] = core.now()
        core.write_json(path, op)
        return _public(op)

def start(pid, jid, *, owner, check_token, plate_clear, request_id, launch=None):
    if plate_clear is not True:
        raise core.WorkflowError('请先确认本次打印板已清洁并空置')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{20,100}', check_token or '') or not re.fullmatch(r'[a-fA-F0-9-]{32,36}', request_id or ''):
        raise core.WorkflowError('确认信息无效，请重新核验')
    token_path = _base() / 'checks' / (hashlib.sha256(check_token.encode()).hexdigest() + '.json')
    with core.lock('workbench-start'):
        for file in (_base() / 'operations').glob('*.json'):
            op = core.read_json(file)
            if op.get('owner') == owner and op.get('request_id') == request_id:
                if (op['project_id'], op['job_id']) != (pid, jid):
                    raise core.WorkflowError('此确认已绑定另一任务')
                return _public(op)
            if op.get('state') not in TERMINAL or op.get('state') == 'unknown':
                raise core.WorkflowError('已有发送正在处理或结果不明，请先核对结果，不能重复发送')
        ticket = core.read_json(token_path)
        if (not ticket or ticket.get('owner') != owner or ticket.get('consumed')
                or (ticket.get('project_id'), ticket.get('job_id')) != (pid, jid)
                or not 0 <= _stamp_age(ticket.get('created_at')) <= TTL):
            raise core.WorkflowError('核验已过期或已使用，请重新核验')
        ticket['consumed'] = True
        core.write_json(token_path, ticket)
        op = {'id': secrets.token_hex(16), 'project_id': pid, 'job_id': jid, 'owner': owner,
              'request_id': request_id, 'created_at': core.now(), 'confirmed_at': core.now(),
              'fingerprint': ticket['fingerprint'], 'state': 'checking', 'executed': False,
              'message': '正在再次核验设备与耗材，尚未发送'}
        core.write_json(_operation_path(op['id']), op)
    try:
        (launch or _launch)(op)
    except Exception:
        op.update(state='blocked', message='后台执行器未启动，未发送；请重新核验', updated_at=core.now())
        core.write_json(_operation_path(op['id']), op)
    return _public(op)

def _launch(op):
    threading.Thread(target=_run, args=(op,), daemon=True, name='printlab-workbench-send').start()

def _run(op):
    path = _operation_path(op['id'])
    pid, jid = op['project_id'], op['job_id']
    try:
        result = check(pid, jid)
        if not result['ready'] or result['fingerprint'] != op['fingerprint']:
            op.update(state='blocked', message='设备、材料、文件或发送能力已变化，请重新核验；未发送', checks=result['checks'])
            return
        if not 0 <= _stamp_age(op['confirmed_at']) <= TTL:
            op.update(state='blocked', message='清板确认已过期，请重新核验；未发送')
            return
        event = confirmation.record(pid, jid, {'print_authorized': True, 'plate_clear': True},
            '打印板已清洁并空置，确认打印此配件', 'PrintLab 工作台 / 操作 ' + op['id'], confirmed_at=op['confirmed_at'])
        core.approve(pid, jid, confirmation_event_id=event['id'])
        op.update(state='dispatching', message='正在通过官方应用发送；尚未确认设备已开始')
        core.write_json(path, op)
        from . import studio_bridge
        try:
            result = studio_bridge.dispatch(pid, jid)
        except studio_bridge.BeforeSendError:
            op.update(state='blocked', executed=False, message='官方发送窗口准备未通过，已确认未发起发送；可重新核验')
            return
        if result.get('command_sent') is not True:
            raise core.WorkflowError('发送执行器未证实已发起发送')
        op.update(state='submitted', executed=result.get('executed', False), message='发送操作已结束，等待设备读回', result=result)
        observed = bambuddy.reconcile(pid, jid)
        op['observation'] = {k: observed.get(k) for k in ('matching_task', 'fresh', 'device_state')}
        if observed.get('matching_task') and observed.get('fresh'):
            op.update(state='observed', message='设备已读回匹配任务；首层与实物仍需检查')
        # Dispatch receipts alone never prove physical extrusion.
        if op['state'] != 'observed':
            op['message'] = '已发起发送，尚未匹配到设备任务；不会重复发送'
    except Exception:
        dispatched = op.get('state') in {'dispatching', 'submitted', 'observed'} or (core.job_path(pid, jid) / 'dispatch.json').exists()
        op.update(state='unknown' if dispatched else 'blocked', executed=False,
            message='发送结果需要核对，不会自动重发' if dispatched else '核验或准备未通过，未发送；请查看任务记录')
    finally:
        op['updated_at'] = core.now()
        core.write_json(path, op)
