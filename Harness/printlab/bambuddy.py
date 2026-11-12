"""Bambuddy v1.2.5.7 adapter; browser access is strictly read-only.

Routes verified against backend/app/api/routes/{printers,library,print_queue,inventory}.py.
An ambiguous write is never automatically retried.
"""
from __future__ import annotations

import datetime as dt
import time
import uuid
import json
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from . import core, materials


class Client:
    def __init__(self, write=False):
        cfg = core.config()
        base = cfg.get("bambuddy_url", "http://127.0.0.1:8017").rstrip("/")
        parsed = urlparse(base)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise core.WorkflowError("Invalid Bambuddy service URL")
        secret = core.read_json(core.ROOT / "Runtime/private/bambuddy.json", {})
        key = secret.get("write_api_key" if write else "read_api_key")
        if not key:
            raise core.WorkflowError("Bambuddy write credential is not configured" if write else "Bambuddy read-only credential is not configured")
        self.http = httpx.Client(base_url=base + "/api/v1/", headers={"X-API-Key": key}, timeout=15, follow_redirects=False, trust_env=False)

    def close(self):
        self.http.close()

    def get(self, path):
        r = self.http.get(path.lstrip("/"))
        r.raise_for_status()
        return r.json()

    def post(self, path, **kwargs):
        r = self.http.post(path.lstrip("/"), **kwargs)
        r.raise_for_status()
        return r.json()

    def patch(self, path, **kwargs):
        r = self.http.patch(path.lstrip("/"), **kwargs)
        r.raise_for_status()
        return r.json()


def telemetry_age(status):
    """last_ams_update is printer-derived, unlike time the HTTP response was fetched."""
    stamp = status.get("last_ams_update")
    if not isinstance(stamp, (float, int)) or stamp <= 0:
        return None
    age = time.time() - stamp
    return age if age >= -5 else None


def sanitize_device(raw):
    allowed = {"id", "name", "connected", "state", "current_print", "progress", "remaining_time", "layer_num", "total_layers", "temperatures", "ams_extruder_map", "awaiting_plate_clear", "hms_errors", "firmware_version", "developer_mode", "sdcard"}
    printer = {k: v for k, v in raw.items() if k in allowed}
    tray_fields = {"id", "tray_info_idx", "tray_id_name", "tray_color", "tray_type", "tray_sub_brands", "remain", "nozzle_temp_min", "nozzle_temp_max", "state", "exists"}
    def tray(value):
        return {k: v for k, v in value.items() if k in tray_fields}
    ams_fields = {"id", "humidity", "temp", "is_ams_ht", "dry_time", "dry_status", "dry_target_temp", "dry_filament"}
    printer["ams"] = [{**{k: v for k, v in unit.items() if k in ams_fields}, "tray": [tray(t) for t in unit.get("tray", [])]} for unit in raw.get("ams", [])]
    printer["vt_tray"] = [tray(t) for t in raw.get("vt_tray", [])]
    printer["nozzles"] = [{k: v for k, v in n.items() if k in {"nozzle_type", "nozzle_diameter"}} for n in raw.get("nozzles", [])]
    fts = raw.get("fila_switch")
    printer["fila_switch"] = {k: v for k, v in fts.items() if k in {"installed", "in_slots", "out_extruders", "stat", "info", "ready"}} if isinstance(fts, dict) else None
    return printer


def device():
    pid = core.config().get("printer_id")
    result = {"state": "unconfigured", "message": "打印机尚未连接；没有实时状态。", "updated_at": None, "printer": None}
    if pid is None:
        return result
    client = None
    try:
        client = Client()
        raw = client.get(f"printers/{pid}/status")
        metadata = {}
        try:
            metadata = client.get(f'printers/{pid}')
        except (httpx.HTTPError, ValueError, core.WorkflowError):
            result['metadata_warning'] = '设备实时状态可读，机型元数据读取失败。'
        age = telemetry_age(raw)
        printer = sanitize_device(raw)
        if isinstance(metadata, dict) and metadata.get('id') == pid:
            printer['model'] = metadata.get('model')
        online = raw.get("connected") is True
        stale = age is None or age > 60
        result.update(state="online" if online else "offline", printer=printer, updated_at=core.now(),
                      telemetry_age_seconds=age, telemetry_source="AMS report; no global printer timestamp available", stale=stale,
                      message="已连接；设备数据时间未知或已过期。" if online and stale else "设备已连接。" if online else "打印机离线；状态不可用于开始打印。")
        assignments, spools = [], []
        try:
            assignments = client.get("inventory/assignments")
            spools = client.get("inventory/spools")
        except (httpx.HTTPError, ValueError, core.WorkflowError):
            pass  # Failure to enrich names must not turn a connected device into offline.
        result["material_slots"] = materials.slot_overview(raw, assignments, spools,
            observed_at=result["updated_at"], printer_model=printer.get('model'))
        reported_fts = (printer.get("fila_switch") or {}).get("installed")
        declared_fts = core.fts_declaration()
        fts_resolution = "conflict" if reported_fts is True and declared_fts is False else "reported_present" if reported_fts is True else "user_confirmed_absent" if declared_fts is False else "unknown"
        result["routing_evidence"] = {"source": "Bambuddy status + confirmed device card", "observed_at": result["updated_at"],
                                      "ams_extruder_map": printer.get("ams_extruder_map"),
                                      "fts_reported_installed": reported_fts,
                                      "fts_user_confirmed_installed": declared_fts, "fts_resolution": fts_resolution,
                                      "validated_for_dispatch": False,
                                      "message": "设备报告与用户确认冲突，禁止提交。" if fts_resolution == "conflict" else "用户已明确确认没有 FTS；设备未报告不等于设备证实。仍需核对本次实际路线、打印板和批准。" if fts_resolution == "user_confirmed_absent" else "FTS 未获得无配件的明确用户确认；不能把空设备字段当作不存在。"}
        from .machine_profiles import single_nozzle_model
        if single_nozzle_model(printer.get('model')):
            result['routing_evidence'].update(fts_resolution='not_applicable',
                message='已识别单喷嘴机型，按当前 AMS 槽位与切片核对供料。')
    except (httpx.HTTPError, core.WorkflowError, ValueError):
        result.update(state="offline", message="无法读取 Bambuddy；设备状态未知。")
    finally:
        if client:
            client.close()
    return result


def material_quantity(spool, baseline=None):
    return materials.quantity(spool, baseline)


def inventory():
    client = None
    try:
        client = Client()
        rows = client.get("inventory/spools")
        baseline_path = core.safe_path(core.ROOT, 'Library/Materials/quantity-baseline.json', require_file=False)
        # Preserve historical evidence when upgrading an existing private workspace.
        if not baseline_path.is_file():
            baseline_path = core.safe_path(core.ROOT, 'Library/Materials/quantity-baseline-2026-10-25.json', require_file=False)
        baseline = core.read_json(baseline_path, {})
        return {"state": "online", "kind": "inventory_ledger", "items": materials.inventory_items(rows, baseline),
                "updated_at": core.now(), "quantity_note": "实际余量未知；设备报告与台账估算分开，历史100%不代表当前满卷。不人工扣料，保留Bambuddy原生追踪。"}
    except (httpx.HTTPError, core.WorkflowError, ValueError, TypeError):
        return {"state": "unavailable", "items": [], "updated_at": None}
    finally:
        if client:
            client.close()


def reported_trays(status):
    trays = {unit['id'] * 4 + tray['id']: tray
             for unit in status.get('ams', []) for tray in unit.get('tray', [])}
    external = status.get('vt_tray', [])
    if not isinstance(external, list):
        external = []
    seen = set()
    for tray in external:
        slot = tray.get('id')
        if slot not in (254, 255) or slot in seen:
            raise core.WorkflowError('External spool report has missing or duplicate nozzle identities')
        seen.add(slot)
        trays[slot] = tray
    return trays


def validate_ready(status, mapping, *, cleared_finished=False, cancelled_reprint=None, printer_model=None):
    from .machine_profiles import single_nozzle_model
    single_nozzle = single_nozzle_model(printer_model)
    if status.get("connected") is not True:
        raise core.WorkflowError("Printer is disconnected")
    from . import cancelled_transition
    verified_cancel = cleared_finished and cancelled_transition.matches_live(status, cancelled_reprint)
    if status.get('state') == 'FAILED' and cleared_finished and not verified_cancel:
        raise core.WorkflowError(
            'FAILED requires verified cancellation evidence for the exact old task and a fresh approved new file. '
            'A successful cancellation and fresh plate-clear approval do not change hardware state. '
            'Inspect the cancelled-task end screen on the printer, then read back its state; '
            'Bambuddy clear-plate only releases its queue and cannot reset FAILED. No resend was made.'
        )
    if status.get("state") != "IDLE" and not (cleared_finished and status.get("state") == "FINISH") and not verified_cancel:
        raise core.WorkflowError("Printer must report IDLE; inspect and clear its plate in Bambuddy first")
    if status.get("awaiting_plate_clear") and not cleared_finished:
        raise core.WorkflowError("Bambuddy still requires plate-clear acknowledgment")
    age = telemetry_age(status)
    if age is None or age > 30:
        raise core.WorkflowError("Fresh printer telemetry (within 30 seconds) is required; freshness is unknown or stale")
    if status.get("hms_errors"):
        raise core.WorkflowError("Resolve printer diagnostics before dispatch")
    if mapping.get("routing_verified") is not True:
        raise core.WorkflowError("Validate the actual filament/nozzle route and record routing_verified")
    if mapping.get("use_ams") is not True:
        raise core.WorkflowError("First adapter supports the verified AMS route only")
    ams = mapping.get("ams_mapping")
    extruders = mapping.get("extruder_mapping")
    if not isinstance(ams, list) or not ams or not all(type(x) is int and x >= 0 for x in ams):
        raise core.WorkflowError("Explicit AMS mapping is required")
    if not isinstance(extruders, list) or len(extruders) != len(ams) or not all(type(x) is int and x in {0, 1} for x in extruders):
        raise core.WorkflowError("Explicit matching extruder mapping is required")
    if "nozzle_mapping" in mapping:
        raise core.WorkflowError("nozzle_mapping is an H2C rack field, not X2D extruder IDs")
    # The first local adapter only supports directly observed AMS-to-extruder routes.
    # FTS changes that relationship; an upstream issue closure is not local validation.
    fts = status.get("fila_switch")
    if isinstance(fts, dict) and fts.get("installed") is True:
        raise core.WorkflowError("Live device reports FTS installed; this conflicts with or exceeds the verified direct route")
    if not single_nozzle and core.fts_declaration() is not False:
        raise core.WorkflowError("FTS absence requires explicit dated user confirmation; unknown/null telemetry is insufficient")
    if not single_nozzle and mapping.get("fts_installed") is not False:
        raise core.WorkflowError("Approved route must explicitly bind fts_installed:false to the current hardware declaration")
    trays = reported_trays(status)
    for slot, extruder in zip(ams, extruders):
        tray = trays.get(slot)
        if not tray or tray.get("exists") is False or tray.get("state") == 9 or not tray.get("tray_type"):
            raise core.WorkflowError("Mapped AMS slot is missing, empty, or has unknown material")
        if slot >= 254:
            if single_nozzle:
                raise core.WorkflowError('This single-nozzle adapter currently requires an observed AMS slot')
            if mapping.get('transport') not in {'bambu_native', 'bambu_studio'} or slot != {0: 255, 1: 254}[extruder]:
                raise core.WorkflowError('External spool does not match its bound X2D physical nozzle')
        elif single_nozzle:
            if extruder != 0:
                raise core.WorkflowError('The selected single-nozzle machine requires physical extruder 0')
            observed = status.get('ams_extruder_map', {}).get(str(slot // 4))
            if observed is not None and observed != 0:
                raise core.WorkflowError('Reported AMS route contradicts the single-nozzle mapping')
        elif status.get("ams_extruder_map", {}).get(str(slot // 4)) != extruder:
            raise core.WorkflowError("Observed AMS-to-extruder routing does not match the approved mapping")


def verify_machine_identity(client, job):
    from .machine_profiles import single_nozzle_model, model_id
    if single_nozzle_model(job.get('sliced_printer_model')):
        metadata = client.get(f"printers/{job['printer_id']}")
        if metadata.get('id') != job['printer_id'] or model_id(metadata.get('model')) != model_id(job['sliced_printer_model']):
            raise core.WorkflowError('Live selected printer identity differs from the sliced machine profile')


def validate_support_profile_identity(settings, tray, index):
    """Support can report family PLA. Bind the exact preset, never just family.

    GFS05 is Bambu Support for PLA/PETG, inherited from fdm_filament_pla.
    A live support spool must not satisfy an ordinary PLA sliced profile.
    """
    def entry(key):
        values = settings.get(key, [])
        return values[index] if isinstance(values, list) and index < len(values) else None
    # Bambu Studio exports the per-filament vector as filament_ids;
    # filament_id is the individual preset/legacy representation.
    expected = entry("filament_ids")
    legacy = entry("filament_id")
    if expected is not None and legacy is not None and expected != legacy:
        raise ValueError("Support filament preset ID fields conflict")
    if expected is None:
        expected = legacy
    reported = tray.get("tray_info_idx")
    support = str(entry("filament_is_support")).lower() in {"1", "true"}
    known_support = any(isinstance(x, str) and x.startswith("GFS") for x in (expected, reported))
    if not support and not known_support:
        return
    if not support:
        raise ValueError("Support spool requires the actual support-material profile, not ordinary PLA")
    if not isinstance(expected, str) or not expected or expected != reported:
        raise ValueError("Support filament preset ID is missing or differs from live tray_info_idx")


def validate_slice_route(jd, job, status):
    """Require actual slice assignments, not the slicer's preferred/nozzle-auto setting.

    This narrow parser deliberately rejects legacy slices without an explicit
    nozzle table; the pinned upstream parser has broader fallback heuristics.
    """
    try:
        with zipfile.ZipFile(core.safe_path(jd, job["artifact"])) as z:
            settings = json.loads(z.read("Metadata/project_settings.config"))
            root = ET.fromstring(z.read("Metadata/slice_info.config"))
        if settings.get("curr_bed_type") != job.get("requested_bed_type"):
            raise ValueError("Sliced plate type differs from the explicitly confirmed physical plate")
        physical = settings["physical_extruder_map"]
        plates = [p for p in root.findall(".//plate") if any(m.get("key") == "index" and m.get("value") == str(job["plate"]) for m in p.findall("metadata"))]
        if len(plates) != 1:
            raise ValueError("Selected plate metadata missing")
        plate = plates[0]
        groups = {}
        for n in plate.findall(".//nozzle"):
            group, index = int(n.attrib["id"]), int(n.attrib["extruder_id"]) - 1
            if index < 0 or group in groups and groups[group] != index:
                raise ValueError("Ambiguous nozzle table")
            groups[group] = index
        actual = {}
        for f in plate.findall(".//filament"):
            slot = int(f.attrib["id"])
            if slot < 1 or slot in actual:
                raise ValueError("Invalid or duplicate sliced filament ID")
            actual[slot] = int(physical[groups[int(f.attrib["group_id"])]])
        mapping = job["mapping"]
        # Studio retains project-wide IDs when exporting one plate (e.g. 3, 9).
        # Bind every active ID explicitly; never infer or omit a sliced filament.
        ids = mapping.get("project_filament_ids", list(range(1, len(mapping["extruder_mapping"]) + 1)))
        if (not isinstance(ids, list) or len(ids) != len(mapping["extruder_mapping"])
                or len(ids) != len(mapping["ams_mapping"])
                or any(type(i) is not int or i < 1 for i in ids) or len(set(ids)) != len(ids)):
            raise ValueError("Invalid project filament ID mapping")
        if "project_filament_ids" in mapping and mapping.get("transport") != "bambu_studio":
            raise ValueError("Explicit project filament IDs require the official Studio route")
        expected = dict(zip(ids, mapping["extruder_mapping"]))
        if actual != expected:
            raise ValueError("Slice assignment differs from approved mapping")
        types = settings["filament_type"]
        trays = reported_trays(status)
        for filament_id, slot in zip(ids, mapping["ams_mapping"]):
            i = filament_id - 1
            validate_support_profile_identity(settings, trays[slot], i)
            sliced_type = str(types[i]).upper()
            live_type = str(trays[slot]["tray_type"]).upper()
            # GFS05 inherits PLA in the official preset, while AMS RFID and
            # Studio's slice_info report PLA-S. Require the exact support ID
            # and support flag above before accepting this one family alias.
            gfs05_alias = (sliced_type == 'PLA' and live_type == 'PLA-S'
                           and trays[slot].get('tray_info_idx') == 'GFS05')
            if sliced_type != live_type and not gfs05_alias:
                raise ValueError("Loaded material differs from sliced filament profile")
    except (KeyError, ValueError, IndexError, TypeError, ET.ParseError) as exc:
        raise core.WorkflowError("Cannot verify exact sliced nozzle/material route; inspect in Bambu Studio. " + str(exc)) from exc


def validate_native_filaments(status, mapping):
    trays = reported_trays(status)
    expected_color = mapping.get("color")
    expected_material = mapping.get("material")
    route = mapping['ams_mapping']
    if len(route) == 1:
        if not expected_color or not expected_material:
            raise core.WorkflowError('Native route requires explicitly identified filament')
        tray = trays[route[0]]
        if tray.get('tray_color', '').upper() != expected_color.upper() or tray.get('tray_sub_brands') != expected_material:
            raise core.WorkflowError('Live filament colour or series differs from approved material')
    else:
        types = mapping.get('filament_types', [])
        colours = mapping.get('filament_colours', [])
        series = mapping.get('filament_series', [])
        if len(types) != len(route) or len(colours) != len(route) or len(series) != len(route):
            raise core.WorkflowError('Each mixed-route filament needs an explicit material, colour and reported-series binding')
        for i, slot in enumerate(route):
            tray = trays[slot]
            if (not types[i] or not colours[i] or str(tray.get('tray_type', '')).upper() != types[i].upper()
                    or str(tray.get('tray_color', '')).upper() != colours[i].upper()
                    or (tray.get('tray_sub_brands') or '') != series[i]):
                raise core.WorkflowError('Live filament colour, material or series differs from approved mixed route')


def preflight(p, jd, job, approval, client, *, native=False, official=False):
    if job.get("trial_only") or core.print_configuration_issues(job):
        raise core.WorkflowError("Trial slice cannot be submitted; configure the printer, route and physical plate then re-slice")
    if job.get("state") != "approved":
        raise core.WorkflowError("Job is not approved, or dispatch has already been attempted")
    if (jd / "dispatch.json").exists():
        raise core.WorkflowError("Dispatch receipt already exists; reconcile status before any manual retry")
    if not approval or approval.get("revoked") or not approval.get("plate_clear") or approval.get("fingerprint") != core.job_fingerprint(p, jd, job):
        raise core.WorkflowError("Valid approval for these exact files and mappings is required")
    from . import slicer_guard
    slicer_guard.assert_safe_archive(core.safe_path(jd, job['artifact']), job.get('plate', 1))
    try:
        approved_at = dt.datetime.fromisoformat(approval["approved_at"])
        approved_age = (dt.datetime.now(dt.timezone.utc) - approved_at).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise core.WorkflowError("Approval timestamp is invalid") from None
    if not 0 <= approved_age <= 1800:
        raise core.WorkflowError("Plate-clear confirmation expired after 30 minutes; obtain fresh user print/plate confirmation and approve again")
    for key in ("plate_clear_confirmed_at", "print_authorized_at"):
        if approval.get(key):
            stamp = dt.datetime.fromisoformat(approval[key])
            age = (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds()
            if not 0 <= age <= 1800:
                raise core.WorkflowError("Original confirmation expired; recording a new approval does not refresh it")
    status = client.get(f"printers/{job['printer_id']}/status")
    verify_machine_identity(client, job)
    device_card = core.read_json(core.ROOT / "Library/Devices/X2D/device.json", {})
    model = device_card.get("model") or device_card.get("user_confirmed", {}).get("model") or job.get("sliced_printer_model", "")
    if not native and not official and "X2D" in str(model).upper() and status.get("sdcard") is not True:
        raise core.WorkflowError("X2D queue/FTPS route has no verified external storage; prepare an explicitly approved native internal-storage route, never automatically fall back or resend")
    if native and job.get("mapping", {}).get("transport") != "bambu_native":
        raise core.WorkflowError("Native route is not bound to approval")
    if official and job.get('mapping', {}).get('transport') != 'bambu_studio':
        raise core.WorkflowError('Official route is not bound to approval')
    from . import cancelled_transition
    cancelled_reprint = cancelled_transition.clearance(p, jd, job, approval) if native else None
    validate_ready(status, job["mapping"], cleared_finished=native or official, cancelled_reprint=cancelled_reprint,
                   printer_model=job.get('sliced_printer_model'))
    validate_slice_route(jd, job, status)
    if native or official:
        validate_native_filaments(status, job['mapping'])
    queue = client.get("queue/")
    # Reject even unassigned pending jobs: releasing a printer must never dispatch another job.
    if any(item.get("status") in {"pending", "printing"} for item in queue):
        raise core.WorkflowError("Bambuddy has another pending or printing job; resolve its queue first")
    return status


def submit(pid, jid, execute=False, client_factory=None):
    if core.read_json(core.job_path(pid, jid) / "job.json").get("mapping", {}).get("transport") == "bambu_studio":
        from . import official
        return official.submit(pid, jid, execute, client_factory)
    if core.read_json(core.job_path(pid, jid) / "job.json").get("mapping", {}).get("transport") == "bambu_native":
        from . import native
        return native.submit(pid, jid, execute, client_factory)
    factory = client_factory or Client
    with core.lock("printer"):
        p, jd = core.project_path(pid), core.job_path(pid, jid)
        job = core.read_json(jd / "job.json")
        approval = core.read_json(jd / "approval.json")
        client = factory(write=execute)
        try:
            status = preflight(p, jd, job, approval, client)
            from . import recovery
            recovery.before_submit(jd, job, approval, client)
            if not execute:
                return {"ready": True, "executed": False, "job_id": jid, "device": status.get("state")}
            receipt = {"id": str(uuid.uuid4()), "job_id": jid, "created_at": core.now(), "state": "uploading", "fingerprint": approval["fingerprint"]}
            core.write_json(jd / "dispatch.json", receipt)  # durable before the first write
            job.update(state="dispatching", updated_at=core.now())
            core.write_json(jd / "job.json", job)
            try:
                with core.safe_path(jd, job["artifact"]).open("rb") as f:
                    uploaded = client.post("library/files", files={"file": (jid + ".gcode.3mf", f, "application/octet-stream")})
                receipt.update(state="uploaded", library_file_id=uploaded["id"])
                core.write_json(jd / "dispatch.json", receipt)
                item = client.post("queue/", json={"printer_id": job["printer_id"], "library_file_id": uploaded["id"], "manual_start": True, "quantity": 1, "plate_id": job["plate"], "ams_mapping": job["mapping"]["ams_mapping"], "use_ams": True, "skip_filament_check": False, "gcode_injection": False, "confirm_outcome": True})
                receipt.update(state="staged", queue_id=item["id"])
                core.write_json(jd / "dispatch.json", receipt)
                staged = client.get(f"queue/{item['id']}")
                if staged.get("manual_start") is not True or staged.get("status") != "pending" or staged.get("ams_mapping") != job["mapping"]["ams_mapping"] or staged.get("printer_id") != job["printer_id"]:
                    raise core.WorkflowError("Staged queue readback differs from approved task")
                queue = client.get("queue/")
                if any(q.get("id") != item["id"] and q.get("status") in {"pending", "printing"} for q in queue):
                    raise core.WorkflowError("Another task entered the queue while staging")
                verify_machine_identity(client, job)
                validate_ready(client.get(f"printers/{job['printer_id']}/status"), job["mapping"],
                               printer_model=job.get('sliced_printer_model'))
                if core.job_fingerprint(p, jd, job) != approval["fingerprint"]:
                    raise core.WorkflowError("Approved files changed while staging")
                receipt.update(state="start_requested", start_requested_at=core.now())
                core.write_json(jd / "dispatch.json", receipt)
                client.post(f"queue/{item['id']}/start")
                receipt.update(state="submitted", updated_at=core.now())
                job.update(state="submitted", queue_id=item["id"], updated_at=core.now())
                core.write_json(jd / "dispatch.json", receipt)
                core.write_json(jd / "job.json", job)
                # Acknowledgment is not physical execution. Re-read the queue and machine.
                return reconcile(pid, jid, client=client)
            except Exception as exc:
                receipt.update(state="unknown", error_type=type(exc).__name__, updated_at=core.now())
                job.update(state="dispatch_unknown", updated_at=core.now())
                core.write_json(jd / "dispatch.json", receipt)
                core.write_json(jd / "job.json", job)
                raise core.WorkflowError("Dispatch outcome requires reconciliation; no retry was sent. Inspect dispatch.json and Bambuddy queue.") from exc
        finally:
            client.close()


def reconcile(pid, jid, client=None):
    jd = core.job_path(pid, jid)
    receipt = core.read_json(jd / "dispatch.json", {})
    if receipt.get('transport') == 'bambu_studio':
        from . import official
        return official.reconcile(pid, jid, client)
    if receipt.get("transport") == "bambu_native":
        from . import native
        return native.reconcile(pid, jid, client)
    if not receipt.get("queue_id"):
        return {"state": "unknown", "message": "No queue ID available; manually inspect Bambuddy before retrying", "receipt": receipt}
    own = client is None
    client = client or Client()
    try:
        job = core.read_json(jd / "job.json")
        if job.get("bambuddy_url") != core.config().get("bambuddy_url"):
            raise core.WorkflowError("Service endpoint changed; cannot reconcile this receipt against another service")
        remote = client.get(f"queue/{receipt['queue_id']}")
        if remote.get("id") != receipt["queue_id"] or remote.get("printer_id") != job["printer_id"] or remote.get("library_file_id") != receipt.get("library_file_id"):
            raise core.WorkflowError("Remote task identity differs from the durable dispatch receipt")
        live = client.get(f"printers/{job['printer_id']}/status")
        state = remote.get("status")
        mapped = {"pending": "submitted", "printing": "printing", "completed": "awaiting_physical_review", "failed": "failed", "cancelled": "cancelled", "skipped": "cancelled"}.get(state, "dispatch_unknown")
        if state == "pending" and remote.get("manual_start"):
            mapped = "staged_requires_reconciliation"
        stamp = core.now()
        age = telemetry_age(live)
        stale = live.get("connected") is not True or age is None or age > 60
        expected_names = {jid, jid + '.gcode', jid + '.gcode.3mf'}
        matching = live.get('current_print') in expected_names
        observation = {"observed_at": stamp, "queue": remote, "device": {k: live.get(k) for k in ("id", "connected", "state", "current_print", "progress", "last_ams_update")},
                       "telemetry_age_seconds": age, "telemetry_source": "AMS report; global printer timestamp unavailable", "stale": stale}
        core.write_json(jd / "observation.json", observation)
        job.update(state=mapped, queue_id=receipt["queue_id"], last_reconciled_at=stamp, updated_at=stamp,
                   reconciliation={"state": "stale" if stale else "current", "observed_at": stamp, "last_success_at": stamp,
                                   "message": "设备数据过期或未知；队列记录已读回。" if stale else "已读取对应队列记录和设备状态。"})
        core.write_json(jd / "job.json", job)
        project = core.read_json(core.project_path(pid) / "project.json")
        project_state = "needs_changes" if mapped == "failed" else mapped
        from .native import _is_current_attempt
        if project_state in {"printing", "awaiting_physical_review", "needs_changes"} and _is_current_attempt(core.project_path(pid), job):
            project.update(status=project_state, updated_at=core.now())
            core.write_json(core.project_path(pid) / "project.json", project)
        return {"job": job, "queue_state": state, "device_state": live.get("state"), "connected": live.get("connected"),
                "matching_task": matching, "fresh": not stale, "telemetry_age_seconds": telemetry_age(live)}
    finally:
        if own:
            client.close()


ACTIVE_JOB_STATES = {"dispatching", "dispatch_unknown", "submitted", "preparing", "running", "printing", "paused", "staged_requires_reconciliation"}


def ensure_no_active_dispatches(current_directory):
    for project in core.list_projects():
        for path in (core.project_path(project["id"]) / "Print").glob("*/job.json"):
            if path.parent != current_directory and core.read_json(path, {}).get("state") in ACTIVE_JOB_STATES:
                raise core.WorkflowError("Another submitted or uncertain PrintLab task requires reconciliation")


def reconcile_active_jobs(client_factory=None):
    """GET-only observer for durable queue receipts or uniquely named native jobs.

    Missing/ambiguous IDs are never guessed. Failures preserve the last observed
    task state and explicitly mark its observation unavailable.
    """
    factory = client_factory or Client
    outcomes = []
    with core.lock("printer"):
        candidates = []
        for project in core.list_projects():
            p = core.project_path(project["id"])
            for path in (p / "Print").glob("*/job.json"):
                job = core.read_json(path, {})
                receipt = core.read_json(path.parent / "dispatch.json", {})
                if job.get("state") in ACTIVE_JOB_STATES and (type(receipt.get("queue_id")) is int or receipt.get("transport") in {"bambu_native", "bambu_studio"}):
                    candidates.append((project["id"], job, path))
        if not candidates:
            return outcomes
        client = None
        try:
            for pid, job, path in candidates:
                try:
                    client = client or factory(write=False)
                    result = reconcile(pid, job["id"], client=client)
                    outcomes.append({"project_id": pid, "job_id": job["id"], "state": result["job"]["state"]})
                except Exception as exc:
                    prior = job.get("reconciliation", {})
                    job["reconciliation"] = {"state": "unavailable", "checked_at": core.now(), "last_success_at": prior.get("last_success_at"),
                                             "error_type": type(exc).__name__, "message": "无法读回对应任务；保留上次状态，不重发。"}
                    core.write_json(path, job)
                    outcomes.append({"project_id": pid, "job_id": job["id"], "state": "unavailable"})
        finally:
            if client:
                client.close()
    return outcomes
