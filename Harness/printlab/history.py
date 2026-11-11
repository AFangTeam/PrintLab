"""Read-only union of device archives and individual print runs.

No project creation, device commands, inventory deduction or inferred acceptance.
Only an allowlist of fields survives into the local cache and browser.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import os
import tempfile
import re
import threading
import zipfile

import httpx

from . import bambuddy, core

_lock = threading.Lock()
PAGE_SIZE = 100
MAX_PAGES = 100


def timestamp(value):
    if not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.replace(tzinfo=stamp.tzinfo or dt.timezone.utc).isoformat()
    except ValueError:
        return None


def pages(client, route, printer_id):
    rows, seen = [], set()
    for page in range(MAX_PAGES):
        data = client.get(f'{route}/?printer_id={printer_id}&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}')
        batch = data if isinstance(data, list) else data['items']
        fresh = [r for r in batch if r['id'] not in seen]
        rows.extend(fresh)
        seen.update(r['id'] for r in fresh)
        if len(batch) < PAGE_SIZE:
            return rows
        if not fresh:
            raise ValueError('Pagination did not advance')
    raise ValueError('History exceeds pagination bound')


def archive_photo(client, archive):
    """Copy an existing archive photo; never create or infer a model file."""
    from PIL import Image, UnidentifiedImageError
    aid, photos = archive.get('id'), archive.get('photos') or []
    if type(aid) is not int or aid <= 0 or not isinstance(photos, list) or not photos:
        return None
    name = photos[0]
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+[.](?:jpg|jpeg|png|webp)', name, re.I):
        return None
    ext = name.rsplit('.', 1)[-1].lower()
    tag = hashlib.sha256(name.encode()).hexdigest()[:12]
    rel = f'Library/References/PrintHistory/ArchivePhotos/{aid}-{tag}.{ext}'
    try:
        path = core.safe_path(core.ROOT, rel, require_file=False)
        if not path.is_file():
            response = client.http.get(f'archives/{aid}/photos/{name}')
            response.raise_for_status()
            data = response.content
            if len(data) > 8 * 1024 * 1024:
                return None
            with Image.open(io.BytesIO(data)) as im:
                if im.format not in {'JPEG','PNG','WEBP'}:
                    return None
                im.verify()
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
                temp = tmp.name
                tmp.write(data)
            try:
                os.replace(temp, path)
            finally:
                if os.path.exists(temp): os.unlink(temp)
        return '/api/documents/' + rel
    except (httpx.HTTPError, OSError, ValueError, AttributeError, UnidentifiedImageError, core.WorkflowError):
        return None


def local_jobs():
    rows = []
    for path in sorted((core.ROOT / 'Project').glob('*/Print/*/job.json')):
        job = core.read_json(path, {})
        project = core.read_json(path.parents[2] / 'project.json', {})
        if not job.get('id') or not project.get('id'):
            continue
        aids = {job['archive_id']} if job.get('archive_id') else set()
        for filename in ('official-observation.json', 'observation.json'):
            observation = core.read_json(path.parent / filename, {})
            if observation.get('archive_id'):
                aids.add(observation['archive_id'])
            match = observation.get('match') or {}
            if isinstance(match, dict) and match.get('archive_id'):
                aids.add(match['archive_id'])
        rows.append({'id': job['id'], 'printer_id': job.get('printer_id'), 'archive_ids': aids,
                     'project_id': project['id'], 'project_name': project.get('name'),
                     'revision': job.get('revision'), 'artifact': job.get('artifact'), 'plate': job.get('plate', 1)})
    return rows


def model_preview(archive, jobs):
    """Only an exact task/archive association may use its sliced plate preview."""
    name = archive.get('print_name') or ''
    ids = set(re.findall(r'J\d{8}-\d{6}-[a-zA-Z0-9]+', name))
    matches = [j for j in jobs if j['printer_id'] == archive.get('printer_id') and
               (archive.get('id') in j['archive_ids'] or j['id'] in ids)]
    if len(matches) != 1:
        return None
    job = matches[0]
    try:
        from PIL import Image
        jd = core.job_path(job['project_id'], job['id'])
        source = core.safe_path(jd, job['artifact'])
        plate = int(job.get('plate') or 1)
        if plate < 1 or plate > 100:
            return None
        with zipfile.ZipFile(source) as z:
            info = z.getinfo(f'Metadata/plate_{plate}.png')
            if info.file_size > 8 * 1024 * 1024:
                return None
            data = z.read(info)
        with Image.open(io.BytesIO(data)) as img:
            if img.format != 'PNG' or img.width * img.height > 20_000_000:
                return None
            img.verify()
        digest = hashlib.sha256(data).hexdigest()[:20]
        rel = f'Library/References/PrintHistory/ModelPreviews/{job["id"]}-{plate}-{digest}.png'
        path = core.safe_path(core.ROOT, rel, require_file=False)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
                temp = tmp.name
                tmp.write(data)
            try: os.replace(temp, path)
            finally:
                if os.path.exists(temp): os.unlink(temp)
        return {'url': '/api/documents/' + rel, 'job_id': job['id'], 'revision': job['revision'], 'kind': 'sliced_plate'}
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, core.WorkflowError):
        return None


def association(archive, jobs):
    name = archive.get('print_name') or ''
    # Task IDs are unique. Similar titles, filenames and MakerWorld designs are not.
    ids = set(re.findall(r'J\d{8}-\d{6}-[a-zA-Z0-9]+', name))
    matches = [j for j in jobs if j['printer_id'] == archive.get('printer_id') and
               (archive.get('id') in j['archive_ids'] or j['id'] in ids)]
    projects = {j['project_id'] for j in matches}
    if len(projects) == 1:
        return {k: matches[0][k] for k in ('project_id', 'project_name')}
    return {'project_id': None, 'project_name': None}


def normalize(archive, run, jobs):
    source = run or archive
    raw = ((archive.get('extra_data') or {}).get('_print_data') or {}).get('raw_data') or {}
    design_id = str(raw.get('design_id') or '')
    started = timestamp(source.get('started_at'))
    ended = timestamp(source.get('completed_at'))
    duration = source.get('duration_seconds') if run else archive.get('actual_time_seconds')
    if duration is None and started and ended:
        duration = max(0, int((dt.datetime.fromisoformat(ended) - dt.datetime.fromisoformat(started)).total_seconds()))
    linked = association(archive, jobs) if archive else {'project_id': None, 'project_name': None}
    return {
        'id': f"run-{run['id']}" if run else f"archive-{archive['id']}",
        'archive_id': archive.get('id') or source.get('archive_id'),
        'printer_id': source.get('printer_id'),
        'name': source.get('print_name') or archive.get('print_name') or '未命名打印',
        **linked,
        'origin': 'linked_project' if linked['project_id'] else 'external',
        'launch_app': None,  # Cloud task/design IDs do not prove Handy versus Studio.
        'status': source.get('status', 'unknown'),
        'started_at': started, 'completed_at': ended,
        'created_at': timestamp(source.get('created_at')),
        'duration_seconds': duration,
        'estimated_seconds': archive.get('print_time_seconds'),
        'reported_weight_grams': source.get('filament_used_grams'),
        'weight_basis': 'bambuddy_record_not_weighed',
        'archive_photo_url': archive.get('_printlab_photo_url'),
        'model_preview': archive.get('_printlab_model_preview'),
        'has_3mf': bool(archive.get('file_path')),
        'has_source_3mf': bool(archive.get('source_3mf_path')),
        'file_missing_reason': (archive.get('extra_data') or {}).get('no_3mf_reason'),
        'makerworld_url': f'https://makerworld.com.cn/zh/models/{design_id}' if design_id.isdigit() and int(design_id) > 0 else None,
        'is_print_event': bool(run or started),
        'physical_review': 'not_verified',
        'status_source': 'bambuddy_print_log' if run else 'bambuddy_archive',
    }


def combine(archives, runs, jobs):
    by_id = {a['id']: a for a in archives}
    items = [normalize(by_id.get(r.get('archive_id'), {}), r, jobs) for r in runs]
    represented = {(r.get('archive_id'), timestamp(r.get('started_at'))) for r in runs}
    for archive in archives:
        if (archive['id'], timestamp(archive.get('started_at'))) not in represented:
            items.append(normalize(archive, None, jobs))
    return sorted(items, key=lambda r: r['started_at'] or r['created_at'] or '', reverse=True)


def view(force=False, client_factory=None):
    cache_path = core.ROOT / 'Runtime/history/latest.json'
    with _lock:
        cached = core.read_json(cache_path, {})
        pid = core.config().get('printer_id')
        if type(pid) is not int:
            return {'state': 'unconfigured', 'stale': False, 'items': [],
                    'message': '连接 Bambuddy 并配置打印机后，这里会显示已捕获的打印历史。'}
        if cached.get('printer_id') != pid:
            cached = {}
        stamp = timestamp(cached.get('updated_at'))
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(stamp)).total_seconds() if stamp else None
        if not force and age is not None and 0 <= age < 30:
            return cached
        client = None
        try:
            if not isinstance(pid, int):
                raise ValueError('Printer is not configured')
            client = (client_factory or bambuddy.Client)()
            archives = pages(client, 'archives', pid)
            runs = pages(client, 'print-log', pid)
            jobs = local_jobs()
            recovered = core.read_json(core.ROOT / 'Library/References/PrintHistory/recovered-previews.json', {})
            for archive in archives:
                archive['_printlab_photo_url'] = archive_photo(client, archive)
                archive['_printlab_model_preview'] = model_preview(archive, jobs)
                saved = recovered.get(str(archive['id']), {})
                raw = (archive.get('extra_data') or {}).get('_print_data', {}).get('raw_data', {})
                if (not archive['_printlab_model_preview'] and saved.get('printer_id') == archive.get('printer_id')
                    and ((saved.get('kind') == 'reference_model' and saved.get('archive_name') == archive.get('print_name'))
                         or (str(raw.get('profile_id')) == saved.get('profile_id')
                             and str(raw.get('plate_idx') or raw.get('plate_id') or 1) == saved.get('plate')))):
                    url = saved.get('url', '')
                    if url.startswith('/api/documents/Library/References/PrintHistory/CloudPreviews/'):
                        try:
                            core.safe_path(core.ROOT, url.removeprefix('/api/documents/'))
                            archive['_printlab_model_preview'] = {k: saved.get(k) for k in ('url', 'kind', 'profile_id', 'plate')}
                        except core.WorkflowError:
                            pass
            items = combine(archives, runs, jobs)
            # A stale unfinished archive must not look like a live running print.
            active = [r for r in items if r['status'] in {'printing', 'running', 'paused'}]
            if active:
                try:
                    live = client.get(f'printers/{pid}/status')
                    telemetry_age = bambuddy.telemetry_age(live)
                    fresh = live.get('connected') is True and telemetry_age is not None and telemetry_age <= 60
                except (httpx.HTTPError, ValueError):
                    live, fresh = {}, False
                for row in active:
                    if fresh and live.get('current_archive_id') == row['archive_id'] and live.get('state') in {'RUNNING', 'PAUSE'}:
                        row.update(status='paused' if live['state'] == 'PAUSE' else 'printing',
                                   progress=live.get('progress'), status_source='fresh_device_archive_id')
                    else:
                        row.update(reported_status=row['status'], status='unresolved')
            events = [r for r in items if r['is_print_event']]
            recovery = {'policy': 'exact_plate_or_explicit_reference',
                        'records': len(events),
                        'preview_available': sum(bool(r.get('model_preview')) for r in events),
                        'missing_preview': sum(not r.get('model_preview') for r in events),
                        'missing_with_source_link': sum(not r.get('model_preview') and bool(r.get('makerworld_url')) for r in events),
                        'cloud_history': 'not_connected'}
            result = {'state': 'current', 'stale': False, 'updated_at': core.now(), 'printer_id': pid,
                      'items': items, 'archive_count': len(archives), 'run_count': len(runs),
                      'counts': {'records': len(items), 'prints': len(events),
                                 'external': sum(r['origin'] == 'external' for r in events),
                                 'linked': sum(r['origin'] == 'linked_project' for r in events),
                                 'completed': sum(r['status'] == 'completed' for r in events)},
                      'coverage': {'from': min((r['started_at'] for r in events if r['started_at']), default=None),
                                   'all_recorded_pages_loaded': True, 'all_lifetime_prints_verified': False,
                                   'cloud_history_synced': False},
                      'recovery': recovery,
                      'message': '已读取本机保存的全部分页记录；未捕获的旧任务及云端完整历史尚未核实。'}
            core.write_json(cache_path, result)
            return result
        except (httpx.HTTPError, core.WorkflowError, OSError, ValueError, KeyError, TypeError):
            return {**cached, 'state': 'unavailable', 'stale': True, 'items': cached.get('items', []),
                    'message': '历史同步失败，保留上次成功记录；本次没有确认完整覆盖。'}
        finally:
            if client:
                client.close()
