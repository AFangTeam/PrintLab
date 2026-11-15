# Windows installation and workflow

Windows provides the browser workbench, project/version management, Unicode records, cross-session handoffs, materials/history, shopping lists and prepared print packages. Use Python 3.11+, Node.js 22+ (including npm) and an agent with local terminal/file access. The UI currently uses Chinese; see [language coverage](LANGUAGE.md).

## Install and start

Download `PrintLab.zip` from a release and extract it, or clone the repository. Open PowerShell in the PrintLab folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Open <http://127.0.0.1:8018> and keep the launch terminal running. For a separate workspace on another port, append `--port 18018` to the start command. The execution-policy option applies only to that process.

Setup prefers Python Launcher's `py -3` and also supports `python` on PATH. To select an interpreter, set `$env:PRINTLAB_PYTHON = 'C:\path\to\python.exe'` first. Repeated setup preserves configuration. A downloaded ZIP does not require Git installation.

## Verify and continue

```powershell
.\Runtime\venv\Scripts\python.exe scripts/verify_onboarding.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\printlab.ps1 doctor
powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\printlab.ps1 context
```

Onboarding verification creates temporary Chinese-language projects and checks assignments, handoffs and the API through independent processes. Success reports `ok: true`. Sarah, Mike and task groups share one workspace; establish entry points and handoffs through the onboarding guide. Replace other guides' `./Harness/bin/printlab` with the PowerShell launcher above; subcommands/arguments remain the same.

## Install design and printing tools independently

Obtain Bambu Studio, Blender, Text-to-CAD, Bambuddy and optional modeling dependencies from their original upstream sources. Follow Windows-specific installation instructions and record actual versions/executable paths. See [sources](DEPENDENCIES.md), [Text-to-CAD](CAD_SETUP.md), [Bambuddy](BAMBUDDY_SETUP.md) and [Studio](STUDIO_SETUP.md).

Check `slicer_path`, `slicer_profiles_path`, `blender_path` and `cad_python` in `Runtime/config.json`. Setup searches PATH and Program Files for Studio/Blender. JSON paths may use forward slashes, such as `C:/Program Files/Bambu Studio/bambu-studio.exe`. Slicer profiles are normally under the installation's `resources/profiles`; verify the actual path.

If CadQuery export is needed, install independently in the local environment and verify a real export:

```powershell
.\Runtime\venv\Scripts\python.exe -m pip install cadquery trimesh numpy pillow
```

The MLX image-to-model route targets Apple Silicon. Choose and verify Windows alternatives according to their upstream instructions. Obtain model weights from their original authors.

## Printing through official Studio

The prepared page follows the route bound to the task. Supported `bambuddy_queue` combinations can use workbench sending, under `PRINTING.md` and current verification limits. For an official Studio package, use the following handoff. The dedicated Mac window helper still requires macOS.

1. Save the actual version, sliced package, device, plate, material mapping and usage in PrintLab; confirm the exact job and clear-plate state.
2. Use `studio-copy PROJECT_ID JOB_ID` to prepare the official Studio copy. Check the returned file/task record and current `--help`.
3. The user or an agent with desktop control opens that copy in official Studio and checks device, materials and options. Preserve approval for the exact file, send once, and record task name, file hash, time and receipt in the project Session.
4. Read device state and the receipt after that single send. Reconcile an unclear outcome before deciding what to do next.
5. Save first-layer, completion and physical-feedback evidence; continue the same project.

Setup independently downloads the pinned public file inspector. `doctor` performs real file inspection and reports missing dependencies/failures. Windows supports inspection, official send reservations and the workbench API. Bambuddy queue software checks are covered by the release's CI; physical sending still requires on-site verification. The Studio GUI helper remains Mac-only.

See [printing](PRINTING.md) for approval and receipt constraints. First connection to a real printer requires local device, slicing and dispatch verification.

## VM verification

Desktop VM verification runs setup, automated tests, independent-process handoffs and Chromium checks on GitHub-hosted Windows Server 2022, Windows Server 2025 and macOS. It saves results, logs and screenshots. These checks do not establish Windows 10/11 desktop, locally installed CAD/slicer integration or physical-print validation. See the release and [verification history](VERIFICATION.md) for specific results.
