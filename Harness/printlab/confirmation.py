"""Exact-task confirmation facts and a read-only card; no device writes."""
from __future__ import annotations

import datetime as dt
import re
import uuid
from . import core

FACTS = {'print_authorized', 'plate_clear', 'material_loaded', 'design_selected', 'colors_selected'}


def _age(stamp):
    try:
        parsed = dt.datetime.fromisoformat(stamp)
        if parsed.tzinfo is None:
            return None
        return (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds()
    except (TypeError, ValueError):
        return None


def record(pid, jid, facts, quote, source, confirmed_at=None):
    if not isinstance(facts, dict) or not facts or set(facts) - FACTS or any(type(v) is not bool for v in facts.values()):
        raise core.WorkflowError('Confirmation facts must be explicit supported boolean fields')
    if not isinstance(quote, str) or not quote.strip() or not isinstance(source, str) or not source.strip():
        raise core.WorkflowError('Record the actual user quote and conversation source')
    if confirmed_at is not None:
        age=_age(confirmed_at)
        if age is None or age < 0:
            raise core.WorkflowError('Confirmation time must be a timezone-aware past user-message timestamp')
    with core.lock('printer'):
        p, jd = core.project_path(pid), core.job_path(pid, jid)
        job = core.read_json(jd / 'job.json')
        if (jd / 'dispatch.json').exists() or job.get('state') not in {'awaiting_approval', 'awaiting_configuration', 'approved'}:
            raise core.WorkflowError('Only a prepared, undispatched task can receive new confirmation facts')
        fingerprint = core.job_fingerprint(p, jd, job)
        event = {'id':'C'+uuid.uuid4().hex, 'job_id':jid, 'project_id':job['project_id'],
                 'recorded_at':core.now(), 'facts':facts, 'quote':quote.strip(), 'source':source.strip(),
                 'fingerprint':fingerprint, 'printer_id':job['printer_id']}
        if confirmed_at is not None:
            event['confirmed_at']=confirmed_at
        core.write_json(jd / 'Confirmations' / (event['id']+'.json'), event)
        if any(facts.get(k) is False for k in ('print_authorized','plate_clear')):
            previous=core.read_json(jd/'approval.json')
            if previous:
                core.write_json(jd/'ApprovalHistory'/(uuid.uuid4().hex+'.json'), previous)
                core.write_json(jd/'approval.json', {**previous,'revoked':True,'revoked_at':core.now(),'revocation_event_id':event['id']})
            job.update(state='awaiting_approval',updated_at=core.now())
            core.write_json(jd/'job.json',job)
        return event


def events(jd, job, fingerprint):
    rows = []
    for path in (jd / 'Confirmations').glob('C*.json'):
        if path.is_symlink():
            continue
        row = core.read_json(path, {})
        if row.get('job_id') == job['id'] and row.get('fingerprint') == fingerprint and row.get('printer_id') == job.get('printer_id'):
            rows.append(row)
    return sorted(rows, key=lambda r:r.get('recorded_at', ''))


def resolve(jd, job, fingerprint, event_id=None):
    if event_id is not None and not re.fullmatch(r'C[0-9a-f]{32}', event_id):
        raise core.WorkflowError('Invalid confirmation event ID')
    rows = events(jd, job, fingerprint)
    if event_id is not None:
        if not any(row.get('id') == event_id for row in rows):
            raise core.WorkflowError('Confirmation does not match this exact task')
        # Later corrections or withdrawals override an older selected event.
    facts = {}
    for row in rows:
        for name,value in row.get('facts', {}).items():
            if name in FACTS:
                facts[name] = {'value':value,'quote':row.get('quote'),'source':row.get('source'),
                               'recorded_at':row.get('confirmed_at') or row.get('recorded_at'),'event_id':row.get('id')}
    for name in ('plate_clear','print_authorized'):
        fact = facts.get(name)
        if fact:
            age = _age(fact['recorded_at'])
            fact['fresh'] = age is not None and 0 <= age <= 1800
    return facts


def approval_facts(pid, jid, event_id):
    p, jd = core.project_path(pid), core.job_path(pid, jid)
    job = core.read_json(jd/'job.json')
    fingerprint = core.job_fingerprint(p,jd,job)
    facts = resolve(jd,job,fingerprint,event_id)
    if any(not facts.get(k,{}).get('value') or not facts.get(k,{}).get('fresh') for k in ('print_authorized','plate_clear')):
        raise core.WorkflowError('Current exact-task print authorization and cleared-plate facts are required')
    return facts


def card(pid, jid=None, device=None):
    p = core.project_path(pid)
    project = core.read_json(p/'project.json')
    if not jid:
        jid = (core.current_attempt(p, project) or {}).get('id')
    plate = core.read_json(core.ROOT/'Library/Devices/X2D/device.json',{}).get('user_confirmed',{}).get('build_plate_description')
    if not jid:
        return {'project_id':project['id'],'project_name':project['name'],'revision':project.get('current_revision'),
                'job_id':None,'plate_type':plate,'missing':[{'key':'slice','label':'尚未准备具体切片任务','needs_user':False}],
                'can_approve':False,'already_dispatched':False,'facts':{}}
    jd = core.job_path(pid,jid)
    job = core.read_json(jd/'job.json')
    dispatched = (jd/'dispatch.json').exists()
    issues = core.print_configuration_issues(job)
    fingerprint = None
    try:
        fingerprint = core.job_fingerprint(p,jd,job)
    except (core.WorkflowError,OSError) as exc:
        issues.append(str(exc))
    facts = resolve(jd,job,fingerprint) if fingerprint else {}
    approval = core.read_json(jd/'approval.json',{})
    if fingerprint and approval.get('fingerprint') == fingerprint and not approval.get('revoked'):
        age = _age(approval.get('approved_at'))
        fresh = age is not None and 0 <= age <= 1800
        for key,value in [('print_authorized',bool(approval.get('confirmation'))),('plate_clear',approval.get('plate_clear') is True)]:
            if key not in facts or facts[key].get('recorded_at','') < approval.get('approved_at',''):
                facts[key]={'value':value,'fresh':fresh,'source':'approval.json','quote':approval.get('confirmation'),
                            'recorded_at':approval.get('approved_at')}
    missing=[{'key':'configuration','label':issue,'needs_user':False} for issue in issues]
    if not dispatched:
        if not facts.get('plate_clear',{}).get('value') or not facts.get('plate_clear',{}).get('fresh'):
            missing.append({'key':'plate_clear','label':'本次打印板已清空','needs_user':True})
        if not facts.get('print_authorized',{}).get('value') or not facts.get('print_authorized',{}).get('fresh'):
            missing.append({'key':'print_authorized','label':'允许这一个具体任务开始打印','needs_user':True})
    if device is None:
        from . import bambuddy
        device=bambuddy.device()
    routes=[]
    mapping=job.get('mapping',{})
    raw=(device or {}).get('printer') or {}
    trays={u.get('id',0)*4+t.get('id',0):t for u in raw.get('ams',[]) for t in u.get('tray',[])}
    normalized_slots={s.get('diagnostics',{}).get('ams_id',0)*4+s.get('diagnostics',{}).get('tray_id',s.get('slot_number',1)-1):s
                      for module in (device or {}).get('material_slots',{}).get('modules',[]) for s in module.get('slots',[])}
    for i,slot in enumerate(mapping.get('ams_mapping',[])):
        t=trays.get(slot,{})
        normalized=normalized_slots.get(slot,{})
        routes.append({'filament_index':i+1,'slot_number':slot%4+1,'ams_id':slot//4,
                       'physical_extruder':mapping.get('extruder_mapping',[])[i] if i<len(mapping.get('extruder_mapping',[])) else None,
                       'material':t.get('tray_sub_brands') or mapping.get('material'),'material_type':t.get('tray_type'),
                       'color':t.get('tray_color') or mapping.get('color'),
                       'english_label':normalized.get('english_label'), 'material_number':normalized.get('material_number'),
                       'route_text':normalized.get('route',{}).get('text'), 'slot_state':normalized.get('state'),
                       'route_matches':normalized.get('diagnostics',{}).get('physical_extruder_id') == (mapping.get('extruder_mapping',[])[i] if i<len(mapping.get('extruder_mapping',[])) else None) if normalized else None})
    fresh_device=(device or {}).get('state')=='online' and (device or {}).get('stale') is False
    return {'project_id':project['id'],'project_name':project['name'],'revision':job['revision'],'job_id':jid,
            'state':job['state'],'plate_type':job.get('curr_bed_type') or plate,'known_plate_type':plate,
            'artifact_sha256':job.get('artifact_sha256'),'estimates':job.get('estimates'),
            'routes':routes,'facts':facts,'missing':missing,'already_dispatched':dispatched,
            'can_approve':not missing and not dispatched and job.get('state') in {'awaiting_approval','approved'},
            'device_fresh':fresh_device,'observed_at':(device or {}).get('updated_at'),
            'device_note':'设备状态只用于核对；软件与下发安全门仍需实时检查。'}
