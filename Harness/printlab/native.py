"""X2D eMMC transport: exact approval, one attempt, read-only recovery.

The full upstream MCP safety gate owns execution. Observation never dispatches.
"""
import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from . import core, bambuddy

CLIENT_TIMEOUT_SECONDS = 390
TERMINATE_GRACE_SECONDS = 2
TASK_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _terminate_group(proc):
    """Kill only this freshly created session, including Node/MCP/helper children."""
    def send(sig):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
    send(signal.SIGTERM)
    try:
        proc.communicate(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        send(signal.SIGKILL)
        proc.communicate(timeout=TERMINATE_GRACE_SECONDS)
    # A parent can exit on TERM while a descendant ignores it and closes stdout.
    send(signal.SIGKILL)


def run_client(jd, job, mode, approval=None, *, timeout=None):
    client_path = core.ROOT / "Harness/native-client.mjs"
    if not client_path.is_file():
        raise core.WorkflowError("原生适配器尚未独立安装。请按 docs/PRINTING.md 使用官方 Bambu Studio 发送流程。")
    toolchain = core.read_json(core.ROOT / "Harness/native-toolchain.json", {})
    pinned_node = toolchain.get("node", {})
    node = pinned_node.get("path") or shutil.which("node")
    if pinned_node.get("sha256") and core.digest(Path(node)) != pinned_node["sha256"]:
        raise core.WorkflowError("Pinned Node binary changed; no native call made")
    if not node:
        raise core.WorkflowError("Node runtime is unavailable; no native call made")
    for entry in toolchain.get("files", []):
        if entry.get("label") in {"adapter", "offline inspection"}:
            if core.digest(core.safe_path(core.ROOT, entry["path"])) != entry["sha256"]:
                raise core.WorkflowError("Pinned native adapter changed; no native call made")
    from . import cancelled_transition
    approval = approval or core.read_json(jd/'approval.json')
    proof = cancelled_transition.clearance(core.project_path(job['project_id']), jd, job, approval) if mode != 'inspect' and approval else None
    request = {"mode": mode, "file": str(core.safe_path(jd, job["artifact"])),
               "sha256": job["artifact_sha256"], "plate": job["plate"], "job_id": job["id"],
               "ams_mapping": job["mapping"]["ams_mapping"], "approval": approval, "cancelled_reprint": proof}
    env = {k: v for k, v in os.environ.items() if k not in {"NODE_OPTIONS", "NODE_PATH", "LD_PRELOAD"} and not k.startswith("DYLD_")}
    proc = subprocess.Popen([node, str(client_path)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True, env=env)
    try:
        stdout, _stderr = proc.communicate(json.dumps(request), timeout=timeout or CLIENT_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        _terminate_group(proc)
        raise core.WorkflowError("Native interface timed out or was interrupted; its child process group was stopped. Dispatch may have happened: reconcile, never automatically resend") from None
    except Exception:
        _terminate_group(proc)
        raise core.WorkflowError("Native interface failed while reading its receipt; child processes stopped, outcome requires reconciliation") from None
    try:
        if len(stdout) > 4 * 1024 * 1024:
            raise ValueError("oversized receipt")
        data = json.loads(stdout)
        if not isinstance(data, dict):
            raise ValueError("invalid receipt")
    except ValueError as exc:
        raise core.WorkflowError("Native interface returned no valid receipt; inspect printer before any retry") from exc
    if mode == "inspect" and data.get("phase") == "offline_inspection" and data.get("executed") is False:
        return data
    if proc.returncode or not data.get("ok"):
        raise core.WorkflowError(data.get("error", "Native check failed"))
    return data


def check(pid, jid):
    """Fresh validation without uploads; successful observation does not approve."""
    jd = core.job_path(pid, jid)
    job = core.read_json(jd / "job.json")
    core.job_fingerprint(core.project_path(pid), jd, job)
    try:
        result = run_client(jd, job, "check")
        client = bambuddy.Client()
        try:
            live = client.get(f"printers/{job['printer_id']}/status")
        finally:
            client.close()
        result['dispatch_capability'] = {
            'state': 'requires_official_app' if live.get('developer_mode') is False else 'not_proven',
            'message': '只读状态和刀路检查通过不代表发送签名可用；未发送探测打印命令。',
            'developer_mode': live.get('developer_mode')}
    except Exception as exc:
        core.write_json(jd / "native-check.json", {"at": core.now(), "ok": False, "error": str(exc), "executed": False})
        raise
    core.write_json(jd / "native-check.json", {"at": core.now(), **result})
    return result


def submit(pid, jid, execute=False, client_factory=None, runner=None):
    runner = runner or run_client
    with core.lock("printer"):
        p, jd = core.project_path(pid), core.job_path(pid, jid)
        job, approval = core.read_json(jd / "job.json"), core.read_json(jd / "approval.json")
        client = (client_factory or bambuddy.Client)()
        try:
            if job.get("mapping", {}).get("transport") != "bambu_native":
                raise core.WorkflowError("Native route must be bound in the approved mapping")
            live = bambuddy.preflight(p, jd, job, approval, client, native=True)
            from . import recovery
            recovery.before_submit(jd, job, approval, client)
            if live.get('developer_mode') is False:
                core.write_json(jd/'native-capability.json', {'at':core.now(), 'state':'unsupported_mode',
                    'executed':False, 'reason':'Developer mode is off; use the official signed application. Read-only connectivity is not dispatch capability.'})
                raise core.WorkflowError('Native dispatch unavailable in current non-developer mode; use the official signed application. No print command sent.')
            checked = runner(jd, job, "check")
            core.write_json(jd / "native-check.json", {"at": core.now(), **(checked or {})})
            if not execute:
                return {"ready": True, "executed": False, "transport": "bambu_native", "storage": "internal"}
            # Recheck files, actual material/route and current device after native validation.
            live = bambuddy.preflight(p, jd, job, approval, client, native=True)
            if live.get('developer_mode') is False:
                raise core.WorkflowError('Printer mode changed before dispatch; no print command sent')
            receipt = {"job_id": jid, "transport": "bambu_native", "storage": "internal", "state": "start_requested",
                       "created_at": core.now(), "fingerprint": approval["fingerprint"], "expected_task_suffix": jid}
            core.write_json(jd / "dispatch.json", receipt)
            job.update(state="dispatching", updated_at=core.now())
            core.write_json(jd / "job.json", job)
            project = core.read_json(p / "project.json")
            project.update(current_job_id=jid, status="dispatching", updated_at=core.now())
            core.write_json(p / "project.json", project)
            try:
                result = runner(jd, job, "print", approval)
                receipt.update(state="submitted", result=result, updated_at=core.now())
                job.update(state="submitted", updated_at=core.now())
            except Exception as exc:
                receipt.update(state="unknown", error=str(exc), updated_at=core.now())
                job.update(state="dispatch_unknown", updated_at=core.now())
                project.update(status="dispatch_unknown", updated_at=core.now())
                core.write_json(p / "project.json", project)
                raise core.WorkflowError("Native dispatch needs reconciliation; no retry sent. " + str(exc)) from exc
            finally:
                core.write_json(jd / "dispatch.json", receipt)
                core.write_json(jd / "job.json", job)
            return reconcile(pid, jid, client)
        finally:
            client.close()


def observed_state(live):
    raw = str(live.get("state") or "").upper()
    if raw in {"PREPARE", "PREPARING", "HEATING"}:
        return "preparing", "准备 / 加热中；首层尚未核实"
    if raw in {"PAUSE", "PAUSED"}:
        return "paused", "设备报告暂停"
    if raw == "RUNNING":
        def positive(value):
            return type(value) in {int, float} and value > 0
        if positive(live.get("layer_num")) or positive(live.get("progress")):
            return "printing", "设备报告打印进度；实物仍待检查"
        if live.get("layer_num") == 0 or live.get("progress") == 0:
            return "preparing", "任务已启动，等待首层进度"
        return "running", "设备报告运行中；首层进度未知"
    return {"FINISH": ("awaiting_physical_review", "设备报告完成，等待实物验收"),
            "FAILED": ("failed", "设备报告任务失败"),
            "CANCELLED": ("cancelled", "设备报告任务取消")}.get(raw, ("dispatch_unknown", "设备状态无法对应明确阶段，先核对任务"))


def _is_current_attempt(p, job):
    return core.is_current_attempt(p, job)


def reconcile(pid, jid, client=None):
    jd = core.job_path(pid, jid)
    job, receipt = core.read_json(jd / "job.json"), core.read_json(jd / "dispatch.json")
    if not receipt or receipt.get("transport") != "bambu_native" or receipt.get("job_id") != jid:
        raise core.WorkflowError("No matching native receipt")
    if job.get("printer_id") != core.config().get("printer_id") or job.get("bambuddy_url") != core.config().get("bambuddy_url"):
        raise core.WorkflowError("Target device changed")
    own = client is None
    client = client or bambuddy.Client()
    try:
        live = client.get(f"printers/{job['printer_id']}/status")
        primary = live.get("current_print")
        names = [primary] if isinstance(primary, str) and primary.strip() else [live.get(k) for k in ("subtask_name", "gcode_file") if isinstance(live.get(k), str) and live[k].strip()]
        pattern = r"(?:^|/)(checked-" + TASK_UUID + "-" + re.escape(jid) + r")(?:\.gcode(?:\.3mf)?)?$"
        matches = [re.search(pattern, name) for name in names]
        candidates = {m.group(1) for m in matches if m}
        pinned = receipt.get("remote_task")
        # A current primary name wins over potentially stale secondary fields.
        # When primary is absent, conflicting fallback names remain unknown.
        task = next(iter(candidates)) if len(candidates) == 1 and all(matches) else None
        matching = task is not None and (not pinned or pinned == task)
        age = bambuddy.telemetry_age(live)
        fresh = live.get("connected") is True and age is not None and age <= 60
        stamp = core.now()
        previous = job.get("reconciliation", {})
        message = "设备离线或读数过期，保留上次状态" if not fresh else "当前任务与回执不匹配，不能归为本次执行"
        observation_state = "stale" if not fresh else "unmatched"
        if fresh and matching:
            state, message = observed_state(live)
            job["state"] = state
            job["execution_phase"] = message
            receipt["remote_task"] = task
            core.write_json(jd / "dispatch.json", receipt)
            observation_state = "current"
            evidence = job.setdefault("execution_evidence", {})
            if state in {"preparing", "running", "printing", "paused"}:
                evidence.setdefault("started_observed_at", stamp)
            if type(live.get("layer_num")) in {int, float} and live["layer_num"] >= 1:
                evidence.setdefault("first_layer_reported_at", stamp)
            if state == "awaiting_physical_review":
                evidence.setdefault("completed_reported_at", stamp)
            job["printer_progress"] = {k: live.get(k) for k in ("progress", "layer_num", "total_layers", "state")}
        observed = {"at": stamp, "matching_task": matching, "fresh": fresh, "remote_task": task,
                    "device": bambuddy.sanitize_device(live)}
        core.write_json(jd / "native-observation.json", observed)
        job.update(updated_at=stamp, last_reconciled_at=stamp,
                   reconciliation={"state": observation_state, "observed_at": stamp,
                                   "last_success_at": stamp if matching and fresh else previous.get("last_success_at"),
                                   "message": message})
        core.write_json(jd / "job.json", job)
        p = core.project_path(pid)
        if matching and fresh and _is_current_attempt(p, job):
            project = core.read_json(p / "project.json")
            project.update(status="needs_changes" if job["state"] in {"failed", "cancelled"} else job["state"],
                           current_job_id=jid, updated_at=stamp)
            core.write_json(p / "project.json", project)
        return {"job": job, "job_id": jid, "job_state": job["state"], "matching_task": matching, "fresh": fresh,
                "device_state": live.get("state"), "progress": live.get("progress"), "temperatures": live.get("temperatures")}
    finally:
        if own:
            client.close()
