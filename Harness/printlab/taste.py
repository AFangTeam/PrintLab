"""Append-only image-choice evidence. It does not infer or confirm preferences."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from . import core


def archive_root():
    return core.safe_path(core.ROOT, 'Library/Taste/Selections', require_file=False)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def record(project, manifest):
    if not isinstance(manifest, dict):
        raise core.WorkflowError('Choice manifest must be an object')
    p = core.ROOT if project == 'library' else core.project_path(project)
    pid = 'Library' if project == 'library' else core.read_json(p / 'project.json')['id']
    event_id = manifest.get('id', '')
    if not isinstance(event_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', event_id):
        raise core.WorkflowError('Choice id must be a stable filename-safe round identifier')
    if manifest.get('stage') not in {'shape', 'view_set', 'color', 'style', 'review', 'other'}:
        raise core.WorkflowError('Unknown choice stage')
    feedback = manifest.get('user_feedback')
    if not isinstance(feedback, dict) or any(not isinstance(feedback.get(k), str) or not feedback[k].strip() for k in ('quote', 'source')):
        raise core.WorkflowError('A real user quote and source are required; recommendations are not user choices')
    options = manifest.get('options')
    if not isinstance(options, list) or len(options) < 2:
        raise core.WorkflowError('Preserve the full comparison round with at least two options')
    ids, inputs = set(), []
    for option in options:
        if not isinstance(option, dict):
            raise core.WorkflowError('Each option must be an object')
        oid = option.get('id')
        if not isinstance(oid, str) or not oid.strip() or oid in ids:
            raise core.WorkflowError('Option identifiers must be unique nonempty strings')
        ids.add(oid)
        images = option.get('images')
        if not isinstance(images, list) or not images:
            raise core.WorkflowError('Each option needs its presented image(s)')
        sources = []
        for rel in images:
            if not isinstance(rel, str):
                raise core.WorkflowError('Images must be project-relative paths')
            source = core.safe_path(p, rel)
            if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                raise core.WorkflowError('Choice evidence must be an image')
            sources.append((rel, source, core.digest(source)))
        inputs.append((option, sources))
    selected = manifest.get('selected_option_ids')
    if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected) or len(set(selected)) != len(selected) or not set(selected) <= ids:
        raise core.WorkflowError('Selected ids must identify options in this round')
    outcome = manifest.get('outcome', 'selected')
    if outcome not in {'selected', 'none', 'deferred'} or (outcome == 'selected') != bool(selected):
        raise core.WorkflowError('Selected/none/deferred outcome must match the user selection')
    # Image hashes bind idempotency to bytes, not merely a mutable source path.
    fingerprint = hashlib.sha256(_canonical({'manifest': manifest, 'images': [[(r, h) for r, _, h in sources] for _, sources in inputs]})).hexdigest()
    key = f'{pid}-{event_id}'
    with core.lock('taste'):
        root = archive_root()
        root.mkdir(parents=True, exist_ok=True)
        dest = core.safe_path(root, key, require_file=False)
        if dest.exists():
            prior = core.read_json(core.safe_path(dest, 'record.json'))
            if prior['input_sha256'] != fingerprint:
                raise core.WorkflowError('Choice round already exists; append a new correction round instead of overwriting it')
            _verify(dest, prior)
            return {'id': key, 'path': dest.relative_to(core.ROOT).as_posix(), 'reused': True}
        supersedes = manifest.get('supersedes')
        if supersedes is not None:
            if not isinstance(supersedes, str) or '/' in supersedes or not (root / supersedes / 'record.json').is_file():
                raise core.WorkflowError('Correction must reference an existing archived round')
        temp = Path(tempfile.mkdtemp(prefix='.pending-', dir=root))
        try:
            archived_options = []
            for index, (option, sources) in enumerate(inputs):
                assets = []
                for image_index, (rel, source, sha) in enumerate(sources):
                    target = temp / f'option-{index + 1}-{image_index + 1}{source.suffix.lower()}'
                    shutil.copyfile(source, target)
                    if core.digest(target) != sha:
                        raise core.WorkflowError('Image changed during archiving; retry with stable source files')
                    assets.append({'source_path': rel, 'snapshot': target.name, 'sha256': sha})
                archived_options.append({'id': option['id'], 'label': option.get('label', option['id']), 'assets': assets})
            data = {'schema_version': 1, 'id': key, 'project_id': pid,
                    'recorded_at': core.now(), 'input_sha256': fingerprint,
                    'manifest': manifest, 'options': archived_options,
                    'unselected_meaning': 'not chosen in this round; not evidence of dislike',
                    'print_authorized': False}
            core.write_json(temp / 'record.json', data)
            os.replace(temp, dest)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
    return {'id': key, 'path': dest.relative_to(core.ROOT).as_posix(), 'reused': False}


def _verify(folder, data):
    for option in data['options']:
        for asset in option['assets']:
            if core.digest(core.safe_path(folder, asset['snapshot'])) != asset['sha256']:
                raise core.WorkflowError(f'Archived choice image was changed: {data["id"]}')


def summary(project=None, limit=12):
    pid = ('Library' if project == 'library' else core.read_json(core.project_path(project) / 'project.json')['id']) if project else None
    events = []
    for folder in sorted(archive_root().glob('*')):
        if folder.name.startswith('.'):
            continue
        path = core.safe_path(archive_root(), f'{folder.name}/record.json')
        data = core.read_json(path)
        if pid and data['project_id'] != pid:
            continue
        _verify(folder, data)
        m = data['manifest']
        events.append({'id': data['id'], 'project_id': data['project_id'], 'stage': m['stage'],
                       'occurred_at': m.get('occurred_at'), 'recorded_at': data['recorded_at'],
                       'option_count': len(data['options']), 'selected_option_ids': m['selected_option_ids'],
                       'user_feedback': m['user_feedback'], 'supersedes': m.get('supersedes'),
                       'record': path.relative_to(core.ROOT).as_posix()})
    events.sort(key=lambda x: (x['recorded_at'], x['id']))
    return {'total': len(events), 'recent': events[-limit:] if limit else events,
            'preference_summary': 'Context/taste.md', 'archive': 'Library/Taste/Selections',
            'inference_status': 'Agent-maintained evidence-based hypotheses; no automatic preference promotion'}
