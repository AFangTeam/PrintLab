"""Offline candidate evidence checks; synthetic files are not geometry/appearance acceptance."""
import json
import subprocess
import pytest
from printlab import core, image3d


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ROOT", tmp_path)
    core.new_project("Synthetic Image3D")
    pp = core.project_path("P001")
    source = pp / "Sources/reference.png"
    source.write_bytes(b"synthetic reference")
    folder = pp / "Design/Candidates/synthetic"
    folder.mkdir(parents=True)
    artifacts = {}
    for name in ("raw-normalized.glb", "shape-mm.ply", "shape-mm.stl", "candidate-geometry-only.3mf", "conditioning.png"):
        (folder / name).write_bytes(b"synthetic artifact " + name.encode())
        artifacts[name] = core.digest(folder / name)
    views = {}
    for name in ("front", "right", "back", "quarter", "top"):
        f = folder / f"gray-{name}.png"
        f.write_bytes(b"synthetic render " + name.encode())
        views[name] = {"sha256": core.digest(f)}
    core.write_json(folder / "manifest.json", {
        "status": "generated_unreviewed", "reference": {"path": str(source), "sha256": core.digest(source)},
        "conditioning": {"path": "conditioning.png", "sha256": artifacts.pop("conditioning.png")},
        "artifacts": artifacts,
    })
    core.write_json(folder / "render-record.json", {"mesh_sha256": artifacts["shape-mm.ply"], "views": views})
    return pp, folder


def test_integrity_is_not_appearance_or_print_acceptance(candidate):
    result = image3d.inspect("P001", "synthetic")
    assert result["integrity"] == "passed"
    assert result["functional_scope"] == "untested"
    assert result["print_ready"] is False
    assert result["print_authorized"] is False


@pytest.mark.parametrize("name", ["shape-mm.ply", "gray-front.png", "conditioning.png", "candidate-geometry-only.3mf"])
def test_replaced_mesh_preview_or_conditioning_invalidates_evidence(candidate, name):
    _, folder = candidate
    (folder / name).write_bytes(b"changed after generation")
    assert image3d.inspect("P001", "synthetic")["integrity"] == "failed"


def test_different_source_or_rendered_mesh_invalidates_evidence(candidate):
    pp, folder = candidate
    (pp / "Sources/reference.png").write_bytes(b"another concept")
    r = json.loads((folder / "render-record.json").read_text())
    r["mesh_sha256"] = "other mesh"
    core.write_json(folder / "render-record.json", r)
    result = image3d.inspect("P001", "synthetic")
    assert result["integrity"] == "failed"
    assert any("Rendered mesh" in issue for issue in result["issues"])


def test_failed_generation_is_never_completed(candidate):
    _, folder = candidate
    m = core.read_json(folder / "manifest.json")
    m["status"] = "failed"
    core.write_json(folder / "manifest.json", m)
    assert image3d.inspect("P001", "synthetic")["integrity"] == "failed"


def test_candidate_path_cannot_escape_project(candidate):
    with pytest.raises(core.WorkflowError):
        image3d.inspect("P001", "../../other")


def fake_runtime(folder, monkeypatch):
    runtime = folder / "fake-runtime"
    runtime.write_bytes(b"offline test only")
    monkeypatch.setattr(image3d, "toolchain", lambda: {"python": runtime, "worker": runtime})


def test_existing_candidate_cannot_overwrite_prior_log(candidate, monkeypatch):
    _, folder = candidate
    fake_runtime(folder, monkeypatch)
    log = folder / "inference.log"
    log.write_text("original evidence")
    with pytest.raises(core.WorkflowError, match="already exists"):
        image3d.generate("P001", "Sources/reference.png", "synthetic", None, 60, 30, 256, 42, 8)
    assert log.read_text() == "original evidence"


def test_generation_timeout_preserves_log_and_explicit_failure(candidate, monkeypatch):
    pp, folder = candidate
    fake_runtime(folder, monkeypatch)
    out = pp / "Design/Candidates/timeout"
    def timed_out(command, **kwargs):
        out.mkdir()
        core.write_json(out / "manifest.json", {"status": "generating"})
        raise subprocess.TimeoutExpired(command, 900, output=b"partial progress", stderr=b"diagnostic")
    monkeypatch.setattr(image3d.subprocess, "run", timed_out)
    with pytest.raises(core.WorkflowError, match="timed out"):
        image3d.generate("P001", "Sources/reference.png", "timeout", None, 60, 30, 256, 42, 8)
    assert core.read_json(out / "manifest.json")["status"] == "generation_timed_out"
    assert "partial progress" in (out / "inference.log").read_text()
    assert image3d.inspect("P001", "timeout")["integrity"] == "failed"


def test_failed_inspection_has_failure_exit_status(candidate, monkeypatch, capsys):
    from printlab import cli
    _, folder = candidate
    (folder / "gray-front.png").write_bytes(b"stale")
    assert cli.main(["image3d", "inspect", "P001", "--candidate", "synthetic"]) == 2
    assert json.loads(capsys.readouterr().out)["integrity"] == "failed"


def test_eight_view_renderer_cannot_pass_with_missing_new_angles(candidate):
    _, folder = candidate
    record = core.read_json(folder / "render-record.json")
    record["view_schema"] = "eight-view-v2"
    core.write_json(folder / "render-record.json", record)
    assert image3d.inspect("P001", "synthetic")["integrity"] == "failed"
    for view in ("left", "bottom", "back_quarter"):
        f = folder / f"gray-{view}.png"
        f.write_bytes(b"synthetic new view " + view.encode())
        record["views"][view] = {"sha256": core.digest(f)}
    core.write_json(folder / "render-record.json", record)
    assert image3d.inspect("P001", "synthetic")["integrity"] == "passed"
