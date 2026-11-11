"""Browser-only, same-origin control endpoints. Credentials stay server-side."""
import secrets
import time
import os
from urllib.parse import urlsplit
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, StrictBool, ConfigDict, Field
from . import core, prepared, workbench

router = APIRouter(prefix='/api/prepared')
_sessions = {}

def _load_sessions():
    return core.read_json(core.ROOT / 'Runtime/private/workbench-sessions.json', {})

def _save_sessions(rows):
    path = core.ROOT / 'Runtime/private/workbench-sessions.json'
    core.write_json(path, rows)
    os.chmod(path, 0o600)


def _origin(request):
    config = core.config()
    port = os.environ.get('PRINTLAB_STUDIO_PORT', '8018')
    allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
    if config.get('tailscale_ip'):
        allowed.add(config['tailscale_ip'] + ':' + port)
    configured = urlsplit(config.get('studio_url', f'http://127.0.0.1:{port}'))
    allowed.add(configured.netloc)
    host = request.headers.get('host', '')
    if host not in allowed or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '仅允许从 PrintLab 工作台操作')
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{host}':
        raise HTTPException(403, '网页来源不匹配')
    return origin

def _session(request, *, write=False):
    origin = _origin(request)
    sid = request.cookies.get('printlab_session', '')
    row = _load_sessions().get(sid)
    if not row or time.time() - row['at'] > 43200:
        raise HTTPException(403, '会话已过期，请刷新工作台')
    if write and (not origin or not secrets.compare_digest(request.headers.get('x-printlab-csrf', ''), row['csrf'])):
        raise HTTPException(403, '请从工作台核验并确认打印')
    return sid

@router.get('')
def catalogue(request: Request):
    result = prepared.catalogue()
    for item in result['items']:
        item['operation'] = workbench.latest_operation(item['project_id'], item['job_id'])
    return result

@router.get('/session')
def session(request: Request, response: Response):
    _origin(request)
    now = time.time()
    with core.lock('workbench-sessions'):
        rows = {k: v for k, v in _load_sessions().items() if now - v['at'] <= 43200}
        sid = request.cookies.get('printlab_session')
        if sid not in rows:
            sid = secrets.token_urlsafe(32)
            rows[sid] = {'csrf': secrets.token_urlsafe(32), 'at': now}
        _save_sessions(rows)
    response.set_cookie('printlab_session', sid, httponly=True, samesite='strict', secure=request.url.scheme == 'https', max_age=43200)
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token': rows[sid]['csrf']}

@router.post('/{pid}/{jid}/check')
def check(pid: str, jid: str, request: Request):
    owner = _session(request, write=True)
    try:
        return workbench.check(pid, jid, owner=owner)
    except core.WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc

class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    check_token: str = Field(min_length=20, max_length=100)
    request_id: str = Field(min_length=32, max_length=36)
    plate_clear: StrictBool

@router.post('/{pid}/{jid}/start', status_code=202)
def start(pid: str, jid: str, body: Start, request: Request):
    owner = _session(request, write=True)
    try:
        return workbench.start(pid, jid, owner=owner, **body.model_dump())
    except core.WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get('/operations/{opid}')
def operation(opid: str, request: Request):
    owner = _session(request)
    try:
        return workbench.operation(opid, owner)
    except core.WorkflowError as exc:
        raise HTTPException(404, str(exc)) from exc

@router.post('/operations/{opid}/reconcile')
def reconcile(opid: str, request: Request):
    owner = _session(request, write=True)
    try:
        return workbench.reconcile_operation(opid, owner)
    except core.WorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get('/sender/capability')
def sender_capability(request: Request):
    _origin(request)
    from . import studio_bridge
    result = studio_bridge.capability()
    observed = result.pop('observation', {})
    result['permissions'] = {k: observed.get(k) is True for k in ('accessibility', 'screen_capture')}
    result['setup_required'] = result.get('setup_supported', True) and not all(result['permissions'].values())
    return result

class EnableSender(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_permissions: StrictBool

@router.post('/sender/enable')
def enable_sender(body: EnableSender, request: Request):
    _session(request, write=True)
    if body.request_permissions is not True:
        raise HTTPException(400, '需要本人明确选择为发送助手启用系统权限')
    from . import studio_bridge
    if not hasattr(studio_bridge, 'setup_permissions'):
        raise HTTPException(409, '发送助手正在准备，请稍后刷新')
    return studio_bridge.setup_permissions()
