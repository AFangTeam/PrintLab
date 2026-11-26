# PrintLab

English · [简体中文](README.zh-CN.md)

Turn an idea into something you can hold.

PrintLab is the 3D-printing workbench and collaboration workflow AFang (Eric) uses in his E41 video. It is designed for **Mac / Windows + Codex + Bambu Lab printers**. Describe what you want to make, then work with Codex on the design, CAD, slicing comparisons, materials, print records, and physical feedback in one workspace.

## Watch PrintLab in use

[![PrintLab demonstration by AFang EricFang: ChatGPT meets a 3D printer (Chinese audio)](https://i.ytimg.com/vi/q7G8J5Tz0aQ/hqdefault.jpg)](https://www.youtube.com/watch?v=q7G8J5Tz0aQ)

[Watch on YouTube](https://www.youtube.com/watch?v=q7G8J5Tz0aQ) · [Watch on Bilibili · 阿方EricFang](https://www.bilibili.com/video/BV1r1W26hEHg/)

By AFang EricFang. Video language: Chinese. For current dispatch capabilities, use this README and the printing guide.

> **Acknowledgments and project roles:** Thank you to [Text-to-CAD](https://github.com/earthtojake/text-to-cad) for CAD modeling and viewing tools, [Bambuddy](https://github.com/maziggy/bambuddy) for printer status, filament and print-record management, and [Bambu Studio](https://github.com/bambulab/BambuStudio) for slicing and official print submission. PrintLab contributes the workbench, collaboration workflow and adapters. These third-party tools are maintained by their respective authors, installed independently from their original projects, and governed by their own licenses. See [third-party sources and licenses](docs/DEPENDENCIES.md).

## Get started

On first launch, open **项目图册** (Projects). The gallery is empty and the printer is unconfigured until you add your own.

Give the repository URL and this prompt to Codex or another agent with local terminal and filesystem access.

> Install https://github.com/AFangTeam/PrintLab on this computer. Read README.md, AGENTS.md, and docs/AGENT_START.md. Create a persistent workspace, start the workbench, and run the onboarding verification. Create Sarah, the 3D-printing advisor, and Mike, the workflow designer, as chats sharing this workspace, and record their actual setup status. Create a task-group chat when I choose my first object. Install third-party tools independently from their original projects. Tell me the specific actions needed for device information, login, or system permissions. Report the workspace path, workbench URL, role entry points, verified results, and next steps.

The repository includes a [PrintLab skill](.agents/skills/printlab/SKILL.md) and a [first-run checklist](docs/FIRST_RUN.md). The interaction guide explains what happens in chat, what happens in the web workbench, and how roles exchange project context. The agent guide provides executable setup steps and completion checks. [User interaction guide](docs/GETTING_STARTED.md) · [Agent onboarding guide](docs/AGENT_START.md)

For a manual installation, prepare Python 3.11+ and Node.js 22+, then run the following commands.

```bash
git clone https://github.com/AFangTeam/PrintLab.git
cd PrintLab
bash scripts/setup.sh
bash scripts/start.sh
```

Open <http://127.0.0.1:8018>. Setup creates an empty workspace and local configuration. Running it again preserves existing settings. If the system Python is too old, select an interpreter with `PRINTLAB_PYTHON=/path/to/python3 bash scripts/setup.sh`.

You can also download `PrintLab.zip` from a release. Extract it and open the resulting `PrintLab/` folder in Codex, or use these commands. [Latest release](https://github.com/AFangTeam/PrintLab/releases/latest)

```bash
curl -fL -o PrintLab.zip https://github.com/AFangTeam/PrintLab/releases/latest/download/PrintLab.zip
unzip PrintLab.zip
cd PrintLab
bash scripts/setup.sh
bash scripts/start.sh
```

[Installation guide](docs/SETUP.md) · [Language coverage and contribution policy](docs/LANGUAGE.md)

On Windows, install Python 3.11+ and Node.js 22+, open PowerShell in the repository folder, and run these commands.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

The Windows guide covers tool paths, verification, and official Studio handoff. [Windows guide](docs/WINDOWS.md)

**Language coverage:** The workbench UI is currently in Chinese. The default README, installation and core agent collaboration guides are in English; some detailed references and project templates remain in Chinese. Your agent can explain them in your preferred language. [Language policy](docs/LANGUAGE.md)

## Three collaboration roles

- **Sarah, 3D-printing advisor** helps track equipment, filament, common problems, and parts. Shopping lists span projects. Adding products to a shopping cart uses Codex browser capabilities after the user authorizes it.
- **Mike, workflow designer** maintains tool connections, the workbench, and shared procedures. Mike handles installation, versions, interfaces, and workflow problems.
- **Task group, named after the object** gives each object its own chat and project. Requirements, selected references, source models, slices, and feedback stay together for later sessions.

PrintLab provides context through files and commands. Available models and tools depend on the user's Codex installation. Copy the role prompts to start your own chats. [Role prompts](docs/ROLES.md)

## The workbench

- Project gallery, 3D model previews, and design revisions. Open a project and choose **删除项目** to delete its local folder, prepared entries, and shopping requirements. The workbench shows the project name and ID before asking for permanent deletion.
- Device status, filament inventory, and captured print history from Bambuddy.
- Reference collections, personal preferences, and image-selection records.
- Shared parts lists, stock, and purchasing records.
- Prepared print packages, material mappings, estimates, task-specific confirmations, and execution receipts.

## History and collection coverage

PrintLab shows print history already captured by Bambuddy and locally maintained inspiration collections. Importing older Bambu Cloud history and MakerWorld account collections is outside the current scope. Preserve existing Handy and cloud needs when choosing a connection mode. Missing archive thumbnails can be recovered from Mac Studio caches or explicitly linked local PNG/3MF files using `history-recover`. [Sync limits](docs/SYNC_TROUBLESHOOTING.md) · [Preview recovery](docs/PREVIEW_RECOVERY.md)

## From idea to physical result

Purpose and dimensions → choose a shape → confirm three views → build CAD → compare revisions → choose colors and materials → compare slices → confirm the exact print → record physical feedback.

For a new shape, the default workflow first selects one concept image, then one of four three-view sets derived from that concept. Small revisions are handled according to their impact, using existing decisions. Text-to-CAD provides modeling and viewing capabilities. Dimensions, interfaces, and assembly still require checks. [Full workflow](Context/workflow.md)

## Supported environment

Mac requires macOS 14+, with Apple Silicon recommended. Windows provides native PowerShell setup, command-line tools, and the browser workbench. The general workbench runs independently. Device status and print history use a separately installed Bambuddy service.

The Mac automated sending helper targets **X2D, Chinese Bambu Studio 02.08.02.61, 0.4 mm, one main AMS filament, the left main nozzle, and one Textured PEI plate**. Other printers, software versions, and multi-material routes need verification in the user's environment. [Printing and compatibility](docs/PRINTING.md)

v0.4.3 adds the offline `dispatch-plan` command to assess the model and feeding route before recommending permissions. Supported A1, A1 mini, P1S and X1 Carbon AMS combinations prefer the Bambuddy queue on Mac or Windows; actual device acceptance still requires on-site validation. Declined permissions, cloud-preserving choices or unsupported combinations use official Studio with manual handoff if automation is unavailable. **PrintLab A1 external-spool automatic dispatch is not yet adapted.** Unknown send outcomes require reconciliation before any route change.

The dedicated Studio GUI helper is macOS-only. Windows users can use an eligible Bambuddy queue route or hand prepared files to official Studio. Setup independently downloads the pinned public file inspector on both systems, and `doctor` exercises it with a disposable file. Complete the printer and material questionnaire before creating a design. [First-run questionnaire](docs/FIRST_RUN.md) · [Connections](docs/CONNECTIONS.md)

The repository includes a PrintLab Agent Skill at `.agents/skills/printlab/SKILL.md`. Open this workspace in a compatible agent and verify that it discovers the skill. Text-to-CAD is installed separately, with pinned-version commands and a modeling smoke test in the CAD guide. [CAD setup](docs/CAD_SETUP.md)

This repository contains the workbench source, original workflow documents, role prompts, and empty project templates. Obtain third-party projects, model weights, Bambu applications, and plugins independently from their original authors. Your own objects live in the local `Project/` directory. [Third-party dependencies](docs/DEPENDENCIES.md)

## Development and verification

```bash
Runtime/venv/bin/python scripts/verify_onboarding.py
Runtime/venv/bin/python -m pytest Harness/tests -q
node --test Harness/tests/native-inspection.test.mjs
cd Harness/studio && npm run build
```

Tests use temporary workspaces and synthetic devices. Read-only integration tests for installed equipment require an explicit `PRINTLAB_LIVE_TEST=1` opt-in. The release verification record documents completed checks, skipped tests, and remaining physical validation. [Verification record](docs/VERIFICATION.md)

## License and attribution

PrintLab-authored source and documentation use **PolyForm Noncommercial 1.0.0**. Use, modification, and redistribution are permitted for the noncommercial purposes defined by that license. Redistribution must include the license terms and required attribution from `NOTICE.txt`. Commercial use requires separate authorization from AFangTeam.

Original author is **AFangTeam / 阿方 (Eric)**. Independently installed third-party software retains its own license. [License](LICENSE.md) · [Required notices](NOTICE.txt) · [Project](https://github.com/AFangTeam/PrintLab)
