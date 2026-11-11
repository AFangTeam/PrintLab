#!/usr/bin/env python3
"""Private local snapshots and non-destructive recovery checks (standard library).

Usage:
  python3 Harness/backup.py backup --verify
  python3 Harness/backup.py verify Runtime/backups/<snapshot>

Only the explicit allowlist below is copied. SQLite is backed up through its
online backup API, never by copying a live database and its WAL independently.
A verification restores into a new Runtime/evidence/recovery-* directory; it
never replaces live files. Stop the services and explicitly authorize a real
restore before copying a verified recovery payload back into the workspace.
This local snapshot is not an off-machine backup or a cross-file transaction.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import time
import uuid


DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", ".gitignore")
TREES = ("Context", "Library", "Project", "Templates", "Harness",
         "Runtime/config", "Runtime/private", "Runtime/bambuddy-data")
RUNTIME_FILES = ("Runtime/config.json",)
EXCLUDED_NAMES = {"node_modules", "dist", "__pycache__", ".pytest_cache",
                  ".mypy_cache", ".ruff_cache", ".git", ".venv", "venv",
                  "env", "vendor", "cache", "caches", "logs", ".DS_Store"}
DB_PATH = "Runtime/bambuddy-data/bambuddy.db"
MAX_MANIFEST_BYTES = 64 * 1024 * 1024


class BackupError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def private_dir(path: Path) -> None:
    """Create our own directory, rejecting symlinked ancestors."""
    missing = []
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise BackupError(f"Symlink directory is not allowed: {candidate}")
        if not candidate.exists():
            missing.append(candidate)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise BackupError(f"Not a directory: {path}")
    path.chmod(0o700)
    for candidate in missing:
        candidate.chmod(0o700)


def checked_relative(value: str) -> Path:
    item = PurePosixPath(value)
    if (not value or item.is_absolute() or ".." in item.parts
            or str(item) != value or "\\" in value):
        raise BackupError("Invalid relative path in snapshot manifest")
    return Path(*item.parts)


def safe_regular(path: Path, boundary: Path) -> None:
    try:
        path.relative_to(boundary)
    except ValueError as exc:
        raise BackupError("File escaped its source boundary") from exc
    for item in (path, *path.parents):
        if item.is_symlink():
            raise BackupError(f"Symlink is not backed up: {path}")
        if item == boundary:
            break
    if not stat.S_ISREG(path.stat().st_mode):
        raise BackupError(f"Only regular files can be backed up: {path}")


def excluded(rel: Path) -> bool:
    return (any(part.lower() in EXCLUDED_NAMES for part in rel.parts)
            or rel.name.endswith((".pyc", ".pyo", ".log", ".db-wal", ".db-shm")))


def inventory(root: Path) -> tuple[list[Path], list[str], list[str]]:
    files, skipped, directories = [], [], set()
    for name in (*ROOT_FILES, *RUNTIME_FILES, *TREES):
        start = root / name
        if start.is_symlink():
            raise BackupError(f"Symlink is not backed up: {start}")
        if not start.exists():
            continue
        if start.is_file():
            files.append(start)
            continue
        for directory, dirs, names in os.walk(start, followlinks=False):
            base = Path(directory)
            directories.add(base.relative_to(root).as_posix())
            retained = []
            for dirname in sorted(dirs):
                child = base / dirname
                rel = child.relative_to(root)
                if excluded(rel):
                    skipped.append(rel.as_posix())
                elif child.is_symlink():
                    raise BackupError(f"Symlink is not backed up: {child}")
                else:
                    retained.append(dirname)
            dirs[:] = retained
            for filename in sorted(names):
                child = base / filename
                rel = child.relative_to(root)
                if excluded(rel):
                    skipped.append(rel.as_posix())
                else:
                    safe_regular(child, root)
                    files.append(child)
    return sorted(set(files)), skipped, sorted(directories)


def copy_stable(source: Path, target: Path, boundary: Path) -> None:
    safe_regular(source, boundary)
    private_dir(target.parent)
    before = source.stat()
    with source.open("rb") as src, target.open("xb") as dst:
        os.chmod(target, 0o600)
        shutil.copyfileobj(src, dst, 1024 * 1024)
    after = source.stat()
    if ((before.st_size, before.st_mtime_ns, before.st_ino)
            != (after.st_size, after.st_mtime_ns, after.st_ino)):
        raise BackupError(f"Source changed during copy; retry when quiet: {source}")
    # Legacy projects select their latest handoff by modification time. Preserve
    # nanoseconds on both snapshot and restore; copy order must not change it.
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))


def sqlite_backup(source: Path, target: Path, timeout: float = 60) -> None:
    private_dir(target.parent)
    deadline = time.monotonic() + timeout

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise BackupError("SQLite backup timed out; no complete snapshot created")

    src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)
    dst = sqlite3.connect(target)
    try:
        target.chmod(0o600)
        src.backup(dst, pages=256, progress=progress, sleep=0.05)
        # The online backup copies the source's WAL journal setting. Normalize
        # only this private destination so later read-only checks do not create
        # unlisted -wal/-shm companions beside the archived database.
        checkpoint = dst.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint and checkpoint[0] != 0:
            raise BackupError("Destination SQLite checkpoint could not complete")
        mode = dst.execute("PRAGMA journal_mode=DELETE").fetchone()
        if mode != ("delete",):
            raise BackupError("Destination SQLite journal mode could not be normalized")
        result = dst.execute("PRAGMA quick_check").fetchall()
        if result != [("ok",)]:
            raise BackupError("SQLite backup integrity check failed")
    finally:
        dst.close()
        src.close()
    if any(Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise BackupError("Destination SQLite has unexpected WAL companion files")


def write_json(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        path.chmod(0o600)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def create_backup(root: Path = DEFAULT_ROOT, destination: Path | None = None) -> Path:
    root = root.absolute()
    if root.is_symlink() or not root.is_dir():
        raise BackupError("Workspace must be an existing real directory")
    destination = (destination or root / "Runtime/backups").absolute()
    # Reject a destination nested in a copied tree (would recursively copy itself).
    for name in TREES:
        if destination == root / name or root / name in destination.parents:
            raise BackupError("Backup destination must be outside copied trees")
    private_dir(destination)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    partial = destination / (".incomplete-" + stamp)
    final = destination / stamp
    private_dir(partial)
    payload = partial / "payload"
    private_dir(payload)
    started = now()
    try:
        files, skipped, directories = inventory(root)
        for directory in directories:
            private_dir(payload / directory)
        entries = []
        for source in files:
            rel = source.relative_to(root).as_posix()
            target = payload / rel
            safe_regular(source, root)
            if rel == DB_PATH:
                sqlite_backup(source, target)
                method = "sqlite-online-backup"
            else:
                copy_stable(source, target, root)
                method = "file-copy"
            entries.append({"path": rel, "bytes": target.stat().st_size,
                            "sha256": digest(target), "method": method,
                            "sensitive": rel.startswith("Runtime/"),
                            "source_mode": stat.S_IMODE(source.stat().st_mode)})
        manifest = {"schema_version": 1, "status": "complete", "started_at": started,
                    "completed_at": now(), "source_root": str(root),
                    "files": entries, "directories": directories, "excluded_paths": skipped,
                    "sqlite_included": any(e["path"] == DB_PATH for e in entries),
                    "consistency": "Per-file stable copies; SQLite transaction snapshot. Not a global workspace transaction.",
                    "sensitive_values": "Present only inside private payload; never printed in manifest or report.",
                    "exclusions": sorted(EXCLUDED_NAMES)}
        write_json(partial / "manifest.json", manifest)
        readme = partial / "RESTORE.txt"
        readme.write_text(
            "PrintLab 私有本地备份\n\n"
            "本目录含设备凭据和数据库，请保持目录权限700、文件600，不上传公共仓库。\n"
            "这是本机副本，不是异地灾备。node_modules、虚拟环境、vendor、缓存和日志未备份；按锁定版本重建。\n"
            "验证：python3 Harness/backup.py verify <本备份目录>\n"
            "验证只将payload恢复到新的Runtime/evidence/recovery-*目录，不覆盖在线资料。\n"
            "实际恢复需先停止相关服务，保留当前状态副本，再由用户明确选择恢复目录和版本。\n"
            "先校验manifest的全部SHA256与SQLite quick_check，再复制相应项目及Bambuddy数据、密钥和配置。\n"
            "恢复Bambuddy数据库时服务必须停止，旧db-wal/db-shm不能混入恢复库；保留旧数据以便回退。\n"
            "备份文件全部收紧为600；验证恢复保留源文件修改时间，并仅恢复原有的拥有者执行位，普通文件600、可执行文件700。\n"
            "恢复副本不继承组/其他用户权限和SUID/SGID；环境重建后再次doctor并读取实际设备状态。\n"
            "数据库快照完整；文件逐个稳定复制，不保证跨文件同一瞬间。重要批准包备份前应停止修改。\n"
            "SHA256用于发现损坏，不是签名，不能证明不可信来源的备份真实性。\n", encoding="utf-8")
        readme.chmod(0o600)
        partial.rename(final)
        return final
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise


def load_verified(snapshot: Path) -> dict:
    manifest_path = snapshot / "manifest.json"
    safe_regular(manifest_path, snapshot)
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise BackupError("Manifest is too large")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("status") != "complete":
        raise BackupError("Unsupported or incomplete snapshot")
    payload = snapshot / "payload"
    if payload.is_symlink():
        raise BackupError("Symlink payload is not allowed")
    for directory in manifest.get("directories", []):
        item = payload / checked_relative(directory)
        for parent in (item, *item.parents):
            if parent.is_symlink():
                raise BackupError("Symlink found in snapshot directory")
            if parent == payload:
                break
        if not item.is_dir():
            raise BackupError("Snapshot directory is missing")
    seen = set()
    for entry in manifest["files"]:
        rel = checked_relative(entry["path"])
        if str(rel) in seen:
            raise BackupError("Duplicate manifest path")
        seen.add(str(rel))
        source = payload / rel
        safe_regular(source, payload)
        if source.stat().st_size != entry["bytes"] or digest(source) != entry["sha256"]:
            raise BackupError(f"Snapshot checksum mismatch: {rel}")
    actual = set()
    for directory, dirs, files in os.walk(payload, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise BackupError("Symlink found in snapshot payload")
        for name in files:
            path = Path(directory) / name
            safe_regular(path, payload)
            actual.add(str(path.relative_to(payload)))
    if actual != seen:
        raise BackupError("Snapshot contains missing or unlisted files")
    return manifest


def verify_restore(snapshot: Path, root: Path = DEFAULT_ROOT) -> dict:
    """Restore only to a newly allocated evidence directory, never live paths."""
    snapshot, root = snapshot.absolute(), root.absolute()
    manifest = load_verified(snapshot)
    evidence = root / "Runtime/evidence"
    private_dir(evidence)
    recovery = evidence / ("recovery-" + uuid.uuid4().hex)
    private_dir(recovery)
    payload = recovery / "payload"
    private_dir(payload)
    try:
        for directory in manifest.get("directories", []):
            private_dir(payload / checked_relative(directory))
        for entry in manifest["files"]:
            rel = checked_relative(entry["path"])
            target = payload / rel
            copy_stable(snapshot / "payload" / rel, target, snapshot / "payload")
            # Keep the private recovery tree private while allowing original
            # owner-executable entrypoints to run; never restore SUID/SGID bits.
            target.chmod(0o600 | (int(entry.get("source_mode", 0)) & 0o100))
            if target.stat().st_size != entry["bytes"] or digest(target) != entry["sha256"]:
                raise BackupError(f"Restored checksum mismatch: {rel}")
        db_check = "not_present"
        if (payload / DB_PATH).exists():
            conn = sqlite3.connect((payload / DB_PATH).as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise BackupError("Restored SQLite integrity check failed")
                db_check = "ok"
            finally:
                conn.close()
        report = {"status": "verified", "verified_at": now(), "snapshot": str(snapshot),
                  "recovery_directory": str(recovery), "files": len(manifest["files"]),
                  "bytes": sum(e["bytes"] for e in manifest["files"]),
                  "sha256": "all_match", "sqlite_quick_check": db_check,
                  "live_files_replaced": False,
                  "file_mtime": "preserved from snapshot",
                  "executable_mode": "owner executable bit preserved; group/other and special bits cleared",
                  "sensitive_payload": True,
                  "limitations": "Local copy only; service restart/device connection and relational links not exercised."}
        write_json(recovery / "verification.json", report)
        return report
    except BaseException:
        shutil.rmtree(recovery, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="Create a private local snapshot")
    backup.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    backup.add_argument("--destination", type=Path)
    backup.add_argument("--verify", action="store_true")
    verify = sub.add_parser("verify", help="Check snapshot and restore to separate evidence directory")
    verify.add_argument("snapshot", type=Path)
    verify.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            snapshot = create_backup(args.root, args.destination)
            result = (verify_restore(snapshot, args.root) if args.verify else
                      {"status": "created", "snapshot": str(snapshot)})
        else:
            result = verify_restore(args.snapshot, args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BackupError, OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        # Never print file contents, credential values, or database records.
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
