"""Link a real stop receipt to a verified old task. Never sends a command."""
import datetime as dt
import re
from pathlib import Path
from . import core


def _fresh(stamp):
    try:
        age = (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(stamp)).total_seconds()
        return 0 <= age <= 1800
    except (TypeError, ValueError):
        return False


def _past(stamp):
    try:
        return (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(stamp)).total_seconds() >= 0
    except (TypeError, ValueError):
        return False


def register(pid, jid, receipt_relative):
    """Record existing complete-MCP stop evidence and its matching terminal readback."""
    from . import native
    p, jd = core.project_path(pid), core.job_path(pid, jid)
    job = core.read_json(jd/'job.json')
    if not Path(receipt_relative).parts or Path(receipt_relative).parts[0] not in {'Evidence','Print'} or Path(receipt_relative).suffix != '.json':
        raise core.WorkflowError('Stop receipt must be a project Evidence/Print JSON file')
    receipt_path = core.safe_path(p, receipt_relative)
    receipt = core.read_json(receipt_path, {})
    payload = receipt.get('structuredContent', {})
    if receipt.get('isError') or payload.get('status') != 'success' or payload.get('command') != 'stop' or payload.get('route') != 'bambu:///local':
        raise core.WorkflowError('A successful complete-MCP native stop receipt is required')
    observation = core.read_json(jd/'native-observation.json', {})
    dispatch = core.read_json(jd/'dispatch.json', {})
    remote = dispatch.get('remote_task')
    device = observation.get('device', {})
    if (job.get('state') not in {'failed','cancelled'} or not remote or not re.fullmatch('checked-'+native.TASK_UUID+'-'+re.escape(jid),remote,re.I) or
            observation.get('matching_task') is not True or observation.get('fresh') is not True or
            observation.get('remote_task') != remote or device.get('current_print') != remote or
            device.get('id') != job.get('printer_id') or device.get('state') != 'FAILED' or
            device.get('hms_errors') != [] or not _past(observation.get('at'))):
        raise core.WorkflowError('Cancellation registration requires a fresh matching FAILED old task without HMS errors')
    record_path = jd/'cancel-confirmation.json'
    if record_path.exists():
        raise core.WorkflowError('Cancellation evidence already recorded; preserve the original')
    value = {'schema_version':1,'old_job_id':jid,'printer_id':job['printer_id'],'previous_task':remote,
             'receipt':receipt_relative,'receipt_sha256':core.digest(receipt_path),
             'cancelled_at':observation['at'],'recorded_at':core.now(),
             'terminal_observation':observation,'scope':'Existing stop and terminal evidence only; no physical command sent'}
    core.write_json(record_path,value)
    return value


def clearance(p, jd, job, approval):
    """An exact new artifact, original user times, and immutable old stop evidence."""
    lineage = core.read_json(jd/'repair-lineage.json', {})
    old_id = lineage.get('repair_for') or job.get('retry_of',{}).get('job_id')
    if not old_id or not approval:
        return None
    if (approval.get('revoked') or not approval.get('plate_clear') or approval.get('job_id') != job['id'] or
            approval.get('fingerprint') != core.job_fingerprint(p,jd,job)):
        return None
    authorized = approval.get('print_authorized_at',approval.get('approved_at'))
    cleared = approval.get('plate_clear_confirmed_at',approval.get('approved_at'))
    if not _fresh(authorized) or not _fresh(cleared):
        return None
    old_dir = core.job_path(job['project_id'],old_id)
    old = core.read_json(old_dir/'job.json', {})
    record = core.read_json(old_dir/'cancel-confirmation.json', {})
    if not record:
        return None
    receipt_path = core.safe_path(p,record['receipt'])
    receipt = core.read_json(receipt_path, {})
    payload = receipt.get('structuredContent', {})
    if (old_id == job['id'] or old.get('state') not in {'failed','cancelled'} or
            old.get('printer_id') != job.get('printer_id') or record.get('printer_id') != job.get('printer_id') or
            record.get('old_job_id') != old_id or record.get('receipt_sha256') != core.digest(receipt_path) or
            receipt.get('isError') or payload.get('status') != 'success' or payload.get('command') != 'stop' or
            payload.get('route') != 'bambu:///local' or
            record.get('previous_task') != core.read_json(old_dir/'dispatch.json',{}).get('remote_task')):
        raise core.WorkflowError('Recorded cancellation evidence changed or is not for this printer/task')
    return {'previousTask':record['previous_task'],'newJobId':job['id'],'fileSha256':job['artifact_sha256'],
            'receiptSha256':record['receipt_sha256'],'cancelledAt':record['cancelled_at'],
            'printAuthorizedAt':authorized,'plateClearedAt':cleared}


def matches_live(status, proof):
    if not proof or status.get('state') != 'FAILED' or status.get('current_print') != proof['previousTask']:
        return False
    if status.get('hms_errors') != [] or not _fresh(proof.get('printAuthorizedAt')) or not _fresh(proof.get('plateClearedAt')):
        return False
    # The native MCP independently requires raw print_error=0, empty HMS,
    # zero heater targets, fresh identity, nozzle/material/route and rechecks.
    for key in ('print_error','mc_print_error_code'):
        if key in status and status[key] not in (0,'0'):
            return False
    if 'fail_reason' in status and status['fail_reason'] not in (0,'0',50348044,'50348044'):
        return False
    return True
