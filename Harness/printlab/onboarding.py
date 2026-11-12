"""Resumable onboarding. Host agents create chats; this module records evidence."""
from __future__ import annotations

import copy
import platform
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import bambuddy, core, workspace


STATE = 'Context/onboarding.json'
ROLES = {'sarah': ('Sarah · 3D 打印顾问', '设备、材料、打印问题与制作建议'),
         'mike': ('Mike · 工作流设计师', '工具连接、工作习惯、工作台与流程改进')}
CAPABILITIES = {'local_files', 'terminal', 'chat_create', 'chat_read', 'desktop_control',
                'image_generation', 'cad_viewer'}


def state():
    path = core.safe_path(core.ROOT, STATE, require_file=False)
    value = core.read_json(path, {'schema_version': 1, 'version': 0, 'host': {}, 'roles': {},
                                  'answers': {}, 'events': []})
    if value.get('schema_version') != 1:
        raise core.WorkflowError('Unsupported onboarding schema; preserve the file and check the installed version')
    return value


def _save(value, event):
    value['version'] += 1
    value['updated_at'] = core.now()
    value['events'].append({'at': value['updated_at'], **event})
    core.write_json(core.safe_path(core.ROOT, STATE, require_file=False), value)
    return value


def _version(value, expected):
    if type(expected) is not int or value['version'] != expected:
        raise core.WorkflowError('Onboarding changed; reread onboarding status and merge the new information')


def record_host(name, capabilities, evidence, expected):
    name = workspace.required_text(name, 'Host name', 200)
    evidence = workspace.required_text(evidence, 'Host tool evidence')
    if not isinstance(capabilities, dict) or set(capabilities) - CAPABILITIES:
        raise core.WorkflowError('Unknown host capability')
    if any(type(v) is not bool for v in capabilities.values()):
        raise core.WorkflowError('Host capabilities must be true or false')
    with core.lock('onboarding'):
        value = state()
        _version(value, expected)
        value['host'] = {'name': name, 'capabilities': capabilities, 'evidence': evidence,
                         'observed_at': core.now()}
        return _save(value, {'kind': 'host_observed'})


def answer(key, text, source, expected):
    if key not in {'usage_goals', 'cloud_needs', 'additional_materials'}:
        raise core.WorkflowError('Unknown onboarding question')
    text = workspace.required_text(text, 'User answer')
    source = workspace.required_text(source, 'User answer source')
    # Answers keep interview progress. Existing profile and inventory remain authoritative.
    with core.lock('onboarding'):
        value = state()
        _version(value, expected)
        if key in {'usage_goals', 'cloud_needs'}:
            request_id = hashlib.sha256(f'{key}:{expected}:{text}:{source}'.encode()).hexdigest()
            current = workspace.document('profile')
            workspace.append_note('profile', text, source, request_id, current['sha256'])
            value['answers'][key] = {'document': 'Context/profile.md', 'request_id': request_id, 'at': core.now()}
        else:
            value['answers'][key] = {'text': text, 'source': source, 'at': core.now()}
        return _save(value, {'kind': 'answer', 'key': key})


def _role(role):
    key = 'sarah' if role.lower() == 'sara' else role.lower()
    if key not in ROLES:
        raise core.WorkflowError('Role must be Mike or Sarah (Sara is accepted for existing chats)')
    return key


def role_prompt(role, request_id):
    title, duties = ROLES[role]
    return (f'你是{title}。共同工作空间为 {core.ROOT}。职责为{duties}。'
            '先读取这个工作空间的 AGENTS.md，使用实际 CLI 执行 context，读取设备、材料、'
            '用户偏好、经验与已有项目。首次回复请介绍职责，列出真实读到的配置、尚缺信息及一项下一步。'
            '沿用初始会话已经收集的答案，避免重复访谈。每次接手作品都先按稳定项目 ID 读取 context，'
            '收尾保存交接。事实、经验或偏好更新使用 workspace 命令的版本检查，保留用户原话与来源。'
            '设置和设计不能触发实体打印，具体打印仍经共同批准与发送入口。'
            f'本次角色建立标识为 {request_id}，恢复时用它核对已有聊天，避免重复创建。')


def reserve_role(role, request_id, expected):
    role = _role(role)
    request_id = workspace.required_text(request_id, 'Request ID', 100)
    with core.lock('onboarding'):
        value = state()
        existing = value['roles'].get(role)
        if existing:
            return {'version': value['version'], 'role': existing, 'create_allowed': False,
                    'next_action': 'Read the existing chat or reconcile the pending host creation before continuing'}
        _version(value, expected)
        capabilities = value['host'].get('capabilities', {})
        if not all(capabilities.get(k) is True for k in ('local_files', 'terminal', 'chat_create', 'chat_read')):
            raise core.WorkflowError('Host file/terminal and chat creation/read tools must be observed first')
        record = {'role': role, 'title': ROLES[role][0], 'status': 'creating',
                  'request_id': request_id, 'workspace': str(core.ROOT),
                  'prompt': role_prompt(role, request_id), 'created_at': core.now()}
        value['roles'][role] = record
        _save(value, {'kind': 'role_reserved', 'role': role, 'request_id': request_id})
        return {'version': value['version'], 'role': record, 'create_allowed': True,
                'next_action': 'Use the current host chat tool, then record its real thread ID and first reply'}


def record_role(role, receipt, expected, adopt=False):
    role = _role(role)
    required = {'request_id', 'thread_id', 'host_id', 'workspace', 'source'}
    optional = {'first_reply', 'context_paths', 'title'}
    if not isinstance(receipt, dict) or not required <= receipt.keys() or receipt.keys() - required - optional:
        raise core.WorkflowError('Role receipt requires request_id, thread_id, host_id, workspace and source')
    for key in required:
        workspace.required_text(receipt[key], key)
    declared_root = Path(receipt['workspace'].replace('\\', '/')).expanduser()
    if not declared_root.is_absolute() or declared_root.resolve() != core.ROOT.resolve():
        raise core.WorkflowError('The chat must use this exact shared workspace')
    receipt = {**receipt, 'workspace': str(core.ROOT)}
    reply = receipt.get('first_reply')
    paths = receipt.get('context_paths', [])
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        raise core.WorkflowError('context_paths must contain observed shared document paths')
    # Resolve against this workspace, never accept a suffix from another workspace.
    path_type = PureWindowsPath if PureWindowsPath(receipt['workspace']).drive else PurePosixPath
    root = path_type(receipt['workspace'])
    normalized = []
    for raw in paths:
        path = path_type(raw.replace('\\', '/'))
        if '..' in path.parts:
            raise core.WorkflowError('Shared context paths must stay inside this workspace')
        if path.is_absolute():
            try:
                path = path.relative_to(root)
            except ValueError:
                raise core.WorkflowError('Shared context was read from another workspace') from None
        normalized.append(path.as_posix())
    receipt = {**receipt, 'context_paths': normalized} if 'context_paths' in receipt else receipt
    paths = normalized
    if reply is not None:
        workspace.required_text(reply, 'First reply', 20000)
        if not {'AGENTS.md', 'Context/profile.md', 'Context/workflow.md'} <= set(paths):
            raise core.WorkflowError('Record the shared context paths actually read by the role')
    with core.lock('onboarding'):
        value = state()
        existing = value['roles'].get(role)
        if not existing and adopt:
            _version(value, expected)
            capabilities = value['host'].get('capabilities', {})
            if not all(capabilities.get(k) is True for k in ('local_files', 'terminal', 'chat_read')):
                raise core.WorkflowError('Observe local workspace and host chat read tools before adopting a chat')
            existing = {'role': role, 'title': ROLES[role][0], 'status': 'created',
                        'request_id': receipt['request_id'], 'workspace': str(core.ROOT),
                        'adopted_at': core.now()}
            value['roles'][role] = existing
        if not existing or existing['request_id'] != receipt['request_id']:
            raise core.WorkflowError('No matching role reservation; recover or reserve the role first')
        if existing.get('thread_id') and existing['thread_id'] != receipt['thread_id']:
            raise core.WorkflowError('Role already has a different chat; reconcile it before changing the binding')
        if all(existing.get(k) == v for k, v in receipt.items()):
            return value
        _version(value, expected)
        existing.update(receipt)
        existing.update(status='introduced' if existing.get('first_reply') else 'created', observed_at=core.now())
        return _save(value, {'kind': 'role_observed', 'role': role, 'status': existing['status']})


def release_role(role, request_id, evidence, expected):
    """Release only an unresolved reservation after the host confirms no chat exists."""
    role = _role(role)
    evidence = workspace.required_text(evidence, 'Host search and creation failure evidence')
    with core.lock('onboarding'):
        value = state()
        _version(value, expected)
        record = value['roles'].get(role, {})
        if (record.get('status') != 'creating' or record.get('thread_id')
                or record.get('request_id') != request_id):
            raise core.WorkflowError('Only the matching unbound creation reservation can be released')
        del value['roles'][role]
        return _save(value, {'kind': 'role_creation_absent', 'role': role,
                             'reservation': record, 'host_evidence': evidence})


def discover(client_factory=None):
    """List actual devices without selecting one or changing an existing connection."""
    client = (client_factory or bambuddy.Client)()
    try:
        rows = client.get('printers/')
        if not isinstance(rows, list):
            raise core.WorkflowError('Unexpected printer discovery response')
        fields = {'id', 'name', 'model', 'printer_type', 'firmware_version'}
        return {'printers': [{k: v for k, v in row.items() if k in fields} for row in rows],
                'observed_at': core.now(), 'selected_printer_id': core.config().get('printer_id')}
    finally:
        client.close()


def adopt_device(expected_sha256, client_factory=None):
    """Persist sanitized observations without replacing user-confirmed facts."""
    printer_id = core.config().get('printer_id')
    if printer_id is None:
        raise core.WorkflowError('Select a discovered printer first')
    cfg = workspace.connection()
    client = (client_factory or bambuddy.Client)()
    try:
        metadata = client.get(f'printers/{printer_id}')
        live = client.get(f'printers/{printer_id}/status')
    finally:
        client.close()
    if live.get('connected') is not True or metadata.get('id') != printer_id:
        raise core.WorkflowError('The selected printer identity and live connection must be verified')
    model = metadata.get('model') or metadata.get('printer_type')
    if not isinstance(model, str) or not model.strip():
        raise core.WorkflowError('Printer model is missing from device metadata')
    with core.lock('shared-context'):
        if workspace.connection() != cfg:
            raise core.WorkflowError('Device selection changed during discovery; read the selected device again')
        path = core.safe_path(core.ROOT, workspace.DOCUMENTS['device'], require_file=False)
        workspace.check_version(path, expected_sha256)
        card = core.read_json(path, {'schema_version': 1, 'user_confirmed': {}})
        confirmed_model = card.get('user_confirmed', {}).get('model')
        card['connection'] = {'printer_id': printer_id, 'bambuddy_url': cfg['bambuddy_url']}
        card['observed'] = {'model': model, 'name': metadata.get('name'),
                            'at': core.now(), 'source': 'Bambuddy selected printer and status',
                            'telemetry_age_seconds': bambuddy.telemetry_age(live),
                            'status': bambuddy.sanitize_device(live)}
        card['model'] = confirmed_model or model
        from .machine_profiles import model_id
        card['verification_status'] = 'identity_conflict' if confirmed_model and model_id(confirmed_model) != model_id(model) else 'connected_readonly'
        core.write_json(path, card)
        return workspace.document('device')


def view(device=None, inventory=None):
    value = copy.deepcopy(state())
    card = core.read_json(core.safe_path(core.ROOT, workspace.DOCUMENTS['device'], require_file=False), {})
    cfg = workspace.connection()
    binding = card.get('connection', {})
    selected_device_matches = bool(binding and binding.get('printer_id') == cfg['printer_id']
                                   and binding.get('bambuddy_url') == cfg['bambuddy_url'])
    questions = []
    if core.config().get('printer_id') is None:
        questions.append({'id': 'printer', 'text': '你使用哪些打印机？请选择这次要连接的一台。'})
    for key, text in [('cloud_needs', '你现在怎样使用 Handy 和 Studio？有哪些连接方式需要保留？'),
                      ('additional_materials', '除了已装载和已登记的耗材，你还有哪些材料？'),
                      ('usage_goals', '你主要想制作什么，最重视哪些使用效果？')]:
        if key not in value['answers']:
            questions.append({'id': key, 'text': text})
    roles = [{**{'role': role, 'title': title, 'status': 'pending'}, **value['roles'].get(role, {})}
             for role, (title, _) in ROLES.items()]
    next_actions = []
    if questions:
        next_actions.append({'kind': 'interview', 'text': '由首次配置会话补齐真实缺项', 'questions': questions})
    for role in roles:
        if role['status'] != 'introduced':
            next_actions.append({'kind': 'role', 'role': role['role'], 'text': f"完成 {role['title']} 的创建与首次介绍"})
    if card.get('verification_status') != 'connected_readonly' or not selected_device_matches:
        next_actions.append({'kind': 'device', 'text': '核对设备身份、打印板、喷嘴与实际供料连接'})
    return {**value, 'workspace': str(core.ROOT), 'platform': platform.system(), 'roles': roles,
            'questions': questions, 'next_actions': next_actions,
            'device_card': card, 'device': device, 'inventory': inventory,
            'selected_device_matches': selected_device_matches,
            'shared_documents': [{'name': name, 'path': row['path'], 'sha256': row['sha256']}
                                 for name in workspace.DOCUMENTS if (row := workspace.document(name))],
            'team_document': workspace.document('team')['text'],
            'interview_complete': not questions,
            'team_ready': all(role['status'] == 'introduced' for role in roles),
            'printing_verified': False}
