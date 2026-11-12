from __future__ import annotations

import argparse
import json
import sys
import httpx
from pathlib import Path

from . import bambuddy, core, shop


def parser():
    p = argparse.ArgumentParser(prog="printlab", description="PrintLab file-based design and approved printing workflow")
    sub = p.add_subparsers(dest="command", required=True)
    onboarding_parser = sub.add_parser('onboarding', help='Resume first-run setup and host-managed role creation')
    onboarding_commands = onboarding_parser.add_subparsers(dest='onboarding_command', required=True)
    onboarding_status = onboarding_commands.add_parser('status')
    onboarding_status.add_argument('--refresh', action='store_true')
    onboarding_commands.add_parser('discover')
    adopt_device = onboarding_commands.add_parser('adopt-device')
    adopt_device.add_argument('--expect-sha', required=True, help='Current device document SHA, or missing')
    host = onboarding_commands.add_parser('host')
    host.add_argument('--file', required=True, help='JSON with name, capabilities and observed tool evidence')
    host.add_argument('--expect', type=int, required=True)
    answer = onboarding_commands.add_parser('answer')
    answer.add_argument('key', choices=['usage_goals', 'cloud_needs', 'additional_materials'])
    answer.add_argument('--text', required=True)
    answer.add_argument('--source', required=True)
    answer.add_argument('--expect', type=int, required=True)
    reserve_role = onboarding_commands.add_parser('reserve-role')
    reserve_role.add_argument('role')
    reserve_role.add_argument('--request-id', required=True)
    reserve_role.add_argument('--expect', type=int, required=True)
    record_role = onboarding_commands.add_parser('record-role')
    record_role.add_argument('role')
    record_role.add_argument('--file', required=True)
    record_role.add_argument('--expect', type=int, required=True)
    record_role.add_argument('--adopt-existing', action='store_true', help='Bind an existing host chat after reading its actual workspace and reply')
    release_role = onboarding_commands.add_parser('release-role', help='Recover a failed host creation after verifying no chat was created')
    release_role.add_argument('role')
    release_role.add_argument('--request-id', required=True)
    release_role.add_argument('--evidence', required=True)
    release_role.add_argument('--expect', type=int, required=True)
    workspace_parser = sub.add_parser('workspace', help='Read and version-check shared facts; no printer actions')
    workspace_commands = workspace_parser.add_subparsers(dest='workspace_command', required=True)
    show_document = workspace_commands.add_parser('show')
    show_document.add_argument('name', choices=['profile', 'taste', 'lessons', 'team', 'device'])
    note = workspace_commands.add_parser('note')
    note.add_argument('name', choices=['profile', 'taste', 'lessons', 'team'])
    note.add_argument('--text', required=True)
    note.add_argument('--source', required=True)
    note.add_argument('--request-id', required=True)
    note.add_argument('--expect-sha', required=True)
    device_update = workspace_commands.add_parser('device')
    device_update.add_argument('--file', required=True, help='Confirmed device fact changes as JSON')
    device_update.add_argument('--source', required=True)
    device_update.add_argument('--expect-sha', required=True)
    workspace_commands.add_parser('connection')
    profiles = workspace_commands.add_parser('profiles', help='List installed official machine presets')
    profiles.add_argument('--model')
    profile = workspace_commands.add_parser('profile', help='Record a matching official machine preset and source hashes')
    profile.add_argument('--name', required=True)
    profile.add_argument('--expect-sha', required=True)
    connect = workspace_commands.add_parser('connect')
    connect.add_argument('--url', required=True)
    connect.add_argument('--printer-id', type=int, required=True)
    connect.add_argument('--expect-sha', required=True)
    intake = sub.add_parser('material-intake', help='Register one user-confirmed spool; does not load or print')
    intake.add_argument('--file', required=True, help='JSON describing one physical spool')
    intake.add_argument('--source', required=True, help='User confirmation of owning this spool')
    intake.add_argument('--request-id', required=True, help='Stable ID for this physical spool and intake operation')
    constraints = sub.add_parser('constraints', help='Read or capture project-specific device and material facts')
    constraints.add_argument('action', choices=['show', 'capture'])
    constraints.add_argument('project')
    constraints.add_argument('--source', help='Reason for this design context capture')
    constraints.add_argument('--expect-sha', help='Current snapshot SHA or missing for the first capture')
    shelf = sub.add_parser('prepared', help='Prepared shelf; registration and checks never print')
    shelf_sub = shelf.add_subparsers(dest='prepared_command', required=True)
    shelf_sub.add_parser('list')
    reg = shelf_sub.add_parser('register')
    reg.add_argument('project')
    reg.add_argument('job')
    reg.add_argument('--title')
    reg.add_argument('--part', action='append')
    reg.add_argument('--note')
    chk = shelf_sub.add_parser('check')
    chk.add_argument('project')
    chk.add_argument('job')
    history_parser = sub.add_parser('history', help='Read all captured print history, including external prints; never prints')
    history_parser.add_argument('--refresh', action='store_true')
    recovery = sub.add_parser('history-recover', help='Recover previews for captured archives; dry-run by default')
    recovery.add_argument('--printer-id', type=int, help='Defaults to the configured Bambuddy printer')
    source = recovery.add_mutually_exclusive_group()
    source.add_argument('--cache-dir', help='macOS CFURL/WebKit cache root or a copy of that cache')
    source.add_argument('--manifest', help='JSON binding local PNG/3MF files to archive, device, profile and plate')
    recovery.add_argument('--apply', action='store_true', help='Persist new previews while preserving existing entries')
    recovery.add_argument('--fetch-missing', action='store_true', help='Fetch missing image bodies from known official cache URLs')
    taste = sub.add_parser("taste", help="Archive full image-choice rounds; never prints or confirms inferred preferences")
    taste_commands = taste.add_subparsers(dest="taste_command", required=True)
    taste_record = taste_commands.add_parser("record")
    taste_record.add_argument("project")
    taste_record.add_argument("--manifest", required=True, help="JSON manifest of presented options and actual user response")
    taste_list = taste_commands.add_parser("list")
    taste_list.add_argument("--project")
    design = sub.add_parser("design-check", help="Verify shape choice, selected three-view set, and model review; never prints")
    design.add_argument("project")
    design.add_argument("--stage", choices=["input", "views", "release"], default="views")
    design.add_argument("--reference", help="Project-relative image for the input-stage check")
    design.add_argument("--revision", help="vNNN for the release-stage check")
    image3d = sub.add_parser("image3d", help="Local image-to-shape candidates; never slices or prints")
    image_commands = image3d.add_subparsers(dest="image3d_command", required=True)
    image_doctor = image_commands.add_parser("doctor")
    image_doctor.add_argument("--verify-weights", action="store_true")
    image_inspect = image_commands.add_parser("inspect")
    image_inspect.add_argument("project")
    image_inspect.add_argument("--candidate", required=True)
    image_generate = image_commands.add_parser("generate")
    image_generate.add_argument("project")
    image_generate.add_argument("--reference", required=True, help="Project-relative single-object image")
    image_generate.add_argument("--candidate", required=True, help="New independent candidate ID")
    image_generate.add_argument("--crop", nargs=4, type=int, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    image_generate.add_argument("--height-mm", type=float, required=True, help="Chosen scale, not a dimension inferred from the image")
    image_generate.add_argument("--steps", type=int, default=30)
    image_generate.add_argument("--resolution", type=int, choices=[128, 256, 384], default=256)
    image_generate.add_argument("--seed", type=int, default=42)
    image_generate.add_argument("--quantize", type=int, choices=[4, 8], default=8)
    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--kind", choices=["functional", "sculpture"], default="functional")
    n.add_argument("--brief", default="")
    n.add_argument("--summary", default="")
    c = sub.add_parser("context")
    c.add_argument("project", nargs="?")
    b = sub.add_parser("build")
    b.add_argument("project")
    b.add_argument("--revision", required=True)
    b.add_argument("--engine", choices=["cadquery", "blender"], required=True)
    ep = sub.add_parser("export-project", help="Create and verify an editable Bambu Studio 3MF from the reviewed model")
    ep.add_argument("project")
    ep.add_argument("--revision")
    ep.add_argument("--machine", required=True)
    ep.add_argument("--process", required=True)
    ep.add_argument("--filament", action="append", required=True)
    ep.add_argument("--bed-type", required=True, choices=["Textured PEI Plate"])
    ip = sub.add_parser("inspect-project", help="Verify a full editable 3MF; reject geometry-only and sliced packages")
    ip.add_argument("path")
    v = sub.add_parser("preview")
    v.add_argument("project")
    s = sub.add_parser("slice")
    s.add_argument("project")
    s.add_argument("--machine", required=True)
    s.add_argument("--process", required=True)
    s.add_argument("--filament", required=True, action="append")
    s.add_argument("--revision")
    s.add_argument("--mapping-json", default="{}")
    s.add_argument("--bed-type", help="Exact physically verified Bambu Studio plate type; omitted slices are trial-only")
    s.add_argument("--input-3mf", help="Manifest-bound current Exports/revision geometry-only 3MF with explicit object filament assignment")
    s.add_argument("--preserve-layout", action="store_true", help="Keep the reviewed controlled 3MF placement; verify every build object remains on this plate")
    i = sub.add_parser("inspect-slice")
    i.add_argument("project")
    i.add_argument("job")
    i.add_argument("--refresh", action="store_true", help="Persist metadata/classification only for an unapproved task")
    nc = sub.add_parser("native-check", help="Inspect the sliced artifact and fresh X2D telemetry without uploading or printing")
    nc.add_argument("project")
    nc.add_argument("job")
    ni = sub.add_parser("native-inspect", help="Offline integrity and actual G-code audit; never connects to the printer")
    ni.add_argument("project")
    ni.add_argument("job")
    a = sub.add_parser("approve")
    a.add_argument("project")
    a.add_argument("job")
    a.add_argument("--confirmation", default="")
    a.add_argument("--confirmation-event", help="Recorded exact-task authorization and plate-clear evidence")
    a.add_argument("--plate-clear", action="store_true")
    d = sub.add_parser("submit")
    d.add_argument("project")
    d.add_argument("job")
    d.add_argument("--execute", action="store_true", help="Send this approved task; default only validates")
    so = sub.add_parser('studio-copy', help='Prepare an unapproved official-app package with identical G-code; never sends')
    so.add_argument('project')
    so.add_argument('job')
    bridge = sub.add_parser('studio-bridge', help='Build or inspect the official Studio helper')
    bridge.add_argument('action', choices=['build', 'capability', 'permissions'])
    r = sub.add_parser("reconcile")
    r.add_argument("project")
    r.add_argument("job")
    sub.add_parser("status")
    sub.add_parser("materials", help="Read shared live filament quantities; never resets the full-spool baseline")
    sub.add_parser("doctor")
    r = sub.add_parser("review")
    r.add_argument("project")
    r.add_argument("--outcome", required=True, choices=["passed", "failed", "needs_changes"])
    r.add_argument("--note", required=True)
    h = sub.add_parser("handoff")
    h.add_argument("project")
    h.add_argument("--note", required=True)
    card = sub.add_parser("confirmation", help="One read-only task card: preserved answers and current missing items")
    card.add_argument("project")
    card.add_argument("job", nargs="?")
    facts = sub.add_parser("record-confirmation", help="Record explicit user facts with their original quote and source")
    facts.add_argument("project")
    facts.add_argument("job")
    facts.add_argument("--facts-json", required=True)
    facts.add_argument("--quote", required=True)
    facts.add_argument("--source", required=True)
    facts.add_argument("--confirmed-at", help="Original timezone-aware user-message time when importing an earlier confirmation")
    retry = sub.add_parser("retry", help="Copy an explicitly terminal attempt's exact slice into an unapproved draft; never dispatches")
    retry.add_argument("project")
    retry.add_argument("job")
    retry.add_argument("--note", required=True)
    retry.add_argument("--mapping-json")
    cancel = sub.add_parser('register-cancel', help='Link an existing successful MCP stop receipt to its exact terminal task; never sends a command')
    cancel.add_argument('project')
    cancel.add_argument('job')
    cancel.add_argument('--receipt', required=True, help='Project-relative JSON receipt from the actual complete MCP cancel call')
    publication = sub.add_parser('publish', help='Local MakerWorld preflight and review packet; never uploads')
    publishing = publication.add_subparsers(dest='publish_command', required=True)
    release_init = publishing.add_parser('init', help='Create a public-upload review record without overwriting existing work')
    release_init.add_argument('project')
    release_init.add_argument('--kind', choices=['unknown', 'original', 'remix', 'print_profile'], default='unknown')
    for action in ['check', 'prepare']:
        release = publishing.add_parser(action)
        release.add_argument('project')
    shopping = sub.add_parser("shop", help="Shared non-printable parts; never orders or prints")
    commands = shopping.add_subparsers(dest="shop_command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("project", nargs="?")
    confirm = commands.add_parser("confirm", help="Record explicit user decision to make, not print approval")
    confirm.add_argument("project")
    confirm.add_argument("--quote", required=True)
    confirm.add_argument("--source", required=True)
    sync = commands.add_parser("sync", help="Replace this project's full parts list; stable IDs prevent duplicates")
    sync.add_argument("project")
    sync.add_argument("--file", required=True)
    sync.add_argument("--source", required=True)
    stock = commands.add_parser("stock", help="Set absolute remaining amounts, never increment on retry")
    stock.add_argument("item")
    stock.add_argument("--existing", required=True, help="Non-negative integer or unknown")
    stock.add_argument("--purchased", required=True, type=int)
    stock.add_argument("--note", required=True)
    supplier = commands.add_parser("supplier")
    supplier.add_argument("item")
    supplier.add_argument("--status", required=True, choices=["available", "unavailable", "unverified"])
    supplier.add_argument("--url")
    supplier.add_argument("--evidence", required=True)
    fulfill = commands.add_parser("fulfill", help="Record received parts actually used; consumes stock once")
    fulfill.add_argument("project")
    fulfill.add_argument("--note", required=True)
    for command in [confirm, sync, stock, supplier, fulfill]:
        command.add_argument("--expect", type=int, required=True, help="Current Shop List version from shop list")
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        if a.command == 'workspace':
            from . import workspace
            expected = None if getattr(a, 'expect_sha', None) == 'missing' else getattr(a, 'expect_sha', None)
            if a.workspace_command == 'show':
                result = workspace.document(a.name)
            elif a.workspace_command == 'note':
                result = workspace.append_note(a.name, a.text, a.source, a.request_id, expected)
            elif a.workspace_command == 'device':
                result = workspace.update_device(json.loads(Path(a.file).read_text(encoding='utf-8')), a.source, expected)
            elif a.workspace_command == 'connection':
                result = workspace.connection()
            elif a.workspace_command == 'profiles':
                from . import machine_profiles
                result = machine_profiles.list_profiles(a.model)
            elif a.workspace_command == 'profile':
                from . import machine_profiles
                result = machine_profiles.adopt(a.name, expected)
            else:
                result = workspace.configure_connection(a.url, a.printer_id, expected)
        elif a.command == 'constraints':
            from . import constraints
            if a.action == 'show':
                result = constraints.view(a.project)
            else:
                if not a.source or not a.expect_sha:
                    raise core.WorkflowError('capture requires --source and --expect-sha')
                result = constraints.capture(a.project, a.source, None if a.expect_sha == 'missing' else a.expect_sha)
        elif a.command == 'material-intake':
            from . import material_intake
            result = material_intake.register(json.loads(Path(a.file).read_text(encoding='utf-8')), a.source, a.request_id)
        elif a.command == 'onboarding':
            from . import onboarding
            if a.onboarding_command == 'status':
                result = onboarding.view(bambuddy.device(), bambuddy.inventory()) if a.refresh else onboarding.view()
            elif a.onboarding_command == 'discover':
                result = onboarding.discover()
            elif a.onboarding_command == 'adopt-device':
                result = onboarding.adopt_device(None if a.expect_sha == 'missing' else a.expect_sha)
            elif a.onboarding_command == 'host':
                result = onboarding.record_host(**json.loads(Path(a.file).read_text(encoding='utf-8')), expected=a.expect)
            elif a.onboarding_command == 'answer':
                result = onboarding.answer(a.key, a.text, a.source, a.expect)
            elif a.onboarding_command == 'reserve-role':
                result = onboarding.reserve_role(a.role, a.request_id, a.expect)
            elif a.onboarding_command == 'release-role':
                result = onboarding.release_role(a.role, a.request_id, a.evidence, a.expect)
            else:
                result = onboarding.record_role(a.role, json.loads(Path(a.file).read_text(encoding='utf-8')), a.expect, adopt=a.adopt_existing)
        elif a.command == 'prepared':
            from . import prepared, workbench
            if a.prepared_command == 'list':
                result = prepared.catalogue()
            elif a.prepared_command == 'register':
                result = prepared.register(a.project, a.job, title=a.title, parts=a.part, note=a.note)
            else:
                result = workbench.check(a.project, a.job)
        elif a.command == "taste":
            from . import taste
            if a.taste_command == "record":
                result = taste.record(a.project, json.loads(Path(a.manifest).read_text(encoding="utf-8")))
            else:
                result = taste.summary(a.project, limit=0)
        elif a.command == "design-check":
            from . import design
            result = design.check(a.project, a.stage, a.revision, a.reference)
        elif a.command == "image3d":
            from . import image3d
            if a.image3d_command == "doctor":
                result = image3d.doctor(a.verify_weights)
            elif a.image3d_command == "inspect":
                result = image3d.inspect(a.project, a.candidate)
            else:
                result = image3d.generate(a.project, a.reference, a.candidate, a.crop, a.height_mm,
                                          a.steps, a.resolution, a.seed, a.quantize)
        elif a.command == "new":
            result = core.new_project(a.name, a.kind, a.brief, a.summary)
        elif a.command == "context":
            result = core.context(a.project)
        elif a.command == "build":
            result = core.build(a.project, a.revision, a.engine)
        elif a.command == "export-project":
            from . import project3mf
            result = project3mf.export(a.project, a.revision, a.machine, a.process, a.filament, a.bed_type)
        elif a.command == "inspect-project":
            from . import project3mf
            result = project3mf.inspect(Path(a.path))
        elif a.command == "preview":
            p = core.project_path(a.project)
            result = core.summary(p)
            result["studio_url"] = core.config().get("studio_url", "http://127.0.0.1:8018") + "/?project=" + a.project
        elif a.command == "slice":
            mapping = json.loads(a.mapping_json)
            if not isinstance(mapping, dict):
                raise core.WorkflowError("Mapping JSON must be an object")
            result = core.slice_project(a.project, a.machine, a.process, a.filament, a.revision, mapping=mapping, bed_type=a.bed_type, input_3mf=a.input_3mf, preserve_layout=a.preserve_layout)
        elif a.command == "inspect-slice":
            result = core.inspect_slice(a.project, a.job, a.refresh)
        elif a.command == "approve":
            result = core.approve(a.project, a.job, a.confirmation, a.plate_clear, confirmation_event_id=a.confirmation_event)
        elif a.command == "native-check":
            from . import native
            result = native.check(a.project, a.job)
        elif a.command == "native-inspect":
            from . import native
            jd = core.job_path(a.project, a.job)
            job = core.read_json(jd / "job.json")
            core.job_fingerprint(core.project_path(a.project), jd, job)
            result = native.run_client(jd, job, "inspect")
        elif a.command == "submit":
            result = bambuddy.submit(a.project, a.job, a.execute)
        elif a.command == 'studio-copy':
            from . import official
            result = official.prepare(a.project,a.job)
        elif a.command == 'studio-bridge':
            from . import studio_bridge
            if a.action == 'build':
                result = {'app_path': str(studio_bridge.build_helper()), 'printed': False}
            elif a.action == 'permissions':
                result = studio_bridge.setup_permissions()
            else:
                result = studio_bridge.capability()
        elif a.command == "reconcile":
            with core.lock("printer"):
                result = bambuddy.reconcile(a.project, a.job)
        elif a.command == "status":
            result = {"device": bambuddy.device(), "projects": core.list_projects()}
        elif a.command == "materials":
            result = bambuddy.inventory()
        elif a.command == "review":
            result = core.review(a.project, a.note, a.outcome)
        elif a.command == "handoff":
            result = core.handoff(a.project, a.note)
        elif a.command == "confirmation":
            from . import confirmation
            result = confirmation.card(a.project, a.job)
        elif a.command == "record-confirmation":
            from . import confirmation
            result = confirmation.record(a.project, a.job, json.loads(a.facts_json), a.quote, a.source, confirmed_at=a.confirmed_at)
        elif a.command == "retry":
            result = core.retry_job(a.project, a.job, a.note, mapping=json.loads(a.mapping_json) if a.mapping_json else None)
        elif a.command == 'register-cancel':
            from . import cancelled_transition
            result = cancelled_transition.register(a.project,a.job,a.receipt)
        elif a.command == 'publish':
            from . import publication
            if a.publish_command == 'init':
                result = publication.init(a.project, a.kind)
            elif a.publish_command == 'check':
                result = publication.check(a.project)
            else:
                result = publication.prepare(a.project)
        elif a.command == "shop":
            if a.shop_command == "list":
                result = shop.view(a.project)
            elif a.shop_command == "confirm":
                result = shop.confirm(a.project, a.quote, a.source, a.expect)
            elif a.shop_command == "sync":
                result = shop.sync(a.project, json.loads(Path(a.file).read_text(encoding="utf-8")), a.expect, a.source)
            elif a.shop_command == "stock":
                existing = None if a.existing == "unknown" else int(a.existing)
                result = shop.stock(a.item, existing, a.purchased, a.note, a.expect)
            elif a.shop_command == "supplier":
                result = shop.supplier(a.item, a.status, a.url, a.evidence, a.expect)
            else:
                result = shop.fulfill(a.project, a.note, a.expect)
        elif a.command == 'history-recover':
            from . import preview_recovery
            result = preview_recovery.recover(printer_id=a.printer_id, cache_dir=a.cache_dir,
                                              manifest=a.manifest, apply=a.apply, fetch_missing=a.fetch_missing)
        elif a.command == 'history':
            from . import history
            result = history.view(force=a.refresh)
        else:
            result = core.doctor()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if a.command == 'design-check' and result.get('status') != 'passed':
            return 2
        if a.command == 'image3d' and (result.get('integrity') == 'failed' or result.get('status') in {'unavailable', 'incomplete'}):
            return 2
        if a.command == 'publish' and a.publish_command == 'check' and result['status'] in {'awaiting_evidence', 'not_allowed'}:
            return 2
        return 2 if a.command == "native-inspect" and result.get("ok") is False else 0
    except (core.WorkflowError, OSError, ValueError, httpx.HTTPError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
