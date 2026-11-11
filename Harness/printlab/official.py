"""Audited official Studio handoff through the same single-dispatch ledger.

No GUI automation lives here. After submit --execute, the operator/agent uses
the official UI once; reconciliation never sends or repeats that UI action.
"""
import copy
import datetime as dt
import shutil
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from . import core, bambuddy, native, recovery


def sliced_only(source, target):
    """Remove editable mesh data, retaining every executable/settings byte."""
    changed = {'3D/3dmodel.model', 'Metadata/model_settings.config'}
    with zipfile.ZipFile(source) as src:
        if len([n for n in src.namelist() if n.endswith('.gcode')]) != 1:
            raise core.WorkflowError('Official handoff currently supports one sliced plate only')
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as out:
            for info in src.infolist():
                name, data = info.filename, src.read(info.filename)
                if name.startswith('3D/') and name != '3D/3dmodel.model':
                    changed.add(name)
                    continue
                if name == '3D/3dmodel.model':
                    root = ET.fromstring(data)
                    ET.register_namespace('', 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02')
                    root.attrib.pop('requiredextensions', None)  # Empty model has no production objects.
                    for child in root:
                        if child.tag.rsplit('}',1)[-1] in {'resources','build'}:
                            child.clear()
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                elif name == 'Metadata/model_settings.config':
                    root = ET.fromstring(data)
                    for parent in root.iter():
                        for child in list(parent):
                            if child.tag in {'object','model_instance','assemble','assemble_item'}:
                                parent.remove(child)
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                out.writestr(info, data)
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(target) as b:
        preserved = [n for n in a.namelist() if n not in changed]
        if any(a.read(n) != b.read(n) for n in preserved):
            raise core.WorkflowError('Official handoff altered a preserved entry')
    return {'changed_entries':sorted(changed), 'byte_identical_entries':preserved,
            'gcode_and_settings_identical':True, 'resliced':False}


def prepare(pid, jid):
    """Create an unapproved, uniquely named copy; preserve original approval."""
    with core.lock('printer'):
        p, old_dir = core.project_path(pid), core.job_path(pid,jid)
        old = core.read_json(old_dir/'job.json')
        if (old_dir/'dispatch.json').exists() or old.get('state') not in {'approved','awaiting_approval'}:
            raise core.WorkflowError('Only an undispatched prepared task can be copied for Studio')
        core.job_fingerprint(p, old_dir, old)
        if old.get('mapping',{}).get('transport') not in {'bambu_native','bambu_studio'}:
            raise core.WorkflowError('Unsupported source route')
        new_id = 'J'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        jd = p/'Print'/new_id
        jd.mkdir()
        for field in ('profile_hashes','input_hashes'):
            for rel in old.get(field,{}):
                dest = core.safe_path(jd,rel,require_file=False)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(core.safe_path(old_dir,rel),dest)
        artifact = new_id+'.gcode.3mf'
        proof = sliced_only(old_dir/old['artifact'], jd/artifact)
        job = copy.deepcopy(old)
        for key in ('reconciliation','execution_evidence','last_reconciled_at','execution_phase','printer_progress'):
            job.pop(key,None)
        job.update(id=new_id, state='awaiting_approval', created_at=core.now(), updated_at=core.now(),
                   artifact=artifact, artifact_sha256=core.digest(jd/artifact))
        job['mapping']['transport']='bambu_studio'
        job['official_copy_of']={'job_id':jid,'artifact_sha256':old['artifact_sha256']}
        core.write_json(jd/'job.json',job)
        core.job_fingerprint(p,jd,job)
        core.write_json(jd/'same-toolpath-proof.json', {**proof,'source_job_id':jid,
            'source_sha256':old['artifact_sha256'],'output_sha256':job['artifact_sha256']})
        # A second approved source must not later dispatch the same physical part.
        old.update(state='superseded',superseded_by=new_id,updated_at=core.now())
        core.write_json(old_dir/'job.json',old)
        project=core.read_json(p/'project.json')
        project.update(current_job_id=new_id,status='awaiting_approval',updated_at=core.now())
        core.write_json(p/'project.json',project)
        return job


def submit(pid,jid,execute=False,client_factory=None,inspector=None):
    with core.lock('printer'):
        p,jd=core.project_path(pid),core.job_path(pid,jid)
        job,approval=core.read_json(jd/'job.json'),core.read_json(jd/'approval.json')
        client=(client_factory or bambuddy.Client)()
        try:
            bambuddy.preflight(p,jd,job,approval,client,official=True)
            recovery.before_submit(jd,job,approval,client)
            inspected=(inspector or native.run_client)(jd,job,'inspect')
            if not inspected or not inspected.get('ok'):
                raise core.WorkflowError('Official package failed the independent G-code audit')
            core.write_json(jd/'official-inspection.json', {'at':core.now(),**inspected})
            if execute:
                bambuddy.preflight(p,jd,job,approval,client,official=True)
                receipt={'job_id':jid,'transport':'bambu_studio','state':'awaiting_ui_send',
                         'created_at':core.now(),'fingerprint':approval['fingerprint'],
                         'artifact_sha256':job['artifact_sha256'],'expected_task_name':jid+'.gcode',
                         'send_deadline':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=60)).isoformat(),
                         'command_sent':False}
                core.write_json(jd/'dispatch.json',receipt)
                job.update(state='dispatching',updated_at=core.now())
                core.write_json(jd/'job.json',job)
                project=core.read_json(p/'project.json')
                project.update(current_job_id=jid,status='dispatching',updated_at=core.now())
                core.write_json(p/'project.json',project)
            return {'ready':True,'executed':False,'reserved':execute,'transport':'bambu_studio',
                    'file':str(jd/job['artifact']),'job_id':jid,
                    'next':'Verify the exact filename, target printer, materials and options in official UI; click Send once within 60 seconds, then reconcile. No reslicing or repeat send.'}
        finally:client.close()


def profile_title_archive_match(jd, job, receipt, live, client):
    """Studio may report embedded ProfileTitle instead of the edited send name.

    A title alone never identifies a run: require the exact approved artifact,
    a recorded one-time UI send, and a new archive on this device in its window.
    This is observation only and cannot authorize or trigger another send.
    """
    try:
        aid = live.get('current_archive_id')
        previous = receipt.get('execution_binding') or {}
        terminal = (aid is None and receipt.get('state') == 'observed'
                    and previous.get('method') == 'embedded_profile_title_and_new_archive'
                    and live.get('state') in {'FINISH', 'FAILED'})
        if terminal:
            aid = previous.get('archive_id')
        ui = core.read_json(jd/'official-ui-send.json', {})
        if (type(aid) is not int or aid < 1 or ui.get('clicked_send_once') is not True
                or ui.get('task_name') != job['id'] + '.gcode'
                or (not terminal and live.get('current_plate_id') != job['plate'])):
            return None
        artifact = core.safe_path(jd, job['artifact'])
        if core.digest(artifact) != job['artifact_sha256'] or receipt.get('artifact_sha256') != job['artifact_sha256']:
            return None
        with zipfile.ZipFile(artifact) as archive:
            root = ET.fromstring(archive.read('3D/3dmodel.model'))
        titles = [m.text for m in root if m.tag.rsplit('}',1)[-1] == 'metadata' and m.get('name') == 'ProfileTitle']
        if len(titles) != 1 or not titles[0] or live.get('current_print') != titles[0]:
            return None
        archive = client.get(f'archives/{aid}')
        if terminal and archive.get('status') != {'FINISH':'completed', 'FAILED':'failed'}[live['state']]:
            return None
        def stamp(value):
            parsed = dt.datetime.fromisoformat(value)
            # Bambuddy serializes database UTC timestamps without an offset.
            return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed
        start, deadline = stamp(receipt['created_at']), stamp(receipt['send_deadline'])
        if (archive.get('id') != aid or archive.get('printer_id') != job['printer_id']
                or archive.get('print_name') != titles[0]
                or not start <= stamp(ui['at']) <= deadline
                or not start <= stamp(archive['started_at']) <= deadline):
            return None
        return {'method':'embedded_profile_title_and_new_archive', 'archive_id':aid,
                'print_name':titles[0], 'archive_started_at':archive['started_at'],
                'artifact_sha256':job['artifact_sha256'], 'gcode_download_verified':False}
    except (KeyError, TypeError, ValueError, OSError, ET.ParseError, zipfile.BadZipFile):
        return None


def reconcile(pid,jid,client=None):
    p,jd=core.project_path(pid),core.job_path(pid,jid)
    job,receipt=core.read_json(jd/'job.json'),core.read_json(jd/'dispatch.json')
    if (receipt.get('job_id')!=jid or receipt.get('transport')!='bambu_studio'
            or job.get('printer_id')!=core.config().get('printer_id')
            or job.get('bambuddy_url')!=core.config().get('bambuddy_url')):
        raise core.WorkflowError('Official receipt or device identity mismatch')
    own=client is None
    client=client or bambuddy.Client()
    try:
        live=client.get(f"printers/{job['printer_id']}/status")
        age=bambuddy.telemetry_age(live)
        fresh=live.get('connected') is True and age is not None and age<=30
        matching=Path(str(live.get('current_print') or '')).name in {jid,jid+'.gcode',jid+'.gcode.3mf'}
        binding = None
        if fresh and not matching:
            binding = profile_title_archive_match(jd, job, receipt, live, client)
            matching = binding is not None
        if fresh and matching:
            job['state'],job['execution_phase']=native.observed_state(live)
            receipt.update(state='observed',command_sent=True,observed_at=core.now())
            if binding:
                receipt['execution_binding'] = binding
            core.write_json(jd/'dispatch.json',receipt)
            if core.is_current_attempt(p,job):
                row=core.read_json(p/'project.json');row.update(status=job['state'],updated_at=core.now())
                core.write_json(p/'project.json',row)
        observation={'at':core.now(),'matching_task':matching,'fresh':fresh,'device':bambuddy.sanitize_device(live)}
        core.write_json(jd/'official-observation.json',observation)
        job.update(updated_at=core.now(),reconciliation={'state':'current' if fresh and matching else 'unmatched',
                    'message':'官方任务已读回；实物质量待检查。' if fresh and matching else '官方任务尚未匹配；不重复发送。'})
        core.write_json(jd/'job.json',job)
        return {'job':job,'matching_task':matching,'fresh':fresh,'device_state':live.get('state')}
    finally:
        if own:client.close()
