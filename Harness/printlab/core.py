from __future__ import annotations

import contextlib
import datetime as dt
import portalocker
from . import platforms
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
import xml.etree.ElementTree as ET
import math
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(os.environ.get("PRINTLAB_ROOT", Path(__file__).resolve().parents[2])).expanduser().resolve()
PROJECT_DIRS = ("Sources", "Design", "Exports", "Preview", "Print", "Review", "Sessions")
PUBLIC_DIRS = {"Sources", "Design", "Exports", "Preview", "Print", "Review", "Sessions"}


class WorkflowError(ValueError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@contextlib.contextmanager
def lock(name="workflow"):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        name = hashlib.sha256(name.encode()).hexdigest()
    d = ROOT / "Runtime" / "locks"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{name}.lock").open("a") as f:
        portalocker.lock(f, portalocker.LOCK_EX)
        try:
            yield
        finally:
            portalocker.unlock(f)


def config():
    return read_json(ROOT / "Runtime/config.json", {})


def fts_declaration():
    confirmed = read_json(ROOT / "Library/Devices/X2D/device.json", {}).get("user_confirmed", {})
    value = confirmed.get("fts_installed")
    # A missing/null machine field alone never establishes that hardware is absent.
    if type(value) is not bool or not confirmed.get("fts_confirmation_quote") or not confirmed.get("fts_confirmation_date"):
        return None
    return value


def safe_path(base: Path, rel: str, require_file=True):
    if not rel or "\x00" in rel or Path(rel).is_absolute():
        raise WorkflowError("Invalid relative path")
    lexical = base / rel
    if base.is_symlink() or any(item.is_symlink() for item in [lexical, *lexical.parents] if item == base or item.is_relative_to(base)):
        raise WorkflowError("Symbolic links are not served as workspace artifacts")
    p = lexical.resolve()
    if not p.is_relative_to(base.resolve()):
        raise WorkflowError("Path escapes allowed directory")
    if require_file and not p.is_file():
        raise WorkflowError("File not found")
    return p


def project_path(pid: str):
    if not re.fullmatch(r"P\d{3,}", pid):
        matches = []
        for candidate in (ROOT / "Project").glob("P*-*/project.json"):
            if candidate.is_symlink() or candidate.parent.is_symlink():
                continue
            data = read_json(candidate, {})
            if pid.strip() in {data.get("name"), data.get("slug"), candidate.parent.name}:
                matches.append(candidate)
        paths = matches
    else:
        paths = list((ROOT / "Project").glob(f"{pid}-*/project.json"))
    if len(paths) != 1:
        raise WorkflowError("Project not found or ambiguous; use a unique project name, slug, or P001-style ID")
    if paths[0].is_symlink() or paths[0].parent.is_symlink():
        raise WorkflowError("Project metadata must not be a symbolic link")
    p = paths[0].parent.resolve()
    if not p.is_relative_to((ROOT / "Project").resolve()):
        raise WorkflowError("Project path escapes workspace")
    return p


def public_project_file(pid, rel):
    p = project_path(pid)
    first = Path(rel).parts[0] if Path(rel).parts else ""
    if first not in PUBLIC_DIRS and rel not in {"brief.md", "decisions.md", "project.json"}:
        raise WorkflowError("File is not a project artifact")
    file = safe_path(p, rel)
    # Resolve again against the category so a symlink cannot expose another project or private files.
    if first in PUBLIC_DIRS and not file.is_relative_to((p / first).resolve()):
        raise WorkflowError("Artifact crosses category boundary")
    return file


def public_document(rel):
    first = Path(rel).parts[0] if Path(rel).parts else ""
    if first not in {"Library", "Context"} and rel not in {"README.md", "AGENTS.md"}:
        raise WorkflowError("Document is not public workspace context")
    p = safe_path(ROOT, rel)
    if first in {"Library", "Context"} and not p.is_relative_to((ROOT / first).resolve()):
        raise WorkflowError("Document crosses category boundary")
    return p


def file_url(pid, relative):
    return f"/api/files/{pid}/{quote(relative, safe='/')}"


def artifact_url(p, revision, directory, filename):
    if not revision:
        return None
    rel = f"{directory}/{revision}/{filename}"
    return file_url(read_json(p / "project.json")["id"], rel) if (p / rel).is_file() else None


def summary(p):
    from . import shop
    data = read_json(p / "project.json")
    rev = data.get("current_revision")
    build = read_json(p / "Exports" / str(rev) / "build.json", {}) if rev else {}
    data.update(cover_url=artifact_url(p, rev, "Preview", "cover.png"),
                model_url=artifact_url(p, rev, "Exports", "model.glb"),
                dimensions_mm=build.get("dimensions_mm"),
                verification=build.get("checks", {}), shop=shop.project_summary(data["id"]))
    return data


def list_projects():
    rows = []
    for path in sorted((ROOT / "Project").glob("P*-*/project.json")):
        try:
            p = project_path(read_json(path)["id"])
            rows.append(summary(p))
        except (ValueError, KeyError, OSError):
            continue
    return rows


def texts(directory):
    return [{"name": p.name, "text": p.read_text(encoding="utf-8")[:50000]}
            for p in sorted(directory.glob("*.md"), reverse=True) if not p.is_symlink()][:30]


def current_attempt(p, project=None, jobs=None):
    """A durable explicit pointer wins; old projects fall back to creation time."""
    p = p if isinstance(p, Path) else project_path(p)
    project = project if project is not None else read_json(p / "project.json")
    jobs = jobs if jobs is not None else [read_json(f,{}) for f in (p / "Print").glob("*/job.json")]
    selected = project.get("current_job_id")
    if selected:
        return next((j for j in jobs if j.get("id") == selected), None)
    return max(jobs,key=lambda j:(j.get("created_at", ""),j.get("id", "")),default=None)


def is_current_attempt(p, job):
    p = p if isinstance(p, Path) else project_path(p)
    project = read_json(p / "project.json")
    current = current_attempt(p, project)
    return (project.get("status") not in {"archived", "completed"} and current is not None
            and current.get("id") == job.get("id") and project.get("current_revision") == job.get("revision"))


def detail(pid):
    p = project_path(pid)
    data = summary(p)
    data["brief"] = (p / "brief.md").read_text(encoding="utf-8") if (p / "brief.md").exists() else ""
    data["decisions"] = (p / "decisions.md").read_text(encoding="utf-8") if (p / "decisions.md").exists() else ""
    data["files"] = []
    for d in PROJECT_DIRS:
        for f in sorted((p / d).rglob("*")):
            if f.is_file() and not f.is_symlink() and not any(x.startswith(".") for x in f.relative_to(p).parts):
                rel = f.relative_to(p).as_posix()
                try:
                    public_project_file(pid, rel)
                except WorkflowError:
                    continue
                data["files"].append({"name": f.name, "path": rel, "category": d,
                                      "size": f.stat().st_size, "url": file_url(pid, rel)})
    rev = data.get("current_revision")
    data["build"] = read_json(p / "Exports" / str(rev) / "build.json") if rev else None
    data["prints"] = [read_json(f) for f in sorted((p / "Print").glob("*/job.json"), reverse=True)]
    data["current_attempt"] = current_attempt(p, data, data["prints"])
    if data["current_attempt"]:
        attempt = data["current_attempt"]
        attempt["has_dispatch_receipt"] = (p / "Print" / attempt["id"] / "dispatch.json").is_file()
    data["reviews"] = texts(p / "Review")
    data["sessions"] = texts(p / "Sessions")
    return data


def new_project(name, kind="functional", brief="", summary_text=""):
    if kind not in {"functional", "sculpture"}:
        raise WorkflowError("Invalid project kind")
    slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", name.strip()).strip("-_")[:64]
    if not slug:
        raise WorkflowError("Project name required")
    with lock():
        ids = [int(p["id"][1:]) for p in list_projects()]
        pid = f"P{max(ids, default=0) + 1:03}"
        p = ROOT / "Project" / f"{pid}-{slug}"
        p.mkdir(parents=True, exist_ok=False)
        for d in PROJECT_DIRS:
            (p / d).mkdir()
        stamp = now()
        data = {"id": pid, "name": name, "slug": slug, "status": "designing", "kind": kind,
                "created_at": stamp, "updated_at": stamp, "current_revision": None,
                "bambuddy_project_id": None, "summary": summary_text, "latest_session": "Sessions/handoff.md"}
        write_json(p / "project.json", data)
        template = ROOT / "Templates/Project"
        for source in template.rglob("*.md"):
            rel = source.relative_to(template)
            if rel.as_posix() not in {"brief.md", "decisions.md"} and rel.parts[0] not in PROJECT_DIRS:
                continue
            text = safe_path(template, rel.as_posix()).read_text(encoding="utf-8").replace("{{project_name}}", name)
            target = p / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        if not (p / "brief.md").exists():
            (p / "brief.md").write_text(f"# {name}\n\n待补充：用途、实测尺寸、材料与完成标准。\n", encoding="utf-8")
        if brief:
            with (p / "brief.md").open("a") as f:
                f.write("\n## 初始需求\n\n" + brief + "\n")
        if not (p / "decisions.md").exists():
            (p / "decisions.md").write_text("# 已确认决定\n\n尚无设计或打印批准。\n", encoding="utf-8")
        (p / "Sessions" / "handoff.md").write_text("# 接手\n\n已建立项目。尚未建模、切片或批准打印。下一步：补齐需求。\n", encoding="utf-8")
        choice_example = template / "Review/taste-choice.example.json"
        if choice_example.is_file():
            write_json(p / "Review/taste-choice.example.json", read_json(safe_path(template, "Review/taste-choice.example.json")))
        publication_template = template / "Review/Publication/record.json"
        if publication_template.is_file():
            write_json(p / "Review/Publication/record.json", read_json(safe_path(template, "Review/Publication/record.json")))
        return data


def context(pid=None):
    from . import shop, bambuddy
    paths = [ROOT / x for x in ["AGENTS.md", "Context/profile.md", "Context/workflow.md", "Library/Devices/X2D/device.json", "Library/Devices/X2D/installed.md", "Context/lessons.md"]]
    for rel in ("Context/image-to-print.md", "Context/agent-policy.json", "Context/taste.md", "Context/team.md"):
        if (ROOT / rel).is_file():
            paths.append(ROOT / rel)
    if (ROOT / "Library/Shopping/README.md").is_file():
        paths.append(ROOT / "Library/Shopping/README.md")
    if (ROOT / "Library/Materials/README.md").is_file():
        paths.append(ROOT / "Library/Materials/README.md")
    if (ROOT / "Library/Publishing/README.md").is_file():
        paths.append(ROOT / "Library/Publishing/README.md")
    if pid:
        p = project_path(pid)
        paths += [p / "project.json", p / "brief.md", p / "decisions.md"]
        for rel in ("Review/design-target.json", "Review/model-routing.md", "Review/model-routing.json", "Review/remix-plan.md", "Review/team.md"):
            if (p / rel).is_file():
                paths.append(p / rel)
        pointer = read_json(p / "project.json").get("latest_session")
        if pointer is not None:
            if not isinstance(pointer, str) or not pointer.startswith("Sessions/") or Path(pointer).suffix.lower() != ".md" or Path(pointer).name.lower() == "readme.md":
                raise WorkflowError("latest_session must identify a Markdown handoff inside Sessions")
            paths.append(safe_path(p / "Sessions", pointer[len("Sessions/"):]))
        else:
            sessions = sorted((x for x in (p / "Sessions").glob("*.md") if x.name.lower() != "readme.md" and not x.is_symlink()), key=lambda x: x.stat().st_mtime, reverse=True)
            paths += sessions[:1]
    result = {"project_id": read_json(p / "project.json")["id"] if pid else None, "loaded": [], "missing": [], "documents": [],
              "shopping": shop.view(pid), "materials": bambuddy.inventory()}
    from . import taste
    result["taste"] = taste.summary(pid)
    for p in paths:
        rel = p.relative_to(ROOT).as_posix()
        if p.is_file():
            result["loaded"].append(rel)
            result["documents"].append({"path": rel, "sha256": digest(p), "text": p.read_text(encoding="utf-8")[:24000]})
        else:
            result["missing"].append(rel)
    if pid:
        from . import publication
        try:
            result['publication'] = publication.check(pid)
        except (WorkflowError, OSError, ValueError) as exc:
            result['publication'] = {'status': 'awaiting_evidence', 'error': str(exc),
                                     'upload_authorized': False, 'uploaded': False}
    return result


def build(pid, revision, engine):
    p = project_path(pid)
    if not re.fullmatch(r"v\d{3,}", revision):
        raise WorkflowError("Revision must be v001-style")
    if engine not in {"cadquery", "blender"}:
        raise WorkflowError("Unsupported model engine")
    from . import design
    design.require_if_configured(pid, "views")
    if not (p / "Design" / revision / "model.py").is_file():
        raise WorkflowError("Design revision is missing model.py")
    out = p / "Exports" / revision / "build.json"
    if out.exists():
        raise WorkflowError("Built revisions are immutable; create a new revision")
    cfg = config()
    python = cfg.get("cad_python") or sys.executable
    command = [python, str(ROOT / "Harness/build_model.py"), "--project", str(p), "--revision", revision, "--engine", engine]
    with lock(read_json(p / "project.json")["id"]):
        if out.exists():
            raise WorkflowError("Built revisions are immutable; create a new revision")
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        evidence = ROOT / "Runtime/evidence" / f"{pid}-{revision}-build.log"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0 or not out.exists():
            raise WorkflowError(f"Model build failed; see {evidence}")
        manifest = read_json(out)
        if not (p / "Exports" / revision / "model.stl").is_file():
            raise WorkflowError("Build did not produce model.stl")
        checks = manifest.get("checks", {})
        if manifest.get("verified") is not True or not checks or any(v is not True for v in checks.values()):
            raise WorkflowError("Model build has failing validation checks")
        validate_build_lineage(p, revision, manifest)
        data = read_json(p / "project.json")
        data.update(current_revision=revision, status="awaiting_review", updated_at=now())
        write_json(p / "project.json", data)
        return manifest


def revision_files(p, revision):
    entries = {}
    for category in ("Design", "Exports"):
        d = p / category / revision
        if not d.is_dir():
            raise WorkflowError(f"Missing {category} revision")
        for f in sorted(d.rglob("*")):
            if f.is_symlink():
                raise WorkflowError("Revision files must not be symlinks")
            if f.is_file() and "__pycache__" not in f.parts and not f.name.startswith("."):
                entries[f.relative_to(p).as_posix()] = digest(f)
    return entries


def validate_3mf(path, plate=1):
    try:
        with zipfile.ZipFile(path) as z:
            key = f"Metadata/plate_{plate}.gcode"
            if key not in z.namelist() or z.getinfo(key).file_size == 0:
                raise WorkflowError("A non-empty sliced plate G-code is required")
    except (zipfile.BadZipFile, OSError) as exc:
        raise WorkflowError("Invalid sliced 3MF") from exc


def validate_build_lineage(p, revision, manifest):
    source = manifest.get("source_sha256")
    artifacts = manifest.get("artifacts")
    if not isinstance(source, dict) or not source or not isinstance(artifacts, dict) or not artifacts:
        raise WorkflowError("Build manifest lacks source and artifact provenance")
    current = {}
    for f in (p / "Design" / revision).rglob("*"):
        if f.is_symlink():
            raise WorkflowError("Source symlinks are not supported")
        if f.is_file() and "__pycache__" not in f.parts and not f.name.startswith("."):
            current[f.relative_to(p).as_posix()] = digest(f)
    if current != source:
        raise WorkflowError("Design changed since build; create a new revision and rebuild before slicing")
    required = f"Exports/{revision}/model.stl"
    if required not in artifacts:
        raise WorkflowError("Build manifest does not identify the model STL")
    for rel, expected in artifacts.items():
        if not (rel.startswith(f"Exports/{revision}/") or rel.startswith(f"Preview/{revision}/")):
            raise WorkflowError("Build artifact provenance crosses revision boundary")
        if digest(safe_path(p, rel)) != expected:
            raise WorkflowError("Build output changed since validation; create a new revision and rebuild")


def slice_metadata(path, plate=1):
    validate_3mf(path, plate)
    try:
        with zipfile.ZipFile(path) as z:
            settings = json.loads(z.read("Metadata/project_settings.config"))
            xml = ET.fromstring(z.read("Metadata/slice_info.config"))
        plates = [p for p in xml.findall(".//plate") if any(m.get("key") == "index" and m.get("value") == str(plate) for m in p.findall("metadata"))]
        if len(plates) != 1:
            raise ValueError("Selected plate metadata is missing or ambiguous")
        metadata = {m.attrib["key"]: m.get("value") for m in plates[0].findall("metadata")}
        def number(key):
            value = metadata.get(key)
            if value is None:
                return None
            v = float(value)
            return v if math.isfinite(v) and v >= 0 else None
        return {"curr_bed_type": settings.get("curr_bed_type"),
                "estimates": {"prediction_seconds": number("prediction"), "weight_grams": number("weight"),
                              "kind": "slicer_estimate", "source": "Metadata/slice_info.config"},
                "sliced_printer_model": settings.get("printer_model"), "sliced_filament_types": settings.get("filament_type")}
    except (KeyError, ValueError, ET.ParseError) as exc:
        raise WorkflowError("Cannot read sliced plate metadata: " + str(exc)) from exc


def print_configuration_issues(job):
    issues = []
    if job.get("printer_id") is None:
        issues.append("未绑定实际打印机")
    mapping = job.get("mapping", {})
    if mapping.get("routing_verified") is not True or not mapping.get("ams_mapping") or not mapping.get("extruder_mapping"):
        issues.append("实际耗材和挤出机路线尚未核验")
    if mapping.get("fts_installed") is not False or fts_declaration() is not False:
        issues.append("直连路线需绑定用户明确确认的无 FTS 配置")
    if not job.get("requested_bed_type"):
        issues.append("未明确确认实际打印板；切片中的板型仅为试算配置")
    elif job.get("curr_bed_type") != job["requested_bed_type"]:
        issues.append("切片板型与明确指定的打印板不一致")
    return issues


def inspect_slice(pid, jid, refresh=False):
    with lock("printer"):
        jd = job_path(pid, jid)
        job = read_json(jd / "job.json")
        artifact = safe_path(jd, job["artifact"])
        if job.get("artifact_sha256") != digest(artifact):
            raise WorkflowError("Sliced artifact changed; cannot refresh metadata")
        metadata = slice_metadata(artifact, job.get("plate", 1))
        inspected = {**job, **metadata}
        issues = print_configuration_issues(inspected)
        inspected.update(trial_only=bool(issues), configuration_issues=issues)
        if refresh:
            if job.get("state") not in {"awaiting_approval", "awaiting_configuration"} or (jd / "approval.json").exists() or (jd / "dispatch.json").exists():
                raise WorkflowError("Cannot change metadata of an approved or dispatched task")
            inspected.update(state="awaiting_configuration" if issues else "awaiting_approval", updated_at=now())
            write_json(jd / "job.json", inspected)
        return inspected


def slice_project(pid, machine, process, filaments, revision=None, plate=1, mapping=None, bed_type=None, input_3mf=None, preserve_layout=False):
    p = project_path(pid)
    revision = revision or read_json(p / "project.json").get("current_revision")
    if not revision:
        raise WorkflowError("Build a model first")
    from . import design
    design.require_if_configured(pid, "release", revision=revision)
    source = p / "Exports" / revision / "model.stl"
    if not source.is_file():
        raise WorkflowError("Model STL is missing")
    manifest = read_json(p / "Exports" / revision / "build.json", {})
    if manifest.get("verified") is not True or not manifest.get("checks") or any(v is not True for v in manifest["checks"].values()):
        raise WorkflowError("Slice requires a verified build with passing checks")
    validate_build_lineage(p, revision, manifest)
    input_inspection = None
    if preserve_layout and input_3mf is None:
        raise WorkflowError("Preserving layout requires a manifest-bound controlled 3MF")
    if input_3mf is not None:
        rel = str(input_3mf)
        if not rel.startswith(f"Exports/{revision}/") or Path(rel).suffix.lower() != ".3mf":
            raise WorkflowError("Controlled 3MF must be an artifact inside the selected revision's Exports directory")
        source = safe_path(p, rel)
        if manifest.get("artifacts", {}).get(rel) != digest(source):
            raise WorkflowError("3MF source must be registered in the verified build manifest")
        from . import three_mf
        input_inspection = three_mf.inspect(source, len(filaments))
    if plate != 1:
        raise WorkflowError("The single-model slice path supports plate 1 only")
    profiles = [Path(machine).resolve(), Path(process).resolve()] + [Path(x).resolve() for x in filaments]
    provenance = {}
    official_profiles = platforms.profile_directory(config()).resolve()
    for profile in profiles:
        sidecar = profile.with_suffix(".sources.json")
        if sidecar.exists():
            if sidecar.is_symlink():
                raise WorkflowError("Profile provenance cannot be a symbolic link")
            record = read_json(sidecar, {})
            if record.get("output_sha256") != digest(profile):
                raise WorkflowError("Profile differs from its resolved-source manifest")
            if not isinstance(record.get("source_files"), list) or not record["source_files"]:
                raise WorkflowError("Profile provenance must list its official source files")
            for dependency in record["source_files"]:
                source_file = Path(dependency.get("path", "")).resolve()
                if not source_file.is_relative_to(official_profiles) or source_file.suffix != ".json" or not source_file.is_file() or digest(source_file) != dependency.get("sha256"):
                    raise WorkflowError("Official profile dependency changed or escaped the bundled profile directory")
            provenance[profile] = sidecar
    if not filaments:
        raise WorkflowError("At least one explicit full filament profile is required")
    for f in profiles:
        d = read_json(f)
        if not isinstance(d, dict) or d.get("inherits") or d.get("include"):
            raise WorkflowError("Use complete exported profiles; unresolved inheritance/include is not accepted")
    machine_data = read_json(profiles[0])
    if "X2D" not in str(machine_data.get("printer_model", machine_data.get("name", ""))).upper():
        raise WorkflowError("Machine profile must explicitly target X2D")
    for field in ("machine_start_gcode", "machine_end_gcode", "printable_area"):
        if field not in machine_data:
            raise WorkflowError(f"Incomplete machine profile: missing {field}")
    from . import slicer_guard
    startup_issues = slicer_guard.template_issues(machine_data)
    if startup_issues:
        raise WorkflowError('; '.join(startup_issues))
    slicer = config().get("slicer_path", platforms.tool_defaults()["slicer_path"])
    if not Path(slicer).is_file():
        raise WorkflowError("Bambu Studio executable not available")
    with lock(read_json(p / "project.json")["id"]):
        validate_build_lineage(p, revision, manifest)
        jid = "J" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        jd = p / "Print" / jid
        (jd / "Profiles").mkdir(parents=True)
        copied = []
        for i, f in enumerate(profiles):
            target = jd / "Profiles" / f"{i:02}-{f.name}"
            shutil.copy2(f, target)
            if i == 1 and bed_type:
                profile = read_json(target)
                profile["curr_bed_type"] = bed_type
                write_json(target, profile)
            copied.append(target)
            if f in provenance:
                shutil.copy2(provenance[f], target.with_suffix(".sources.json"))
        source_relative = source.relative_to(p).as_posix()
        input_hashes = {}
        if input_inspection is not None:
            snapshot = jd / "Input/model.3mf"
            snapshot.parent.mkdir()
            shutil.copy2(source, snapshot)
            if digest(snapshot) != digest(source):
                raise WorkflowError("3MF source changed while snapshotting")
            input_hashes = {"Input/model.3mf": digest(snapshot)}
            source = snapshot
        manual_evidence = None
        if (mapping or {}).get('manual_studio_project') is True:
            if input_inspection is None or read_json(p / 'project.json')['id'] != 'P009' or revision != 'v033':
                raise WorkflowError('Manual project route only supports the explicitly reviewed P009 v033 geometry')
            from . import manual_project
            derived = jd / 'Input/manual-project.3mf'
            manual_evidence = manual_project.prepare(p, revision, profiles, mapping, derived)
            if manual_evidence.get('process_overrides'):
                # Fixed reviewed subset overrides; original export profiles stay immutable.
                process_copy = read_json(copied[1])
                process_copy.update(manual_evidence['process_overrides'])
                write_json(copied[1], process_copy)
                provenance_copy = copied[1].with_suffix('.sources.json')
                if provenance_copy.exists():
                    derived_provenance = read_json(provenance_copy)
                    derived_provenance.update(output_sha256=digest(copied[1]),
                        parent_profile_sha256=digest(profiles[1]),
                        plate_variant_overrides=manual_evidence['process_overrides'])
                    write_json(provenance_copy, derived_provenance)
            input_hashes['Input/manual-project.3mf'] = digest(derived)
            source = derived
        out = jd / "job.gcode.3mf"
        command = [slicer, "--load-settings", ";".join(map(str, copied[:2])), "--load-filaments", ";".join(map(str, copied[2:])), "--arrange", "0" if preserve_layout else "1", "--slice", "1", "--export-3mf", str(out), str(source)]
        job = {"id": jid, "project_id": read_json(p / "project.json")["id"], "revision": revision, "state": "slicing", "created_at": now(), "plate": plate, "mapping": mapping or {}, "source_hashes": revision_files(p, revision), "profile_hashes": {str(x.relative_to(jd)): digest(x) for x in (jd / "Profiles").iterdir()}, "slicer_path": slicer, "slicer_sha256": digest(Path(slicer)), "printer_id": config().get("printer_id"), "bambuddy_url": config().get("bambuddy_url"), "artifact": "job.gcode.3mf"}
        job["requested_bed_type"] = bed_type
        job["preserve_layout"] = preserve_layout
        if input_inspection is not None:
            job["input_hashes"] = input_hashes
            job["slice_input"] = {"source":source_relative,"sha256":input_hashes["Input/model.3mf"],**input_inspection}
            if manual_evidence is not None:
                job["slice_input"]["manual_project"] = manual_evidence
        write_json(jd / "job.json", job)
        try:
            r = subprocess.run(command, capture_output=True, text=True, timeout=900)
            (jd / "slicing.log").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
            if r.returncode:
                raise WorkflowError("Slicer returned a failure; inspect slicing.log")
            validate_3mf(out, plate)
            job.update(slice_metadata(out, plate))
            job['startup_audit'] = slicer_guard.assert_safe_archive(out, plate)
            if input_inspection is not None:
                output_inspection = input_inspection
                if manual_evidence and manual_evidence.get('selected_object_filament_assignments'):
                    output_inspection = {**input_inspection, 'object_filament_assignments': manual_evidence['selected_object_filament_assignments']}
                three_mf.validate_slice_output(out, output_inspection, plate)
                if preserve_layout:
                    import xml.etree.ElementTree as ET
                    with zipfile.ZipFile(source) as archive:
                        source_model = ET.fromstring(archive.read('3D/3dmodel.model'))
                    expected_count = len(source_model.find('{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}build'))
                    three_mf.validate_plate_object_count(out, expected_count, plate)
            if manual_evidence is not None:
                job['manual_project_audit'] = manual_project.validate_output(out, plate, variant=manual_evidence['plate_variant'])
            validate_build_lineage(p, revision, manifest)
            if revision_files(p, revision) != job["source_hashes"]:
                raise WorkflowError("Source files changed during slicing; output is not approvable")
        except Exception as e:
            job.update(state="slice_failed", error=str(e), updated_at=now())
            write_json(jd / "job.json", job)
            raise
        issues = print_configuration_issues(job)
        job.update(state="awaiting_configuration" if issues else "awaiting_approval", trial_only=bool(issues), configuration_issues=issues, artifact_sha256=digest(out), updated_at=now())
        write_json(jd / "job.json", job)
        return job


def job_path(pid, jid):
    if not re.fullmatch(r"J[\w-]+", jid):
        raise WorkflowError("Invalid print job ID")
    return safe_path(project_path(pid) / "Print", f"{jid}/job.json").parent


def job_fingerprint(p, jd, job):
    if read_json(p / "project.json").get("current_revision") != job["revision"]:
        raise WorkflowError("Project revision changed; previous approval is stale")
    if job.get("mapping", {}).get("fts_installed") is not False or fts_declaration() is not False:
        raise WorkflowError("FTS hardware declaration changed or is unconfirmed; previous route approval is invalid")
    validate_3mf(jd / job["artifact"], job.get("plate", 1))
    current_source = revision_files(p, job["revision"])
    if current_source != job["source_hashes"]:
        raise WorkflowError("Source or model changed; re-slice and request new approval")
    for rel, expected in job["profile_hashes"].items():
        if digest(safe_path(jd, rel)) != expected:
            raise WorkflowError("Slicing profile changed; approval is stale")
    for rel, expected in job.get("input_hashes", {}).items():
        if not rel.startswith("Input/") or digest(safe_path(jd, rel)) != expected:
            raise WorkflowError("Controlled slice input snapshot changed; approval is stale")
    actual_sha = digest(safe_path(jd, job["artifact"]))
    if actual_sha != job.get("artifact_sha256"):
        raise WorkflowError("Sliced file changed; approval is stale")
    if job.get("printer_id") != config().get("printer_id"):
        raise WorkflowError("Target printer changed; re-slice for the current device")
    if job.get("bambuddy_url") != config().get("bambuddy_url"):
        raise WorkflowError("Printer service endpoint changed; approval is stale")
    value = {"source": current_source, "profiles": job["profile_hashes"], "artifact": actual_sha,
             "printer_id": job["printer_id"], "bambuddy_url": job.get("bambuddy_url"), "mapping": job["mapping"], "plate": job["plate"], "revision": job["revision"], "slicer_sha256": job.get("slicer_sha256"), "requested_bed_type": job.get("requested_bed_type"), "curr_bed_type": job.get("curr_bed_type")}
    if job.get("input_hashes"):
        value["inputs"] = job["input_hashes"]
        value["slice_input"] = job.get("slice_input")
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def approve(pid, jid, confirmation="", plate_clear=False, confirmation_event_id=None):
    confirmation_facts = None
    if confirmation_event_id:
        from . import confirmation as confirmation_module
        confirmation_facts = confirmation_module.approval_facts(pid, jid, confirmation_event_id)
        confirmation = confirmation_facts["print_authorized"]["quote"]
        plate_clear = True
    if not plate_clear:
        raise WorkflowError("Explicit build-plate-clear confirmation is required")
    if not confirmation_facts and (not confirmation or not any(t in confirmation.lower() for t in ("确认打印", "开始打印", "approve print", "start print"))):
        raise WorkflowError("Record the user's explicit print confirmation, not design approval")
    if config().get("printer_id") is None:
        raise WorkflowError("Configure and verify the target printer before approval")
    with lock("printer"):
        if confirmation_event_id:
            from . import confirmation as confirmation_module
            confirmation_facts = confirmation_module.approval_facts(pid, jid, confirmation_event_id)
            confirmation = confirmation_facts["print_authorized"]["quote"]
        p = project_path(pid)
        jd = job_path(pid, jid)
        job = read_json(jd / "job.json")
        if job.get("trial_only") or print_configuration_issues(job):
            raise WorkflowError("Trial slice lacks verified device/mapping/plate configuration; configure then re-slice before approval")
        if job["state"] not in {"awaiting_approval", "approved"} or (jd / "dispatch.json").exists():
            raise WorkflowError("Only a fresh sliced job can be approved")
        from . import slicer_guard
        slicer_guard.assert_safe_archive(safe_path(jd, job['artifact']), job.get('plate', 1))
        receipt = {"job_id": jid, "approved_at": now(), "confirmation": confirmation,
                   "plate_clear": True, "fingerprint": job_fingerprint(p, jd, job)}
        if confirmation_facts:
            receipt["recorded_at"] = receipt["approved_at"]
            receipt["plate_clear_confirmed_at"] = confirmation_facts["plate_clear"]["recorded_at"]
            receipt["print_authorized_at"] = confirmation_facts["print_authorized"]["recorded_at"]
            receipt["approved_at"] = min(confirmation_facts[k]["recorded_at"] for k in ("print_authorized", "plate_clear"))
            receipt["confirmation_facts"] = confirmation_facts
            receipt["confirmation_event_id"] = confirmation_event_id
        previous = read_json(jd / "approval.json")
        if previous:
            write_json(jd / "ApprovalHistory" / (uuid.uuid4().hex + ".json"), previous)
        write_json(jd / "approval.json", receipt)
        job.update(state="approved", updated_at=now())
        write_json(jd / "job.json", job)
        return receipt


def retry_job(pid, jid, note, mapping=None):
    """Prepare a new attempt from exact sliced bytes; never approves or submits."""
    if not isinstance(note, str) or not note.strip():
        raise WorkflowError("Record why this new attempt is needed")
    terminal = {"failed", "cancelled", "awaiting_physical_review", "completed"}
    active = {"dispatching", "submitted", "printing", "running", "preparing", "paused", "dispatch_unknown", "staged_requires_reconciliation"}
    with lock("printer"):
        p, old_dir = project_path(pid), job_path(pid, jid)
        project = read_json(p / "project.json")
        if project.get("status") == "archived":
            raise WorkflowError("Explicitly reopen an archived project before preparing another attempt")
        old = read_json(old_dir / "job.json")
        if old.get("state") not in terminal:
            raise WorkflowError("Only an explicitly failed, cancelled or completed attempt can be retried; reconcile unknown/active tasks first")
        for other_project in list_projects():
            for path in (project_path(other_project["id"]) / "Print").glob("*/job.json"):
                if read_json(path, {}).get("state") in active:
                    raise WorkflowError("Another active or uncertain attempt must be reconciled before preparing a retry")
        receipt = read_json(old_dir / "dispatch.json", {})
        if receipt.get("state") == "unknown":
            observation = read_json(old_dir / "observation.json", {})
            native_observation = read_json(old_dir / "native-observation.json", {})
            queue = observation.get("queue", {})
            queue_failed = (receipt.get("queue_id") is not None and queue.get("id") == receipt["queue_id"]
                            and queue.get("status") in {"failed", "cancelled", "completed"})
            native_finished = (native_observation.get("matching_task") is True and native_observation.get("fresh") is True
                               and native_observation.get("device", {}).get("state") in {"FAILED", "FINISH", "CANCELLED"})
            if not queue_failed and not native_finished:
                raise WorkflowError("Unknown dispatch has no matching terminal observation; no retry prepared")
        original_fingerprint = job_fingerprint(p, old_dir, old)
        from . import slicer_guard
        slicer_guard.assert_safe_archive(safe_path(old_dir, old['artifact']), old.get('plate', 1))
        new_id = "J" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        new_dir = p / "Print" / new_id
        new_dir.mkdir()
        artifact = safe_path(old_dir, old["artifact"])
        target = new_dir / old["artifact"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, target)
        for field, prefix in (("profile_hashes", "Profiles/"), ("input_hashes", "Input/")):
            for rel, expected in old.get(field, {}).items():
                if not rel.startswith(prefix):
                    raise WorkflowError("Attempt snapshot crosses its allowed category")
                source = safe_path(old_dir, rel)
                if digest(source) != expected:
                    raise WorkflowError("Original attempt snapshot changed")
                copied = new_dir / rel
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, copied)
        if digest(target) != old["artifact_sha256"]:
            raise WorkflowError("Sliced bytes changed while copying retry")
        preserve = {key:old[key] for key in ("project_id", "revision", "plate", "source_hashes", "profile_hashes", "slicer_path", "slicer_sha256", "printer_id", "bambuddy_url", "artifact", "artifact_sha256", "requested_bed_type", "curr_bed_type", "estimates", "sliced_printer_model", "sliced_filament_types", "input_hashes", "slice_input") if key in old}
        job = {**preserve, "id":new_id, "created_at":now(), "updated_at":now(), "mapping":mapping if mapping is not None else old.get("mapping", {}),
               "retry_of":{"job_id":jid,"artifact_sha256":old["artifact_sha256"],"fingerprint":original_fingerprint,"reason":note.strip()},
               "root_attempt_id":old.get("root_attempt_id",jid)}
        if not isinstance(job["mapping"], dict):
            raise WorkflowError("Retry mapping must be an object")
        issues = print_configuration_issues(job)
        job.update(state="awaiting_configuration" if issues else "awaiting_approval", trial_only=bool(issues), configuration_issues=issues)
        job_fingerprint(p, new_dir, job)
        write_json(new_dir / "job.json", job)
        project.update(current_job_id=new_id, status=job["state"], updated_at=now())
        write_json(p / "project.json", project)
        return job


def review(pid, note, outcome):
    if outcome not in {"passed", "failed", "needs_changes"}:
        raise WorkflowError("Review outcome must be passed, failed, or needs_changes")
    if not note.strip():
        raise WorkflowError("A physical review note is required")
    with lock(pid):
        p = project_path(pid)
        data = read_json(p / "project.json")
        if data.get("status") == "archived":
            raise WorkflowError("Archived projects remain archived; explicitly reopen before review")
        if outcome == "passed":
            jobs = [read_json(f, {}) for f in (p / "Print").glob("*/job.json")]
            if not any(j.get("state") == "awaiting_physical_review" and j.get("revision") == data.get("current_revision") for j in jobs):
                raise WorkflowError("A confirmed completed print of the current revision is required before physical acceptance")
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        (p / "Review" / f"{stamp}.md").write_text(f"# 实物复盘\n\n日期：{now()}\n结果：{outcome}\n\n{note}\n", encoding="utf-8")
        data.update(status="completed" if outcome == "passed" else "needs_changes", updated_at=now())
        write_json(p / "project.json", data)
        return {"project_id": pid, "outcome": outcome}


def handoff(pid, note):
    if not note.strip():
        raise WorkflowError("Handoff text is required")
    p = project_path(pid)
    with lock(read_json(p / "project.json")["id"]):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        path = p / "Sessions" / f"{stamp}.md"
        with path.open("x", encoding="utf-8") as f:
            f.write(f"# 会话交接\n\n{now()}\n\n{note}\n")
            f.flush()
            os.fsync(f.fileno())
        project = read_json(p / "project.json")
        project.update(latest_session=path.relative_to(p).as_posix(), updated_at=now())
        write_json(p / "project.json", project)
        return {"path": str(path), "latest_session": project["latest_session"]}


def library():
    rows = []
    for base in (ROOT / "Library", ROOT / "Context"):
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in {".md", ".pdf", ".json", ".txt", ".html"}:
                rel = p.relative_to(ROOT).as_posix()
                try:
                    public_document(rel)
                except WorkflowError:
                    continue
                title = p.stem
                if p.suffix == ".md":
                    first = p.read_text(encoding="utf-8").splitlines()
                    if first and first[0].startswith("# "):
                        title = first[0][2:]
                rows.append({"path": rel, "title": title, "category": "/".join(p.relative_to(ROOT).parts[:3]), "url": "/api/documents/" + quote(rel, safe="/")})
    card = ROOT / "Library/Devices/X2D/installed.md"
    return {"documents": rows, "device_card": card.read_text(encoding="utf-8") if card.exists() else "本机配置尚未核验。"}


def doctor():
    cfg = config()
    required = {"builder": ROOT / "Harness/build_model.py", "slicer": Path(cfg.get("slicer_path", platforms.tool_defaults()["slicer_path"]))}
    for k in ("cad_python", "blender_path"):
        required[k] = Path(cfg[k]) if cfg.get(k) else None
    return {"root": str(ROOT), "tools": {k: {"path": str(v) if v else None, "available": bool(v and v.is_file())} for k, v in required.items()}, "printer_configured": cfg.get("printer_id") is not None, "context": context().get("loaded"), "missing_context": context().get("missing")}
