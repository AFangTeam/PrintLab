# Install PrintLab

Use the [Windows guide](WINDOWS.md) on Windows. The commands below target Mac.

## Prerequisites

macOS 14+, Python 3.11+, Node.js 22+ (including npm), Git and an agent with local terminal/filesystem access. Install the workbench first, then add modeling and device connections individually. Original-author links are listed in `DEPENDENCIES.md`.

## Install the workbench

```bash
git clone https://github.com/AFangTeam/PrintLab.git
cd PrintLab
bash scripts/setup.sh
bash scripts/start.sh
```

Open <http://127.0.0.1:8018>. The service stops when its terminal exits. If port 8018 is occupied, identify the existing service to avoid two workbenches writing the same records. A separate workspace can use `bash scripts/start.sh --port 18018`. Setup creates a local Python environment, downloads workbench dependencies from PyPI/npm, builds the web application and initializes empty local configuration.

If Python is too old, install Python 3.11+ and run `PRINTLAB_PYTHON=/path/to/python3 bash scripts/setup.sh` with the actual interpreter path. After setup, run `./Harness/bin/printlab doctor`.

## Let the agent take over

See the [user interaction guide](GETTING_STARTED.md) and [agent onboarding guide](AGENT_START.md) for actions and completion criteria. The workbench UI is currently Chinese; [language coverage](LANGUAGE.md) distinguishes translated instructions from remaining UI/reference work.

Open this repository in Codex and use the README's installation prompt. Fill actual goals/preferences into `Context/profile.md`, choose an available model and record model preferences in `Context/agent-policy.json`. See `ROLES.md` for role prompts.

Create an empty project, then use the actual returned ID in the second command:

```bash
./Harness/bin/printlab new 'My first object' --kind functional --brief 'Describe purpose, dimensions and acceptance criteria'
./Harness/bin/printlab context P001
```

## Connect Bambuddy and a printer

Complete the [first-run interview](FIRST_RUN.md). Independent installation, URLs, read permissions and API checks are described in [Bambuddy setup](BAMBUDDY_SETUP.md).

1. Install Bambuddy independently from its original project, start it using upstream instructions and add the user's printer. It manages connections, inventory and history.
2. Create a read-only API key in Bambuddy and obtain its printer ID. Store the key as `read_api_key` in `Runtime/private/bambuddy.json`, with mode 600 on Mac. Configure a properly scoped `write_api_key` only when actual sending is needed.
3. Set `bambuddy_url` and `printer_id` in `Runtime/config.json`. The default URL is `http://127.0.0.1:8017`; use the actual service address.
4. Update `Library/Devices/X2D/device.json`, checking model, nozzle, plate, AMS/external feeding and FTS. This legacy path does not mean the user owns an X2D; the record must describe their actual printer.
5. Run `./Harness/bin/printlab status` and `./Harness/bin/printlab materials`. Verify identity, current state and material mappings; save results in `Library/Devices/X2D/installed.md`.

An agent with local terminal access can perform authorized downloads, setup, configuration checks and repairs. Account login, credential authorization, macOS permission choices and physical loading require the user's real action or choice; read back the result before continuing.

Keep API keys in restricted local files, never public issues or logs. PrintLab accesses the independently running Bambuddy service through its HTTP API; data remains under the user's local management.

## Install modeling and slicing tools

- **Text-to-CAD:** Install the Codex plugin independently using its original project's instructions. Verify current help, modeling, export and the CAD viewer before starting a real object. `Harness/bin/text2cad` calls an installed `cad` or `cadgen`; `PRINTLAB_CAD_COMMAND` can select an executable.
- **CadQuery export:** To use PrintLab's `build --engine cadquery`, independently install `cadquery`, `trimesh`, `numpy` and `pillow` in the local environment: `Runtime/venv/bin/python -m pip install cadquery trimesh numpy pillow`. Record actual versions in the project's tool record.
- **Blender:** Install from the official source. `blender_path` defaults to `/Applications/Blender.app/Contents/MacOS/Blender` in `Runtime/config.json`.
- **Bambu Studio:** Install from its official source, log in and connect the user's device. `slicer_path` defaults to `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio`. Read slicing profiles from this local installation.

See [Studio setup](STUDIO_SETUP.md) for paths, profile parsing and offline slicing checks. After tools are ready, run `doctor` and verify real dimensions, units, export and preview in a temporary project. Current build engines are CadQuery/Blender. A Text-to-CAD STEP can pass through the matching CadQuery export path; retain source scripts and inputs.

## Optional Mac window

With Xcode Command Line Tools installed, run `zsh Harness/macos/build.sh` to create `Runtime/macos-build/PrintLab.app`. Move it to your applications directory if desired. It uses the local port-8018 workbench, so keep `scripts/start.sh` running. Rebuild after moving the workspace because the app records its actual path.

## First print

Follow `PRINTING.md` item by item. The workbench's Studio sending helper requires an independent build plus accessibility/screen-reading permissions granted by the user. Set `studio_printer_name` to the exact device name in the user's Studio; sending also checks the serial-number match. Setup itself does not authorize printing.

## Updates and backups

See [upgrading](UPGRADING.md) for backup verification and rollback. Save local projects/configuration first. Use `python3 Harness/backup.py backup --help` for current options; backups include private configuration and belong in a restricted local directory. After updating Git source, rerun setup; initialization preserves existing configuration and records. Recheck interfaces and slicing behavior after third-party updates.

See [connections and control](CONNECTIONS.md) and [CAD setup](CAD_SETUP.md) for detailed integration routes and modeling checks.
