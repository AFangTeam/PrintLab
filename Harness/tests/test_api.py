import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from printlab import core, bambuddy
from printlab.api import app


def test_read_only_api_file_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ROOT", tmp_path)
    core.new_project("API fixture")
    core.write_json(tmp_path / "Runtime/private/bambuddy.json", {"write_api_key": "hidden-sentinel"})
    (tmp_path / "Library").mkdir()
    (tmp_path / "Library/untrusted.html").write_text("<script>alert('untrusted')</script>")
    (tmp_path / "Library/key.txt").symlink_to(tmp_path / "Runtime/private/bambuddy.json")
    client = TestClient(app)
    assert client.get("/api/health").json()["read_only"] is False
    assert client.get("/api/projects").json()["projects"][0]["id"] == "P001"
    assert client.get("/api/projects/P001").status_code == 200
    for path in ["/api/documents/Runtime/private/bambuddy.json", "/api/documents/Library/key.txt", "/api/files/P001/Preview/%2e%2e/%2e%2e/%2e%2e/Runtime/private/bambuddy.json"]:
        r = client.get(path)
        assert r.status_code == 404
        assert "hidden-sentinel" not in r.text
    r = client.get("/api/documents/Library/untrusted.html")
    assert r.headers["content-type"].startswith("text/plain")
    assert "sandbox" in r.headers["content-security-policy"]
    assert client.post("/api/projects").status_code == 405


def test_unconfigured_is_not_live(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "ROOT", tmp_path)
    result = TestClient(app).get("/api/device").json()
    assert result["state"] == "unconfigured"
    assert result["printer"] is None
    assert result["updated_at"] is None
