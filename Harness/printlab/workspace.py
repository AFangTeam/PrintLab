"""Version-checked updates to existing shared documents and device facts."""
from __future__ import annotations

import os
import tempfile
import hashlib
import math
from urllib.parse import urlsplit

from . import core


DOCUMENTS = {
    'profile': 'Context/profile.md',
    'taste': 'Context/taste.md',
    'lessons': 'Context/lessons.md',
    'team': 'Context/team.md',
    'device': 'Library/Devices/X2D/device.json',
}


def document(name):
    if name not in DOCUMENTS:
        raise core.WorkflowError('Unknown shared document')
    path = core.safe_path(core.ROOT, DOCUMENTS[name], require_file=False)
    return {'name': name, 'path': DOCUMENTS[name],
            'sha256': core.digest(path) if path.is_file() else None,
            'text': path.read_text(encoding='utf-8') if path.is_file() else ''}


def check_version(path, expected):
    actual = core.digest(path) if path.is_file() else None
    if expected != actual:
        raise core.WorkflowError('Shared document changed; reread it before applying this update')


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.tmp-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def required_text(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise core.WorkflowError(f'{label} must be nonempty text of at most {maximum} characters')
    return value.strip()


def append_note(name, text, source, request_id, expected_sha256):
    """Keep existing prose; a stable request ID makes a repeated append a no-op."""
    if name not in {'profile', 'taste', 'lessons', 'team'}:
        raise core.WorkflowError('Use the device update command for device facts')
    text = required_text(text, 'Note', 16000)
    source = required_text(source, 'Source')
    request_id = required_text(request_id, 'Request ID', 100)
    if any(c in request_id for c in '<>\r\n'):
        raise core.WorkflowError('Invalid request ID')
    marker = f'<!-- printlab-update:{request_id} -->'
    fingerprint = hashlib.sha256(f'{text}\n{source}'.encode()).hexdigest()
    receipt = f'<!-- content-sha256:{fingerprint} -->'
    with core.lock('shared-context'):
        current = document(name)
        if marker in current['text']:
            if marker + '\n' + receipt not in current['text']:
                raise core.WorkflowError('Request ID was already used for a different shared update')
            return {**current, 'replayed': True}
        path = core.safe_path(core.ROOT, current['path'], require_file=False)
        check_version(path, expected_sha256)
        body = f"{current['text'].rstrip()}\n\n{marker}\n{receipt}\n## {core.now()}\n\n{text}\n\n来源记录\n\n{source}\n"
        write_text(path, body)
        return {**document(name), 'replayed': False}


def update_device(changes, source, expected_sha256):
    if not isinstance(changes, dict) or not changes or set(changes) - {'model', 'name', 'user_confirmed'}:
        raise core.WorkflowError('Device changes must contain model, name or user_confirmed')
    for key in ('model', 'name'):
        if key in changes:
            required_text(changes[key], key, 200)
    confirmed = changes.get('user_confirmed', {})
    allowed = {'model', 'nozzle_diameter_mm', 'nozzle_type', 'build_plate_description',
               'owned_build_plates', 'feeding_description', 'ams_count', 'fts_installed',
               'fts_confirmation_quote', 'fts_confirmation_date', 'preferred_network_mode',
               'printable_area', 'printable_height', 'firmware', 'external_spool_description'}
    if not isinstance(confirmed, dict) or set(confirmed) - allowed:
        raise core.WorkflowError('Unsupported device fact; credentials belong in Runtime/private')
    for key, value in confirmed.items():
        if value is None:
            continue
        if key in {'nozzle_diameter_mm', 'printable_height'}:
            numbers = value if isinstance(value, list) and key == 'nozzle_diameter_mm' else [value]
            if not numbers or any(type(n) not in {int, float} or not math.isfinite(n) or n <= 0 for n in numbers):
                raise core.WorkflowError(f'{key} requires positive finite millimetres')
        elif key == 'ams_count':
            if type(value) is not int or value < 0:
                raise core.WorkflowError('ams_count requires a nonnegative integer')
        elif key == 'fts_installed':
            if type(value) is not bool:
                raise core.WorkflowError('fts_installed requires true or false')
        elif key in {'owned_build_plates', 'nozzle_type', 'printable_area'} and isinstance(value, list):
            if not value or any(not isinstance(item, str) or not item.strip() for item in value):
                raise core.WorkflowError(f'{key} requires nonempty text entries')
        else:
            required_text(value, key)
    source = required_text(source, 'Source')
    with core.lock('shared-context'):
        path = core.safe_path(core.ROOT, DOCUMENTS['device'], require_file=False)
        check_version(path, expected_sha256)
        card = core.read_json(path, {'schema_version': 1, 'verification_status': 'unconfigured'})
        for key in ('model', 'name'):
            if key in changes:
                card[key] = changes[key]
        card['user_confirmed'] = {**card.get('user_confirmed', {}), **confirmed}
        card.setdefault('fact_updates', []).append({'at': core.now(), 'source': source, 'changes': changes})
        core.write_json(path, card)
        return document('device')


def connection():
    path = core.safe_path(core.ROOT, 'Runtime/config.json', require_file=False)
    cfg = core.config()
    return {'sha256': core.digest(path) if path.is_file() else None,
            'bambuddy_url': cfg.get('bambuddy_url'), 'printer_id': cfg.get('printer_id')}


def configure_connection(url, printer_id, expected_sha256):
    """Select a service/device without changing credentials or printer settings."""
    parsed = urlsplit(url)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise core.WorkflowError('Use the Bambuddy service URL without credentials, query or fragment')
    if type(printer_id) is not int or printer_id < 1:
        raise core.WorkflowError('Select a positive Bambuddy printer ID from discovery')
    with core.lock('shared-context'):
        path = core.safe_path(core.ROOT, 'Runtime/config.json', require_file=False)
        check_version(path, expected_sha256)
        cfg = core.config()
        cfg.update(bambuddy_url=url.rstrip('/'), printer_id=printer_id)
        core.write_json(path, cfg)
        return connection()
