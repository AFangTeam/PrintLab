"""Delete one explicitly selected local project and its workbench associations."""
from contextlib import ExitStack
from pathlib import Path
import os
import re
import shutil
import stat
import tempfile

from . import bambuddy, core, history, prepared, shop

TERMINAL_JOBS = {'awaiting_physical_review', 'completed', 'failed', 'cancelled', 'dispatch_rejected'}


class ProjectMissing(core.WorkflowError):
    pass


def _workspace_path(relative):
    # Compare the resolved and lexical paths as well: Windows junctions can
    # redirect a directory without reporting is_symlink() on older Python.
    path = core.safe_path(core.ROOT, str(relative), require_file=False)
    if path != core.ROOT / relative:
        raise core.WorkflowError('工作区路径已重定向，无法安全清理')
    return path


def _project(pid):
    root = _workspace_path('Project')
    matches = list(root.glob(f'{pid}-*'))
    if not matches:
        raise ProjectMissing('项目不存在或已删除')
    if len(matches) != 1:
        raise core.WorkflowError('同一编号对应多个目录，无法确定要删除的项目')
    path = matches[0]
    metadata = core.read_json(_workspace_path(path.relative_to(core.ROOT) / 'project.json'))
    if not path.name.startswith(pid + '-') or not isinstance(metadata, dict) or metadata.get('id') != pid:
        raise core.WorkflowError('项目目录和记录的编号不一致，无法安全删除')
    return path, metadata


def _job_states(project):
    states = {}
    print_dir = _workspace_path(project.relative_to(core.ROOT) / 'Print')
    if print_dir.is_dir():
        for entry in print_dir.iterdir():
            if not entry.is_dir() or entry.is_symlink() or entry.resolve() != entry:
                continue
            record = _workspace_path(entry.relative_to(core.ROOT) / 'job.json')
            state = core.read_json(record, {}).get('state')
            states[entry.name] = state
            receipt = core.read_json(_workspace_path(entry.relative_to(core.ROOT) / 'dispatch.json'))
            has_receipt = receipt is not None or (entry / 'studio-send-claimed.json').exists()
            uncertain = has_receipt and state not in TERMINAL_JOBS
            if receipt and receipt.get('state') in {'unknown', 'dispatch_unknown'}:
                settled = state == 'dispatch_rejected' and (entry / 'dispatch-resolution.json').is_file()
                uncertain |= not settled and not core.has_terminal_observation(entry, receipt)
            if state in bambuddy.ACTIVE_JOB_STATES or uncertain:
                raise core.WorkflowError(f'打印任务 {entry.name} 正在运行或发送结果待核对，暂时无法删除')
    return states


def _workbench_files(pid, states):
    owned = []
    for kind in ('operations', 'checks'):
        folder = _workspace_path(f'Runtime/workbench/{kind}')
        for file in folder.glob('*.json'):
            data = core.read_json(_workspace_path(file.relative_to(core.ROOT)))
            if data.get('project_id') != pid:
                continue
            if kind == 'operations':
                state = data.get('state')
                if state != 'blocked' and not (
                    state in {'observed', 'submitted', 'unknown'} and states.get(data.get('job_id')) in TERMINAL_JOBS
                ):
                    raise core.WorkflowError('工作台正在核验或发送打印任务，或发送结果待核对，暂时无法删除')
            owned.append(file)
    return owned


def _detach_favorites(pid, studio_origin):
    path = _workspace_path('Library/References/favorites.json')
    catalog = core.read_json(path, {})
    items = catalog.get('items') if isinstance(catalog, dict) else None
    if not isinstance(items, list):
        return
    changed = False
    # These are Workbench routes. External sites and shared Library pages
    # may describe the same design and must keep their original links.
    target = re.compile(rf'^(?:/?#/projects/{pid}|/api/(?:projects|files)/{pid})(?:[/?#]|$)')
    for item in items:
        if not isinstance(item, dict):
            continue
        related = item.get('related_project_ids')
        if isinstance(related, list) and pid in related:
            item['related_project_ids'] = [entry for entry in related if entry != pid]
            changed = True
        link = item.get('local_detail_url')
        if isinstance(link, str):
            if studio_origin and link.startswith(studio_origin + '/'):
                link = link[len(studio_origin):]
            if target.match(link):
                del item['local_detail_url']
                changed = True
    if changed:
        if type(catalog.get('version')) is int:
            catalog['version'] += 1
        catalog['updated_at'] = core.now()
        core.write_json(path, catalog)


def _detach_catalogues(pid, studio_origin):
    _detach_favorites(pid, studio_origin)
    shelf_path = _workspace_path(prepared.REGISTRY)
    shelf = prepared._registry()
    remaining = [row for row in shelf['items'] if row['project_id'] != pid]
    if len(remaining) != len(shelf['items']):
        shelf.update(items=remaining, updated_at=core.now())
        core.write_json(shelf_path, shelf)

    shop_path = _workspace_path(shop.STORE)
    ledger = shop.load()
    if ledger['projects'].pop(pid, None) is not None:
        stamp = core.now()
        ledger['version'] += 1
        ledger['updated_at'] = stamp
        ledger['history'].append({'action': 'delete_project', 'project_id': pid, 'at': stamp, 'version': ledger['version']})
        core.write_json(shop_path, ledger)


def _check_mounts(folder):
    # Check volume mounts before skipping links: Windows directory junctions
    # and mounted folders both use the mount-point reparse tag.
    if os.path.ismount(folder):
        raise core.WorkflowError('目录是挂载的磁盘，无法安全删除')
    for base, dirs, _ in os.walk(folder, followlinks=False):
        for name in dirs.copy():
            child = Path(base) / name
            if os.path.ismount(child):
                raise core.WorkflowError('项目目录中包含挂载的磁盘，请先卸载后重试')
            if child.is_symlink() or child.resolve() != child:
                dirs.remove(name)


def _remove_caches(pid, project):
    for log in _workspace_path('Runtime/evidence').glob(f'{pid}-v*-build.log'):
        if re.fullmatch(rf'{pid}-v[0-9]{{3,}}-build\.log', log.name) and not log.is_dir():
            log.unlink()
    for preview in _workspace_path('Runtime/studio-previews').glob('preview-*'):
        if preview.is_symlink() or preview.resolve() != preview or not preview.is_dir():
            continue
        manifest = _workspace_path(preview.relative_to(core.ROOT) / 'source.json')
        source = core.read_json(manifest, {}).get('source')
        if isinstance(source, str) and Path(source).is_absolute() and Path(source).resolve().is_relative_to(project):
            _check_mounts(preview)
            _remove_contents(preview, manifest, core.read_json(manifest))


def _remove_tree(project, metadata):
    # Keep the project addressable for a retry after a permission/locked-file
    # error. Delete the identity only once all children were actually removed.
    # Retire the entire job namespace before recursively removing it. A
    # partially removed Print/ must not leave orphan receipts that block retry.
    job_dir = project / 'Print'
    if job_dir.exists():
        retired = Path(tempfile.mkdtemp(prefix='.deleting-', dir=project))
        job_dir.rename(retired / 'Print')
    _remove_contents(project, project / 'project.json', metadata)


def _remove_contents(project, manifest, metadata):
    for entry in project.iterdir():
        if entry == manifest:
            continue
        if os.name == 'nt' and entry.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT:
            # rmtree refuses a junction as its root. Remove only the junction.
            if os.path.ismount(entry):
                raise core.WorkflowError('项目目录中包含挂载的磁盘，请先卸载后重试')
            entry.rmdir()
        elif entry.is_symlink() or not entry.is_dir():
            entry.unlink()
        else:
            shutil.rmtree(entry)
    manifest.unlink()
    try:
        project.rmdir()
    except OSError:
        core.write_json(manifest, metadata)
        raise


def delete(pid, confirm_id, *, studio_origin=None):
    if not re.fullmatch(r'P[0-9]{3,}', pid):
        raise ProjectMissing('请使用工作台上的项目编号')
    if confirm_id != pid:
        raise core.WorkflowError('确认编号与要删除的项目不一致')
    # Match the lock order of workbench start/reconcile and Studio dispatch.
    with ExitStack() as locks:
        for name in ('workflow', pid, 'workbench-start', 'studio-bridge', 'printer', 'prepared-catalogue', 'shop', 'print-history'):
            locks.enter_context(core.lock(name))
        project, metadata = _project(pid)
        _check_mounts(project)
        jobs = _job_states(project)
        if metadata.get('status') in bambuddy.ACTIVE_JOB_STATES:
            # A cancelled queue job can leave an older "printing" project
            # summary behind. Its own terminal record is authoritative.
            current = metadata.get('current_job_id')
            finished = jobs.get(current) in TERMINAL_JOBS if current else bool(jobs) and all(
                state in TERMINAL_JOBS for state in jobs.values())
            if not finished:
                raise core.WorkflowError('项目有正在运行或发送结果待核对的打印任务，暂时无法删除')
        files = _workbench_files(pid, jobs)
        # Legacy installations never assigned a high-water mark. Persist it
        # before this ID disappears from the visible project directory.
        core.reserve_project_id(int(pid[1:]))
        _detach_catalogues(pid, studio_origin)
        history.detach_project(pid)
        for file in files:
            file.unlink()
        _remove_caches(pid, project)
        if metadata.get('status') in bambuddy.ACTIVE_JOB_STATES:
            # Preserve the completed safety check across partial removal of
            # Print/. Retries still check every remaining job and operation.
            metadata = {**metadata, 'status': 'deleting'}
            core.write_json(project / 'project.json', metadata)
        _remove_tree(project, metadata)
    return {'deleted': True, 'project_id': pid}
