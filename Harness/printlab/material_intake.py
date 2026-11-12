"""Register user-confirmed spools in Bambuddy with durable request reconciliation."""
from __future__ import annotations

import hashlib
import json
import re

from . import bambuddy, core, materials, workspace


JOURNAL = 'Library/Materials/intake.json'
FIELDS = {'material', 'brand', 'subtype', 'color_name', 'rgba', 'material_number',
          'storage_location', 'label_weight', 'core_weight'}


def _payload(spool, source):
    if not isinstance(spool, dict) or set(spool) - FIELDS:
        raise core.WorkflowError('Unsupported spool fields; use material, product, colour and storage facts')
    result = {'material': workspace.required_text(spool.get('material'), 'Material', 50)}
    for key, value in spool.items():
        if key in {'label_weight', 'core_weight'}:
            if type(value) is not int or value < 0:
                raise core.WorkflowError(f'{key} must be a nonnegative integer in grams')
            result[key] = value
        elif key == 'rgba':
            if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{8}', value):
                raise core.WorkflowError('rgba must contain eight hexadecimal digits')
            result[key] = value.upper()
        else:
            result[key] = workspace.required_text(value, key, 255)
    # Upstream defaults to a full 1000g spool. Explicit zero leaves unknown weight unknown.
    result.setdefault('label_weight', 0)
    result.setdefault('core_weight', 0)
    result.update(weight_used=0, data_origin='manual', note=f'用户确认的库存记录\n来源 {source}\n实际余量未知。')
    return result


def register(spool, source, request_id, client_factory=None):
    """One request describes one physical spool. Reuse it after interruption."""
    source = workspace.required_text(source, 'User confirmation source')
    request_id = workspace.required_text(request_id, 'Request ID', 100)
    payload = _payload(spool, source)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with core.lock('material-intake'):
        path = core.safe_path(core.ROOT, JOURNAL, require_file=False)
        journal = core.read_json(path, {'schema_version': 1, 'requests': {}})
        existing = journal['requests'].get(request_id)
        service = workspace.connection()['bambuddy_url']
        if existing and (existing['fingerprint'] != fingerprint or existing['service'] != service):
            raise core.WorkflowError('This intake request already describes another spool or service')
        marker = (existing or {}).get('marker') or '[PrintLab intake ' + hashlib.sha256(
            f'{core.ROOT}:{request_id}'.encode()).hexdigest() + ']'
        payload['note'] += '\n' + marker
        client = (client_factory or bambuddy.Client)(write=True)
        try:
            rows = client.get('inventory/spools')
            if not isinstance(rows, list):
                raise core.WorkflowError('Unexpected inventory response')
            matches = [row for row in rows if marker in str(row.get('note') or '')]
            if len(matches) > 1:
                raise core.WorkflowError('Multiple spools carry the intake marker; reconcile their identities')
            if matches:
                row = matches[0]
                if any(row.get(key) != value for key, value in spool.items() if key != 'rgba'):
                    raise core.WorkflowError('The registered spool was changed; inspect it before continuing')
                if 'rgba' in spool and str(row.get('rgba')).upper() != payload['rgba']:
                    raise core.WorkflowError('The registered spool colour changed; inspect it before continuing')
                journal['requests'][request_id] = {'status': 'registered', 'spool_id': row['id'],
                    'fingerprint': fingerprint, 'service': service, 'marker': marker, 'observed_at': core.now()}
                core.write_json(path, journal)
                return {'request_id': request_id, 'replayed': True, 'spool': materials.inventory_items([row])[0]}
            if existing:
                raise core.WorkflowError('Previous intake result is unresolved or the spool was removed. '
                                         'Inspect Bambuddy and the saved request before another write; no retry was sent')
            journal['requests'][request_id] = {'status': 'pending', 'fingerprint': fingerprint,
                'service': service, 'marker': marker, 'started_at': core.now()}
            core.write_json(path, journal)
            row = client.post('inventory/spools', json=payload)
            if type(row.get('id')) is not int:
                raise core.WorkflowError('Intake response has no spool ID; rerun this same request to reconcile')
            observed = client.get(f"inventory/spools/{row['id']}")
            if observed.get('id') != row['id'] or marker not in str(observed.get('note') or ''):
                raise core.WorkflowError('Spool readback did not match; keep the request for reconciliation')
            journal['requests'][request_id].update(status='registered', spool_id=row['id'], observed_at=core.now())
            core.write_json(path, journal)
            return {'request_id': request_id, 'replayed': False, 'spool': materials.inventory_items([observed])[0]}
        finally:
            client.close()
