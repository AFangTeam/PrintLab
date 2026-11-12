"""Workbench access to the existing single-dispatch Bambuddy queue adapter."""
from . import bambuddy, core, machine_profiles


def capability(report):
    blockers = []
    pid, jid = report.get('project_id'), report.get('job_id')
    if not pid or not jid:
        return {'available': False, 'kind': 'bambuddy_queue', 'message': '请选择已绑定具体设备的待打印任务'}
    job = core.read_json(core.job_path(pid, jid) / 'job.json')
    if not machine_profiles.single_nozzle_model(job.get('sliced_printer_model')):
        blockers.append('当前队列按钮适配 A1、A1 mini、P1S 和 X1 Carbon 的 AMS 路线')
    if job.get('mapping', {}).get('transport') != 'bambuddy_queue':
        blockers.append('任务尚未明确绑定 Bambuddy 队列通道')
    if report.get('device', {}).get('state') != 'IDLE':
        blockers.append('队列通道需要设备就绪为 IDLE；请核对上一盘与设备状态')
    if report.get('transport', {}).get('sdcard') is not True:
        blockers.append('设备未报告可用存储卡，文件传输条件待核对')
    secret = core.read_json(core.ROOT / 'Runtime/private/bambuddy.json', {})
    if not secret.get('write_api_key'):
        blockers.append('Bambuddy 写入凭据尚未配置，需具备文件、队列和启动权限')
    return {'available': not blockers, 'kind': 'bambuddy_queue', 'blockers': blockers,
            'message': '；'.join(blockers) if blockers else '可尝试通过 Bambuddy 队列发送，设备接受结果须另行读回',
            'independent_dispatch_verified': False,
            'limitations': ['实际接收取决于设备固件及当前连接权限', '发送结果未知时先对账', '仅已核对的具体任务可启动']}


def dispatch(pid, jid):
    # This reuses approval, file binding, durable upload/start receipts and the printer lock.
    # An exception after any attempted write is handled as uncertain by the workbench.
    receipt_path = core.job_path(pid, jid) / 'dispatch.json'
    try:
        result = bambuddy.submit(pid, jid, execute=True)
    except Exception as exc:
        if not receipt_path.exists():
            from .studio_bridge import BeforeSendError
            raise BeforeSendError(str(exc)) from exc
        raise
    receipt = core.read_json(receipt_path, {})
    return {'command_sent': bool(receipt.get('start_requested_at')), 'executed': False,
            'transport': 'bambuddy_queue', 'queue_id': receipt.get('queue_id'),
            'printer_accepted': result.get('matching_task') is True and result.get('fresh') is True}
