"""Read-only device reconciliation before a new dispatch. Never retries a job."""
import datetime as dt
import json
import re
from . import core, bambuddy


def signed_rejection(receipt):
    # Legacy adapter preserved the upstream structured error as JSON text.
    # Do not interpret a timeout, a free-form mention of -26, or result=0 as rejection.
    try:
        error = json.loads(receipt.get('error', ''))
    except (ValueError, TypeError):
        return False
    return (isinstance(error, dict) and error.get('status') == 'error'
            and error.get('retryable') is False and error.get('tool') == 'print_3mf'
            and isinstance(error.get('message'), str)
            and re.fullmatch(r'Bambu native local print failed \(20\): native_print result=-26',
                             error['message']) is not None)


def settled_rejection(old, receipt, new, approval, live, queue):
    """Close occupancy only after a subsequent operator clear and a quiet printer.

    This deliberately does NOT establish whether the old geometry ever printed
    through another channel, and does not authorize a retry of that geometry.
    """
    if (old.get('state') != 'dispatch_unknown' or receipt.get('transport') != 'bambu_native'
            or receipt.get('job_id') != old.get('id') or not signed_rejection(receipt)
            or old.get('printer_id') != new.get('printer_id')
            or old.get('bambuddy_url') != new.get('bambuddy_url')
            or approval.get('plate_clear') is not True or approval.get('revoked')):
        return False
    try:
        cleared = dt.datetime.fromisoformat(approval.get('plate_clear_confirmed_at') or approval['approved_at'])
        ended = dt.datetime.fromisoformat(receipt['updated_at'])
        age = (dt.datetime.now(dt.timezone.utc) - cleared).total_seconds()
        if not (ended < cleared and 0 <= age <= 1800):
            return False
    except (ValueError, KeyError, TypeError):
        return False
    age = bambuddy.telemetry_age(live)
    if (live.get('connected') is not True or age is None or age > 30
            or live.get('state') not in {'IDLE', 'FINISH'} or live.get('hms_errors')
            or any(row.get('status') in {'pending', 'printing'} for row in queue)):
        return False
    temps = live.get('temperatures')
    if not isinstance(temps, dict) or 'bed_target' not in temps or 'nozzle_target' not in temps or any(
            value != 0 for key, value in temps.items() if key.endswith('_target')):
        return False
    if old['id'] in str(live.get('current_print') or ''):
        return False  # Let the exact-task observer handle this instead.
    return True


def before_submit(jd, job, approval, client):
    """Caller holds the printer lock and has validated the new exact approval."""
    outcomes = []
    for project in core.list_projects():
        for path in (core.project_path(project['id']) / 'Print').glob('*/job.json'):
            old = core.read_json(path, {})
            if path.parent == jd or old.get('state') not in bambuddy.ACTIVE_JOB_STATES:
                continue
            receipt = core.read_json(path.parent / 'dispatch.json', {})
            try:
                bambuddy.reconcile(project['id'], old['id'], client=client)
            except (core.WorkflowError, KeyError):
                pass  # Missing identity remains blocking, never guessed.
            old = core.read_json(path)
            if old.get('state') not in bambuddy.ACTIVE_JOB_STATES:
                outcomes.append({'job_id': old['id'], 'state': old['state']})
                continue
            live = client.get(f"printers/{job['printer_id']}/status")
            queue = client.get('queue/')
            if settled_rejection(old, receipt, job, approval, live, queue):
                evidence = {'at': core.now(), 'kind': 'signature_failure_settled_after_plate_clear',
                            'original_dispatch': receipt, 'next_job_id': job['id'],
                            'next_approval': approval, 'device': bambuddy.sanitize_device(live),
                            'queue': queue, 'execution_outcome': 'not_attributed',
                            'retry_authorized': False}
                core.write_json(path.parent / 'dispatch-resolution.json', evidence)
                # Preserve the original dispatch error, including unknown attribution.
                old.update(state='dispatch_rejected', updated_at=core.now(),
                           reconciliation={'state':'settled', 'message':'签名失败已结案；旧任务不重发，保留原始报错和未归属的实体结果。'})
                core.write_json(path, old)
                p = core.project_path(project['id'])
                if core.is_current_attempt(p, old):
                    row = core.read_json(p/'project.json')
                    row.update(status='awaiting_approval', updated_at=core.now())
                    core.write_json(p/'project.json', row)
                outcomes.append({'job_id': old['id'], 'state': old['state']})
    core.write_json(jd/'history-recovery.json', {'at':core.now(), 'outcomes':outcomes, 'device_writes':False})
    bambuddy.ensure_no_active_dispatches(jd)
    return outcomes
