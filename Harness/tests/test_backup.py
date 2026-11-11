"""Integrity, live-WAL backup, private permissions and non-destructive recovery."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("printlab_backup", Path(__file__).parents[1] / "backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def put(root, relative, value="test"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return path


def test_live_wal_roundtrip_is_private_and_does_not_replace_live_files(tmp_path):
    root = tmp_path / "PrintLab"
    put(root, "Project/P001/brief.md", "original brief")
    put(root, "Runtime/private/credentials.json", '{"token":"test-secret-value"}')
    put(root, "Runtime/bambuddy-data/.jwt_secret", "another-secret-value")
    put(root, "Runtime/config.json", '{"enabled":true}')
    put(root, "Harness/studio/node_modules/huge.js", "excluded")
    put(root, "Harness/studio/dist/app.js", "excluded")
    put(root, "Runtime/vendor/huge.py", "excluded")
    put(root, "Runtime/bambuddy-data/logs/service.log", "excluded")
    put(root, "Library/manual.pdf", "source")
    (root / "Templates/Project/Design").mkdir(parents=True)
    db = root / backup.DB_PATH
    live = sqlite3.connect(db)
    try:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("PRAGMA wal_autocheckpoint=0")
        live.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, name TEXT)")
        live.execute("INSERT INTO jobs VALUES (1, 'synthetic job')")
        live.commit()
        assert Path(str(db) + "-wal").exists()
        snapshot = backup.create_backup(root)
        archived_db = snapshot / "payload" / backup.DB_PATH
        assert not Path(str(archived_db) + "-wal").exists()
        assert not Path(str(archived_db) + "-shm").exists()
        archive_conn = sqlite3.connect(archived_db.as_uri() + "?mode=ro", uri=True)
        try:
            assert archive_conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        finally:
            archive_conn.close()
        assert not Path(str(archived_db) + "-wal").exists()
        assert not Path(str(archived_db) + "-shm").exists()
        assert live.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        manifest_text = (snapshot / "manifest.json").read_text()
        manifest = json.loads(manifest_text)
        assert "test-secret-value" not in manifest_text
        assert "another-secret-value" not in manifest_text
        names = {f["path"] for f in manifest["files"]}
        assert backup.DB_PATH in names
        assert not any("node_modules" in p or "/dist/" in p or p.endswith("-wal") for p in names)
        assert "Runtime/bambuddy-data/.jwt_secret" in names
        assert "Runtime/config.json" in names
        assert manifest["sqlite_included"]
        assert stat.S_IMODE(snapshot.stat().st_mode) == 0o700
        for path in snapshot.rglob("*"):
            assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
        # A later live change must survive recovery verification untouched.
        put(root, "Project/P001/brief.md", "live revised brief")
        live.execute("INSERT INTO jobs VALUES (2, 'later live job')")
        live.commit()
        result = backup.verify_restore(snapshot, root)
        restored = Path(result["recovery_directory"]) / "payload"
        assert (restored / "Templates/Project/Design").is_dir()
        assert (restored / "Project/P001/brief.md").read_text() == "original brief"
        assert (root / "Project/P001/brief.md").read_text() == "live revised brief"
        conn = sqlite3.connect(restored / backup.DB_PATH)
        try:
            assert conn.execute("SELECT count(*) FROM jobs").fetchone() == (1,)
        finally:
            conn.close()
        assert live.execute("SELECT count(*) FROM jobs").fetchone() == (2,)
        assert result["sqlite_quick_check"] == "ok"
        assert not result["live_files_replaced"]
        for path in Path(result["recovery_directory"]).rglob("*"):
            assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
    finally:
        live.close()


def test_tamper_rejected_before_recovery(tmp_path):
    root = tmp_path / "lab"
    put(root, "Context/profile.md", "confirmed")
    snapshot = backup.create_backup(root)
    (snapshot / "payload/Context/profile.md").write_text("tampered")
    with pytest.raises(backup.BackupError, match="checksum"):
        backup.verify_restore(snapshot, root)
    assert not (root / "Runtime/evidence").exists()


def test_symlink_source_rejected_without_following_and_partial_removed(tmp_path):
    root = tmp_path / "lab"
    outside = put(tmp_path, "outside.secret", "secret")
    put(root, "Context/profile.md")
    (root / "Context/link").symlink_to(outside)
    with pytest.raises(backup.BackupError, match="Symlink"):
        backup.create_backup(root)
    assert list((root / "Runtime/backups").iterdir()) == []


@pytest.mark.parametrize("bad_path", ["../outside", "/absolute", "Context/../../outside", "./Context/file"])
def test_manifest_path_traversal_rejected(tmp_path, bad_path):
    root = tmp_path / "lab"
    put(root, "Context/profile.md")
    snapshot = backup.create_backup(root)
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"][0]["path"] = bad_path
    path.write_text(json.dumps(manifest))
    with pytest.raises(backup.BackupError, match="Invalid relative path"):
        backup.verify_restore(snapshot, root)


def test_missing_sqlite_is_reported_and_nested_backup_rejected(tmp_path):
    root = tmp_path / "lab"
    put(root, "Context/profile.md")
    with pytest.raises(backup.BackupError, match="outside copied trees"):
        backup.create_backup(root, root / "Library/backups")
    snapshot = backup.create_backup(root)
    report = backup.verify_restore(snapshot, root)
    assert report["sqlite_quick_check"] == "not_present"


def test_extra_payload_and_duplicate_paths_rejected(tmp_path):
    root = tmp_path / "lab"
    put(root, "Context/profile.md")
    snapshot = backup.create_backup(root)
    extra = put(snapshot, "payload/unlisted", "extra")
    with pytest.raises(backup.BackupError, match="unlisted"):
        backup.verify_restore(snapshot, root)
    extra.unlink()
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"].append(manifest["files"][0])
    path.write_text(json.dumps(manifest))
    with pytest.raises(backup.BackupError, match="Duplicate"):
        backup.verify_restore(snapshot, root)


def test_recovery_preserves_handoff_selection_content_and_executable(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    metadata = {"id": "P001", "name": "sample", "current_revision": "v001"}
    put(root, "Project/P001-sample/project.json", json.dumps(metadata))
    old = put(root, "Project/P001-sample/Sessions/2026-setup.md", "old setup")
    latest = put(root, "Project/P001-sample/Sessions/2026-implementation.md", "latest verified handoff")
    # Opposite of alphabetical copy order, with nanoseconds that must survive.
    os.utime(old, ns=(1700000000000000001, 1700000000000000001))
    os.utime(latest, ns=(1700000001000000002, 1700000001000000002))
    command = put(root, "Harness/bin/example", "#!/bin/sh\nprintf 'recovered-entrypoint'\n")
    command.chmod(0o755)
    from printlab import core, shop
    monkeypatch.setattr(core, "ROOT", root)
    shop.confirm("P001", "Synthetic decision to make", "backup fixture", 0)
    shop.sync("P001", [], 1, "No parts required in this fixture")
    original_context = core.context("P001")
    selected = lambda context: [(d["path"], d["sha256"], d["text"]) for d in context["documents"] if "/Sessions/" in d["path"]]
    assert selected(original_context)[0][0].endswith("2026-implementation.md")
    snapshot = backup.create_backup(root)
    assert stat.S_IMODE((snapshot / "payload/Harness/bin/example").stat().st_mode) == 0o600
    result = backup.verify_restore(snapshot, root)
    restored = Path(result["recovery_directory"]) / "payload"
    for source in (old, latest):
        rel = source.relative_to(root)
        assert (snapshot / "payload" / rel).stat().st_mtime_ns == source.stat().st_mtime_ns
        assert (restored / rel).stat().st_mtime_ns == source.stat().st_mtime_ns
    monkeypatch.setattr(core, "ROOT", restored)
    assert selected(core.context("P001")) == selected(original_context)
    assert core.context("P001")["shopping"] == original_context["shopping"]
    restored_command = restored / "Harness/bin/example"
    assert stat.S_IMODE(restored_command.stat().st_mode) == 0o700
    assert subprocess.check_output([str(restored_command)], text=True) == "recovered-entrypoint"
