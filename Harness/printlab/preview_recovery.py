"""Recover local preview images for existing archives without changing device state.

Studio caches identify a published profile/plate, not the bytes or colours printed.
URLs and raw cache records never enter the recovery index or report.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from urllib.parse import urlsplit
import zipfile

import httpx
from PIL import Image

from . import bambuddy, core, history

INDEX = 'Library/References/PrintHistory/recovered-previews.json'
IMAGES = 'Library/References/PrintHistory/CloudPreviews/'
MAX_IMAGE = 8 * 1024 * 1024
MAX_RECORD = 10 * 1024 * 1024
HOSTS = {'public-cdn.bblmw.cn', 'public-cdn.bblmw.com',
         'bbl-prod-model.oss-cn-shanghai.aliyuncs.com'}
PNG = b'\x89PNG\r\n\x1a\n'


def positive(value):
    text = str(value)
    return text if re.fullmatch(r'[1-9][0-9]*', text) else None


def identity(archive):
    raw = ((archive.get('extra_data') or {}).get('_print_data') or {}).get('raw_data') or {}
    profile = positive(raw.get('profile_id'))
    plates = {positive(raw[k]) for k in ('plate_idx', 'plate_id') if raw.get(k) is not None}
    if not profile or len(plates) != 1 or None in plates:
        return None
    return profile, plates.pop()


def url_identity(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.port not in (None, 443)
                or parsed.username or parsed.password):
            return None
        match = re.search(r'/([1-9][0-9]*)/3mf/(?:[^/]+/)*Metadata/plate_([1-9][0-9]*)\.png$', parsed.path)
        return match.groups() if match else None
    except ValueError:
        return None


def png_digest(data):
    if len(data) > MAX_IMAGE or not data.startswith(PNG):
        raise ValueError('Invalid PNG size or signature')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or image.width * image.height > 20_000_000:
            raise ValueError('Invalid PNG dimensions')
        image.verify()
    return hashlib.sha256(data).hexdigest()


def read_bounded(path, limit=MAX_IMAGE):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Source exceeds size limit')
    return data


def add_candidate(candidates, key, data, source, issues):
    try:
        digest = png_digest(data)
    except (OSError, ValueError, Image.DecompressionBombError):
        issues['invalid_images'] += 1
        return
    candidates.setdefault(key, {})[digest] = (data, source)


def fetch_image(url, issues):
    """Fetch only a known official cache URL, with bounded bytes and no redirects."""
    if url_identity(url) is None:
        return None
    try:
        with httpx.stream('GET', url, timeout=15, follow_redirects=False, trust_env=False) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes(chunk_size=65536):
                data.extend(chunk)
                if len(data) > MAX_IMAGE:
                    raise ValueError('Image exceeds size limit')
        png_digest(data)
        issues['downloaded_images'] += 1
        return bytes(data)
    except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError):
        issues['failed_downloads'] += 1
        return None


def studio_candidates(root, wanted, issues, fetch_missing=False):
    candidates = {}
    database = root / 'Cache.db'
    if database.is_file():
        try:
            # Close the handle explicitly, including on Windows cache-copy tests.
            with contextlib.closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
                rows = conn.execute('SELECT r.request_key, d.isDataOnFS, d.receiver_data '
                                    'FROM cfurl_cache_response r JOIN cfurl_cache_receiver_data d USING(entry_ID)')
                for url, on_disk, blob in rows:
                    key = url_identity(url) if isinstance(url, str) else None
                    if key not in wanted:
                        continue
                    try:
                        if on_disk:
                            filename = blob if isinstance(blob, str) else bytes(blob).decode('utf-8')
                            path = core.safe_path(root / 'fsCachedData', filename, require_file=False)
                            data = read_bounded(path) if path.is_file() else None
                        else:
                            data = bytes(blob)
                        source = 'official_studio_cfurl_cache'
                        if data is None and fetch_missing:
                            data = fetch_image(url, issues)
                            source = 'official_studio_cache_url'
                        if data is None:
                            issues['unreadable_sources'] += 1
                        else:
                            add_candidate(candidates, key, data, source, issues)
                    except (OSError, ValueError, TypeError, core.WorkflowError):
                        issues['unreadable_sources'] += 1
        except sqlite3.Error:
            issues['unreadable_sources'] += 1
    else:
        issues['missing_cache_db'] = 1
    records = sorted((root / 'WebKit/NetworkCache').glob('Version */Records'))
    if not records:
        issues['missing_webkit_records'] = 1
    for folder in records:
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.name.endswith('-blob'):
                continue
            try:
                path = core.safe_path(root, path.relative_to(root).as_posix())
                record = read_bounded(path, MAX_RECORD)
                urls = re.findall(rb'https://[^\x00-\x20\x7f-\xff]+', record)
                keys = {key for url in urls if (key := url_identity(url.decode('ascii')))}
                if len(keys) != 1:
                    if keys & wanted:
                        issues['ambiguous_records'] += 1
                    continue
                key = next(iter(keys))
                if key not in wanted:
                    continue
                start = record.find(PNG)
                end = record.find(b'IEND', start)
                source = 'official_studio_webkit_cache'
                if start >= 0 and end > start:
                    if record.find(PNG, start + len(PNG)) >= 0:
                        issues['ambiguous_records'] += 1
                        continue
                    data = record[start:end + 8]
                else:
                    blob = core.safe_path(root, path.relative_to(root).as_posix() + '-blob', require_file=False)
                    data = read_bounded(blob) if blob.is_file() else None
                if data is None and fetch_missing:
                    url = next(url.decode('ascii') for url in urls if url_identity(url.decode('ascii')) == key)
                    data = fetch_image(url, issues)
                    source = 'official_studio_cache_url'
                if data is None:
                    issues['unreadable_sources'] += 1
                else:
                    add_candidate(candidates, key, data, source, issues)
            except (OSError, ValueError, core.WorkflowError):
                issues['unreadable_sources'] += 1
    return candidates


def manifest_candidates(path, archives, issues):
    manifest = json.loads(read_bounded(path, MAX_RECORD).decode('utf-8-sig'))
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1 or not isinstance(manifest.get('previews'), list):
        raise core.WorkflowError('Expected schema_version 1 and previews list')
    by_key = {(a['printer_id'], a['id']): a for a in archives}
    candidates = {}
    for entry in manifest['previews']:
        if not isinstance(entry, dict):
            raise core.WorkflowError('Preview entries must be objects')
        pid, aid = entry.get('printer_id'), entry.get('archive_id')
        if type(pid) is not int or type(aid) is not int:
            raise core.WorkflowError('Manifest printer_id and archive_id must be integers')
        key = (pid, aid)
        archive = by_key.get(key)
        if not archive or identity(archive) != (positive(entry.get('profile_id')), positive(entry.get('plate'))):
            issues['unmatched_manifest_entries'] += 1
            continue
        filename = entry.get('file')
        if not isinstance(filename, str) or not filename:
            raise core.WorkflowError('Manifest entry needs a local PNG or 3MF file')
        source = Path(filename).expanduser()
        if not source.is_absolute():
            source = path.parent / source
        try:
            if source.suffix.lower() == '.3mf':
                with zipfile.ZipFile(source) as package:
                    member = f'Metadata/plate_{entry["plate"]}.png'
                    matches = [item for item in package.infolist() if item.filename == member]
                    if len(matches) != 1 or matches[0].file_size > MAX_IMAGE:
                        raise ValueError('Missing, duplicate or oversized plate PNG')
                    data = package.read(matches[0])
            elif source.suffix.lower() == '.png':
                data = read_bounded(source)
            else:
                raise ValueError('Expected PNG or 3MF')
            add_candidate(candidates, key, data, 'explicit_local_manifest', issues)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError):
            issues['unreadable_sources'] += 1
    return candidates


def saved_entry(index, archive):
    key = f'{archive["printer_id"]}:{archive["id"]}'
    if key in index:
        return index[key]
    legacy = index.get(str(archive['id']))
    return legacy if isinstance(legacy, dict) and legacy.get('printer_id') == archive['printer_id'] else None


def saved_preview(index, archive):
    """Read old archive-only keys and new device-qualified keys without migration."""
    saved = saved_entry(index, archive)
    if not isinstance(saved, dict) or saved.get('printer_id') != archive.get('printer_id'):
        return None
    if saved.get('archive_id', archive['id']) != archive['id']:
        return None
    if saved.get('kind') == 'reference_model':
        matches = saved.get('archive_name') == archive.get('print_name')
    else:
        matches = identity(archive) == (saved.get('profile_id'), saved.get('plate'))
    url = saved.get('url', '')
    if not matches or not isinstance(url, str) or not url.startswith('/api/documents/' + IMAGES):
        return None
    try:
        path = core.safe_path(core.ROOT, url.removeprefix('/api/documents/'))
        if saved.get('sha256') and png_digest(read_bounded(path)) != saved['sha256']:
            return None
    except (OSError, ValueError, core.WorkflowError, Image.DecompressionBombError):
        return None
    return {key: saved.get(key) for key in ('url', 'kind', 'profile_id', 'plate')}


def atomic_image(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.preview-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def recover(*, printer_id=None, cache_dir=None, manifest=None, apply=False, fetch_missing=False, client_factory=None):
    pid = printer_id if printer_id is not None else core.config().get('printer_id')
    if type(pid) is not int or pid <= 0:
        raise core.WorkflowError('Configure printer_id or pass --printer-id with a positive integer')
    if manifest and cache_dir:
        raise core.WorkflowError('Choose --manifest or --cache-dir')
    if manifest and fetch_missing:
        raise core.WorkflowError('--fetch-missing applies only to Studio cache URLs')
    if not manifest and cache_dir is None and sys.platform != 'darwin':
        raise core.WorkflowError('Use --manifest for local PNG/3MF on this platform; native Studio cache format is unsupported')
    client = (client_factory or bambuddy.Client)()
    try:
        archives = history.pages(client, 'archives', pid)
    finally:
        client.close()
    # Reject a service returning rows outside the requested device, rather than matching their images.
    if any(a.get('printer_id') != pid or type(a.get('id')) is not int for a in archives):
        raise core.WorkflowError('Archive response contains an invalid ID or a different device')
    issues = dict(invalid_images=0, unreadable_sources=0, ambiguous_records=0, unmatched_manifest_entries=0,
                  downloaded_images=0, failed_downloads=0)
    if manifest:
        candidates = manifest_candidates(Path(manifest).expanduser(), archives, issues)
    else:
        root = Path(cache_dir).expanduser() if cache_dir else Path.home() / 'Library/Caches/com.bambulab.bambu-studio'
        wanted = {key for archive in archives if (key := identity(archive))}
        candidates = studio_candidates(root, wanted, issues, fetch_missing)
    report = {'mode': 'apply' if apply else 'dry_run', 'printer_id': pid, 'source': 'manifest' if manifest else 'studio_cache',
              'issues': issues, 'items': [], 'written': 0, 'cloud_history_synced': False}
    # The index is read again under the inter-process lock, so concurrent invocations merge safely.
    with core.lock('preview-recovery'):
        index_path = core.safe_path(core.ROOT, INDEX, require_file=False)
        index = core.read_json(index_path, {})
        if not isinstance(index, dict):
            raise core.WorkflowError('Recovery index must be a JSON object; existing data preserved')
        for archive in archives:
            item = {'archive_id': archive['id'], 'printer_id': pid}
            report['items'].append(item)
            if f'{pid}:{archive["id"]}' in index or saved_entry(index, archive) is not None:
                item['status'] = 'existing' if saved_preview(index, archive) else 'existing_unavailable'
                continue
            profile_plate = identity(archive)
            if profile_plate is None:
                item['status'] = 'missing_identity'
                continue
            key = (pid, archive['id']) if manifest else profile_plate
            options = candidates.get(key, {})
            if len(options) != 1:
                item['status'] = 'conflict' if options else 'not_found'
                continue
            digest, (data, source) = next(iter(options.items()))
            profile, plate = profile_plate
            rel = f'{IMAGES}{profile}-{plate}-{digest}.png'
            item.update(status='ready', profile_id=profile, plate=plate, sha256=digest)
            if apply:
                image_path = core.safe_path(core.ROOT, rel, require_file=False)
                if image_path.exists() and read_bounded(image_path) != data:
                    item['status'] = 'conflict'
                    continue
                if not image_path.exists():
                    atomic_image(image_path, data)
                index[f'{pid}:{archive["id"]}'] = {
                    'url': '/api/documents/' + rel, 'kind': 'reference_plate' if manifest else 'cloud_plate',
                    'profile_id': profile, 'plate': plate, 'archive_id': archive['id'], 'printer_id': pid,
                    'sha256': digest, 'source': source, 'retrieved_at': core.now()}
                report['written'] += 1
                item['status'] = 'recovered'
        if report['written']:
            core.write_json(index_path, index)
    report['counts'] = {status: sum(item['status'] == status for item in report['items'])
                        for status in sorted({item['status'] for item in report['items']})}
    return report
