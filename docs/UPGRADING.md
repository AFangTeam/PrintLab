# Updates, backups and rollback

Before upgrading, record the release tag and local tool versions, finish file edits and stop the workbench. Preserve records for printing tasks or unknown receipts and read the actual device state first.

## Save your data

Run in the current workspace. On Windows, use `Runtime/venv/Scripts/python.exe`.

```bash
Runtime/venv/bin/python Harness/backup.py backup --verify
```

A successful result includes the snapshot path, restore-verification directory and `sha256: all_match`. Backups contain local credentials; keep them in a restricted directory. The command checks file restoration and database integrity. If Bambuddy is installed outside this workspace, also back up its data through Bambuddy's own facility.

Keep a complete source ZIP of the current version as well. The backup script copies only its listed directories; environments and third-party installations must be reconstructed at the appropriate versions.

## Upgrade

Git users should inspect `git status --short`, preserve local source/workflow edits, switch to the selected release tag and rerun setup. ZIP users should extract into a separate directory, keep the old directory and migrate `Project`, personal `Library`, `Runtime/config.json` and `Runtime/private`. Merge customized `Context` files individually with the new version, preserving device records and explicit user decisions.

On Mac, run `bash scripts/setup.sh`. On Windows, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1`. Initialization preserves existing configuration. Then run `doctor`, `context` and `scripts/verify_onboarding.py`; check project counts, recent handoffs, device identity and materials.

Recheck the files and device for tasks approved before upgrading. If the file or material mapping changed, obtain confirmation for the current task.

## Roll back

Stop the new workbench and preserve project/task records created after the upgrade. Extract the old source into a separate directory and rebuild dependencies using that version's setup script. Restore into the backup-verification directory first and check SHA-256 before migrating the appropriate data. Check projects and device connections; retain the newer directory to recover recent records.

Confirm target paths before actual restoration. Stop Bambuddy before restoring its database and follow its official process for the database and companion files. After rollback, run `doctor` and read-only status checks. Continue reconciling unknown send outcomes using their existing task records.

## Installation failures

- For an old Python, select Python 3.11+ with `PRINTLAB_PYTHON` and rerun setup.
- For PyPI/npm download failures, preserve the error type and failed domain, restore connectivity and rerun the same command.
- For inspector failures, run `Runtime/venv/bin/python scripts/install_inspector.py` (use the Windows interpreter there), then `doctor`.
- For an occupied port, identify the existing service. Use `--port` only for an independent workspace.
- For missing devices, check the Bambuddy page, actual URL, read key, printer ID and network mode in order. After the API connects, check data timestamps and materials.

Use the repository issue form with OS, release, redacted errors and reproduction steps. Keep credential files local.

## v0.5.0 project deletion

After upgrading and restarting the workbench, open **项目图册** (Projects), select a project, and choose **删除项目** (Delete project). Check the name and ID in the dialog. **取消** cancels. **永久删除** permanently removes the local project folder, including source copies, models, slices and session notes. It also removes the project from the prepared shelf and shared shopping requirements. Close open project files if the operating system reports they are in use, then retry.

Resolve any active or uncertain print for the project first so its dispatch record remains available for reconciliation. The printer's recorded history, shared stock and image-choice archive are retained. Original files stored outside the project and existing backups are independent copies.

## v0.4.4: English-first documentation

The default README and core installation/agent guides are now in English. Chinese remains available in `README.zh-CN.md`, and old `README.en.md` links still work. YouTube is the primary walkthrough link. Existing private project data, UI text and device-control behavior are unchanged. Merge any customized instructions deliberately; do not replace user records to change their language. See [language coverage](LANGUAGE.md).

## v0.4.3: route selection and queue checks

The read-only `dispatch-plan` command assesses the route before recommending permissions. Queue startup checks the file, plate and materials; previously approved tasks do not automatically switch routes.

A1 without AMS / using Ext still uses Studio fallback; this combination has no new automatic dispatch adapter. If Studio has already sliced the correct file, continue that print there without upgrading solely for troubleshooting. Upgrade when you want the newer route planning/window helper. Downloading a ZIP does not automatically upgrade an existing workspace.
