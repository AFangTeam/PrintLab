import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from printlab import core, bambuddy
from printlab import slicer_guard


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    # Synthetic safety-complete commands, only ever used with in-memory transports.
    templates = {key: 'SYNTHETIC TEST TEMPLATE: ' + key for key in slicer_guard.FIELDS}
    monkeypatch.setattr(slicer_guard, 'official_templates', lambda: templates)
    monkeypatch.setattr(core, "ROOT", tmp_path)
    core.write_json(tmp_path / "Runtime/config.json", {"printer_id": 7})
    core.write_json(tmp_path / "Library/Devices/X2D/device.json", {"user_confirmed": {"fts_installed": False, "fts_confirmation_quote": "Synthetic test operator explicitly confirms no FTS", "fts_confirmation_date": "2026-10-25"}})
    core.new_project("Route validation fixture")
    p = core.project_path("P001")
    (p / "Design/v001").mkdir()
    (p / "Exports/v001").mkdir()
    (p / "Design/v001/model.py").write_text("# Synthetic test source, never sent to a physical printer\n")
    core.write_json(p / "Design/v001/params.json", {"width": 20})
    (p / "Exports/v001/model.stl").write_text("test fixture only")
    project = core.read_json(p / "project.json")
    project["current_revision"] = "v001"
    core.write_json(p / "project.json", project)
    jd = p / "Print/Jtest"
    (jd / "Profiles").mkdir(parents=True)
    core.write_json(jd / "Profiles/machine.json", {"printer_model": "Bambu Lab X2D"})
    with zipfile.ZipFile(jd / "job.gcode.3mf", "w") as z:
        z.writestr("Metadata/plate_1.gcode", "; SYNTHETIC TEST FILE — NEVER EXECUTE\nM620 S0A\nT0\nM621 S0A\nM109 S220\n; CHANGE_LAYER\nG1 X1 E1")
        z.writestr("Metadata/project_settings.config", json.dumps({**templates,"printer_model":"Bambu Lab X2D","nozzle_temperature_initial_layer":[220],"nozzle_temperature":[220],"physical_extruder_map": [0, 1], "filament_map": [1], "filament_type": ["PLA"], "curr_bed_type": "Textured PEI Plate"}))
        z.writestr("Metadata/slice_info.config", '<config><plate><metadata key="index" value="1"/><metadata key="prediction" value="7120"/><metadata key="weight" value="33.02"/><nozzle id="0" extruder_id="1"/><filament id="1" group_id="0"/></plate></config>')
    job = {"id": "Jtest", "project_id": "P001", "revision": "v001", "state": "awaiting_approval", "plate": 1,
           "mapping": {"use_ams": True, "ams_mapping": [0], "extruder_mapping": [0], "routing_verified": True, "fts_installed": False},
           "source_hashes": core.revision_files(p, "v001"), "profile_hashes": {"Profiles/machine.json": core.digest(jd / "Profiles/machine.json")},
           "printer_id": 7, "requested_bed_type": "Textured PEI Plate", "curr_bed_type": "Textured PEI Plate", "trial_only": False,
           "artifact": "job.gcode.3mf", "artifact_sha256": core.digest(jd / "job.gcode.3mf")}
    core.write_json(jd / "job.json", job)
    return p, jd


def ready():
    return {"id": 7, "state": "IDLE", "connected": True, "last_ams_update": time.time(), "hms_errors": [], "fila_switch": {"installed": False},
            "ams_extruder_map": {"0": 0}, "ams": [{"id": 0, "tray": [{"id": 0, "tray_type": "PLA", "state": 11, "exists": True}]}]}


def approve(workspace):
    return core.approve("P001", "Jtest", "确认打印测试任务", True)


class SimulatedBambuddy:
    """In-memory protocol fixture. It has no network/physical transport."""
    def __init__(self, *, timeout=False):
        self.writes = []
        self.item = None
        self.timeout = timeout

    def get(self, path):
        if path.startswith("printers/"):
            return ready()
        if path == "queue/":
            return [self.item] if self.item else []
        if path == "queue/99":
            return self.item
        raise AssertionError(path)

    def post(self, path, **kwargs):
        self.writes.append(path)
        if path == "library/files":
            return {"id": 42}
        if path == "queue/":
            assert kwargs["json"]["manual_start"] is True
            self.item = {**kwargs["json"], "id": 99, "status": "pending"}
            return self.item
        if path == "queue/99/start":
            self.item["manual_start"] = False
            if self.timeout:
                raise httpx.ReadTimeout("Ambiguous response after request")
            return {"success": True}
        raise AssertionError(path)

    def close(self):
        pass


def test_paths_and_symlink_cannot_expose_runtime(workspace):
    p, _ = workspace
    secret = core.ROOT / "Runtime/private/key.json"
    core.write_json(secret, {"secret": "must not leak"})
    (p / "Preview/leak.json").symlink_to(secret)
    for rel in ("../Runtime/private/key.json", "Preview/../../../../Runtime/private/key.json", "Preview/leak.json", "/etc/passwd"):
        with pytest.raises(core.WorkflowError):
            core.public_project_file("P001", rel)
    with pytest.raises(core.WorkflowError):
        core.public_document("Library/../Runtime/private/key.json")


def test_approval_requires_explicit_print_and_plate(workspace):
    with pytest.raises(core.WorkflowError):
        core.approve("P001", "Jtest", "模型看着不错", True)
    with pytest.raises(core.WorkflowError):
        core.approve("P001", "Jtest", "确认打印", False)
    assert approve(workspace)["plate_clear"] is True


@pytest.mark.parametrize("target", ["Design/v001/params.json", "Exports/v001/model.stl", "Print/Jtest/Profiles/machine.json", "Print/Jtest/job.gcode.3mf"])
def test_changed_file_invalidates_approval(workspace, target):
    p, jd = workspace
    approve(workspace)
    with (p / target).open("a") as f:
        f.write("changed")
    with pytest.raises(core.WorkflowError):
        core.job_fingerprint(p, jd, core.read_json(jd / "job.json"))


def test_mapping_and_new_revision_invalidate_approval(workspace):
    p, jd = workspace
    approval = approve(workspace)
    job = core.read_json(jd / "job.json")
    job["mapping"]["ams_mapping"] = [2]
    assert core.job_fingerprint(p, jd, job) != approval["fingerprint"]
    project = core.read_json(p / "project.json")
    project["current_revision"] = "v002"
    core.write_json(p / "project.json", project)
    with pytest.raises(core.WorkflowError):
        core.job_fingerprint(p, jd, job)


@pytest.mark.parametrize("update", [{"state": "RUNNING"}, {"connected": False}, {"last_ams_update": 0}, {"last_ams_update": time.time() - 300}, {"awaiting_plate_clear": True}, {"fila_switch": {"installed": True}}])
def test_not_ready_never_passes(workspace, update):
    _, jd = workspace
    status = {**ready(), **update}
    with pytest.raises(core.WorkflowError):
        bambuddy.validate_ready(status, core.read_json(jd / "job.json")["mapping"])


def test_actual_slice_route_and_material_must_match(workspace):
    _, jd = workspace
    job = core.read_json(jd / "job.json")
    bambuddy.validate_slice_route(jd, job, ready())
    status = ready()
    status["ams"][0]["tray"][0]["tray_type"] = "ABS"
    with pytest.raises(core.WorkflowError):
        bambuddy.validate_slice_route(jd, job, status)


def test_preflight_never_writes(workspace):
    approve(workspace)
    client = SimulatedBambuddy()
    result = bambuddy.submit("P001", "Jtest", client_factory=lambda **kw: client)
    assert result["executed"] is False
    assert client.writes == []


def test_timeout_is_durable_and_never_retried(workspace):
    _, jd = workspace
    approve(workspace)
    client = SimulatedBambuddy(timeout=True)
    for _ in range(2):
        with pytest.raises(core.WorkflowError):
            bambuddy.submit("P001", "Jtest", True, client_factory=lambda **kw: client)
    assert client.writes.count("queue/99/start") == 1
    assert core.read_json(jd / "dispatch.json")["state"] == "unknown"
    assert core.read_json(jd / "job.json")["state"] == "dispatch_unknown"


def test_concurrent_submission_starts_only_once(workspace):
    approve(workspace)
    client = SimulatedBambuddy()
    def run():
        try:
            return bambuddy.submit("P001", "Jtest", True, client_factory=lambda **kw: client)
        except core.WorkflowError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sum(x is not None for x in results) == 1
    assert client.writes.count("queue/99/start") == 1
    assert core.read_json(core.project_path("P001") / "project.json")["status"] != "completed"


def test_archive_or_model_is_not_physical_acceptance(workspace):
    p, jd = workspace
    with pytest.raises(core.WorkflowError):
        core.review("P001", "looks good", "passed")
    project = core.read_json(p / "project.json")
    project["status"] = "archived"
    core.write_json(p / "project.json", project)
    job = core.read_json(jd / "job.json")
    job["state"] = "awaiting_physical_review"
    core.write_json(jd / "job.json", job)
    with pytest.raises(core.WorkflowError):
        core.review("P001", "looks good", "passed")
    assert core.read_json(p / "project.json")["status"] == "archived"


def test_only_physical_review_completes_project(workspace):
    p, jd = workspace
    job = core.read_json(jd / "job.json")
    job["state"] = "awaiting_physical_review"
    core.write_json(jd / "job.json", job)
    core.review("P001", "用户检查了实物尺寸与安装，满足需求。", "passed")
    assert core.read_json(p / "project.json")["status"] == "completed"


def test_context_by_name_skips_session_readme(workspace):
    p, _ = workspace
    metadata = core.read_json(p / "project.json")
    metadata.pop("latest_session", None)  # Legacy projects use the mtime fallback.
    core.write_json(p / "project.json", metadata)
    handoff = p / "Sessions/2026-10-25-handoff.md"
    handoff.write_text("The real handoff")
    (p / "Sessions/README.md").write_text("Template instructions are not current work")
    result = core.context("Route validation fixture")
    assert result["project_id"] == "P001"
    assert any(x.endswith("2026-10-25-handoff.md") for x in result["loaded"])
    assert not any(x.endswith("Sessions/README.md") for x in result["loaded"])


def test_ambiguous_name_requires_id(workspace):
    core.new_project("Route validation fixture")
    with pytest.raises(core.WorkflowError, match="ambiguous"):
        core.project_path("Route validation fixture")


@pytest.mark.parametrize("target", ["Design/v001/params.json", "Exports/v001/model.stl"])
def test_changed_source_before_slice_rejects_stale_stl(workspace, target):
    p, _ = workspace
    manifest = {"verified": True, "checks": {"watertight": True},
                "source_sha256": {f.relative_to(p).as_posix(): core.digest(f) for f in (p / "Design/v001").iterdir()},
                "artifacts": {"Exports/v001/model.stl": core.digest(p / "Exports/v001/model.stl")}}
    core.write_json(p / "Exports/v001/build.json", manifest)
    (p / target).write_text("changed after build but before slice")
    # Invalid profile paths are intentional: source provenance must fail before
    # profiles/slicer are even consulted, so no external tool can execute.
    with pytest.raises(core.WorkflowError, match="changed since"):
        core.slice_project("P001", "does-not-exist", "does-not-exist", ["does-not-exist"])


def test_trial_inspection_extracts_estimates_but_cannot_approve(workspace):
    _, jd = workspace
    job = core.read_json(jd / "job.json")
    job.update(printer_id=None, mapping={}, requested_bed_type=None)
    core.write_json(jd / "job.json", job)
    result = core.inspect_slice("P001", "Jtest", refresh=True)
    assert result["state"] == "awaiting_configuration"
    assert result["trial_only"] is True
    assert len(result["configuration_issues"]) == 4
    assert result["estimates"]["prediction_seconds"] == 7120
    assert result["estimates"]["weight_grams"] == 33.02
    assert result["curr_bed_type"] == "Textured PEI Plate"
    with pytest.raises(core.WorkflowError, match="Trial slice"):
        approve(workspace)


def test_background_reconcile_is_get_only_and_never_resends(workspace):
    p, jd = workspace
    job = core.read_json(jd / "job.json")
    job["state"] = "submitted"
    core.write_json(jd / "job.json", job)
    receipt = {"queue_id": 99, "library_file_id": 42, "state": "submitted"}
    core.write_json(jd / "dispatch.json", receipt)
    class ReadOnly:
        def get(self, path):
            if path == "queue/99":
                return {"id": 99, "printer_id": 7, "library_file_id": 42, "status": "printing"}
            assert path == "printers/7/status"
            return ready()
        def close(self):
            pass
    def factory(**kwargs):
        assert kwargs == {"write": False}
        return ReadOnly()
    for _ in range(2):
        result = bambuddy.reconcile_active_jobs(factory)
        assert result[0]["state"] == "printing"
    assert core.read_json(p / "project.json")["status"] == "printing"
    assert core.read_json(jd / "dispatch.json") == receipt
    assert core.read_json(jd / "observation.json")["queue"]["id"] == 99
    assert core.read_json(jd / "job.json")["reconciliation"]["state"] == "current"


def test_background_failure_marks_stale_without_losing_last_state(workspace):
    _, jd = workspace
    job = core.read_json(jd / "job.json")
    job["state"] = "printing"
    core.write_json(jd / "job.json", job)
    core.write_json(jd / "dispatch.json", {"queue_id": 99, "library_file_id": 42})
    class Offline:
        def get(self, path):
            raise httpx.ConnectError("offline")
        def close(self):
            pass
    bambuddy.reconcile_active_jobs(lambda **kw: Offline())
    updated = core.read_json(jd / "job.json")
    assert updated["state"] == "printing"
    assert updated["reconciliation"]["state"] == "unavailable"


def test_background_does_not_guess_missing_queue_id(workspace):
    _, jd = workspace
    job = core.read_json(jd / "job.json")
    job["state"] = "dispatch_unknown"
    core.write_json(jd / "job.json", job)
    core.write_json(jd / "dispatch.json", {"state": "unknown"})
    def forbidden(**kwargs):
        raise AssertionError("No known remote identity, so no network request is permitted")
    assert bambuddy.reconcile_active_jobs(forbidden) == []


def test_public_device_removes_nested_identifiers_but_preserves_material_state():
    raw = ready()
    raw["serial_number"] = "printer-secret"
    raw["access_code"] = "access-secret"
    raw["ams"][0]["serial_number"] = "ams-secret"
    raw["ams"][0]["tray"][0].update(tag_uid="rfid-secret", tray_uuid="uuid-secret", tray_color="FFFFFFFF", remain=60)
    raw["vt_tray"] = [{"id": 254, "tray_type": "PLA", "tag_uid": "external-secret"}]
    result = bambuddy.sanitize_device(raw)
    assert "secret" not in json.dumps(result)
    assert result["ams"][0]["tray"][0]["remain"] == 60
    assert result["ams"][0]["tray"][0]["tray_type"] == "PLA"
    assert result["ams_extruder_map"] == {"0": 0}
    assert result["vt_tray"][0] == {"id": 254, "tray_type": "PLA"}


def test_null_fts_accepted_only_with_explicit_user_absence_and_bound_route(workspace):
    _, jd = workspace
    mapping = core.read_json(jd / "job.json")["mapping"]
    status = {**ready(), "fila_switch": None}
    bambuddy.validate_ready(status, mapping)
    with pytest.raises(core.WorkflowError, match="bind"):
        bambuddy.validate_ready(status, {k: v for k, v in mapping.items() if k != "fts_installed"})
    core.write_json(core.ROOT / "Library/Devices/X2D/device.json", {"user_confirmed": {}})
    with pytest.raises(core.WorkflowError, match="explicit dated user confirmation"):
        bambuddy.validate_ready(status, mapping)


def test_changed_fts_declaration_invalidates_existing_approval(workspace):
    p, jd = workspace
    approve(workspace)
    job = core.read_json(jd / "job.json")
    core.write_json(core.ROOT / "Library/Devices/X2D/device.json", {"user_confirmed": {"fts_installed": True, "fts_confirmation_quote": "Synthetic operator installed FTS", "fts_confirmation_date": "2026-10-26"}})
    with pytest.raises(core.WorkflowError, match="hardware declaration changed"):
        core.job_fingerprint(p, jd, job)


def test_explicit_handoff_pointer_survives_changed_restore_mtime(workspace):
    import os
    p, _ = workspace
    first = core.handoff("P001", "Earlier handoff")
    latest = core.handoff("P001", "Authoritative latest handoff")
    os.utime(first["path"], (time.time() + 3600, time.time() + 3600))
    result = core.context("P001")
    selected = [item for item in result["documents"] if "/Sessions/" in item["path"]]
    assert len(selected) == 1
    assert selected[0]["path"].endswith(latest["latest_session"])
    assert "Authoritative latest handoff" in selected[0]["text"]
    assert core.read_json(p / "project.json")["latest_session"] == latest["latest_session"]
    assert "Earlier handoff" in __import__('pathlib').Path(first["path"]).read_text()


@pytest.mark.parametrize("pointer", ["../Runtime/private/key.md", "Sources/notes.md", "Sessions/../brief.md", "/tmp/outside.md", "Sessions/README.md"])
def test_explicit_handoff_pointer_cannot_escape_sessions(workspace, pointer):
    p, _ = workspace
    metadata = core.read_json(p / "project.json")
    metadata["latest_session"] = pointer
    core.write_json(p / "project.json", metadata)
    with pytest.raises(core.WorkflowError):
        core.context("P001")


def test_new_project_initializes_handoff_pointer(workspace):
    p, _ = workspace
    assert core.read_json(p / "project.json")["latest_session"] == "Sessions/handoff.md"
    assert any(x.endswith("Sessions/handoff.md") for x in core.context("P001")["loaded"])
