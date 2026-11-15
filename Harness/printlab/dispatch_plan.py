"""Offline route advice before permissions or task creation; never a print preflight."""
from . import core, machine_profiles


def queue_adapter_issues(model, use_ams):
    issues = []
    if not machine_profiles.single_nozzle_model(model):
        issues.append('当前队列适配范围为 A1、A1 mini、P1S 和 X1 Carbon。')
    if use_ams is not True:
        issues.append('PrintLab 队列尚未适配外挂料；Bambuddy 上游支持不等于本版已接好。')
    return issues


def plan(*, model=None, feeding='unknown', permission='unknown', keep_cloud=False):
    """Use explicit facts only; presence of an AMS does not select its feeding route."""
    if feeding not in {'ams', 'external', 'unknown'} or permission not in {'unknown', 'granted', 'declined'}:
        raise core.WorkflowError('Invalid route preference')
    source = 'explicit_argument'
    if not model:
        card = core.read_json(core.ROOT / 'Library/Devices/X2D/device.json', {})
        model = card.get('user_confirmed', {}).get('model') or card.get('model')
        source = 'device_card_not_live'
    result = {
        'scope': 'setup_advice_only', 'executed': False, 'ready_to_print': False,
        'model': machine_profiles.model_id(model) or None, 'model_source': source,
        'feeding': feeding, 'permission_choice': permission,
        'preferred_route': None, 'reasons': [], 'permissions_to_recommend': [],
        'fallback': ['official_studio', 'manual_studio'],
        'before_dispatch': [
            '先核对旧任务、回执和队列；结果未知时停止发送，不能换通道重发。',
            '按具体任务核对文件、设备、材料和清板确认，再通过统一批准与发送入口执行。',
        ],
        'limits': '仅判断本版路线范围；未检查网络、实际权限、设备状态或切片，未修改任务。',
    }
    if not model or feeding == 'unknown':
        result.update(next_step='confirm_missing_facts',
                      reasons=['读取已有记录，补齐机型和本次供料方式；不能把检测到 AMS 当作选用 AMS。'])
        return result
    issues = queue_adapter_issues(model, feeding == 'ams')
    if issues or permission == 'declined' or keep_cloud:
        result.update(preferred_route='official_studio', next_step='prepare_studio_fallback')
        result['reasons'] = issues or [
            '用户拒绝 Bambuddy 控制授权。' if permission == 'declined'
            else '用户要求保留云功能；优先沿用官方 Studio，保持现有网络模式。']
        result['studio_permissions'] = '需要自动操作时才建议对应系统权限；用户拒绝或恢复一次仍失败时交接人工发送。'
        return result
    result.update(preferred_route='bambuddy_queue', next_step=(
        'check_connection_readonly' if permission == 'granted' else 'explain_required_permissions'))
    result['permissions_to_recommend'] = [
        '配置专用写入凭据，授予文件上传、队列管理与启动权限；保留只读凭据。',
        '核对机型和固件的 LAN Only / Developer Mode 要求，说明云功能影响后由用户选择。',
    ] if permission == 'unknown' else []
    result['reasons'] = ['本版支持这套机型与 AMS 组合；实际发送仍须预检和设备验收。']
    return result
