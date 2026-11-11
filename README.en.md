# PrintLab

English · [简体中文](README.md)

Turn an idea into something you can hold.

PrintLab is the 3D-printing workbench and collaboration workflow AFang (Eric) uses in his E41 video. It is designed for **Mac + Codex + Bambu Lab printers**. Describe what you want to make, then work with Codex on the design, CAD, slicing comparisons, materials, print records, and physical feedback in one workspace.

## Get started

Open this repository in Codex and send it this prompt.

> Read AGENTS.md and docs/SETUP.md, then help me install PrintLab on this Mac. Confirm my printer model, nozzle, build plate, and available filament. Install third-party tools independently from their original projects using docs/DEPENDENCIES.md. Start the workbench first, then verify the printer connection and modeling capabilities. Report which functions you have actually verified.

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

The detailed installation and workflow reference pages are currently in Simplified Chinese. [Installation guide](docs/SETUP.md)

## Three collaboration roles

- **Sara, 3D-printing advisor** helps track equipment, filament, common problems, and parts. Shopping lists span projects. Adding products to a shopping cart uses Codex browser capabilities after the user authorizes it.
- **Mike, workflow designer** maintains tool connections, the workbench, and shared procedures. Mike handles installation, versions, interfaces, and workflow problems.
- **Task group, named after the object** gives each object its own chat and project. Requirements, selected references, source models, slices, and feedback stay together for later sessions.

PrintLab provides context through files and commands. Available models and tools depend on the user's Codex installation. Copy the role prompts to start your own chats. [Role prompts](docs/ROLES.md)

## The workbench

- Project gallery, 3D model previews, and design revisions.
- Device status, filament inventory, and captured print history from Bambuddy.
- Reference collections, personal preferences, and image-selection records.
- Shared parts lists, stock, and purchasing records.
- Prepared print packages, material mappings, estimates, task-specific confirmations, and execution receipts.

A fresh installation starts with an empty project collection and an unconfigured printer. Data appears as you connect your own equipment and create projects.

## From idea to physical result

Purpose and dimensions → choose a shape → confirm three views → build CAD → compare revisions → choose colors and materials → compare slices → confirm the exact print → record physical feedback.

For a new shape, the default workflow first selects one concept image, then one of four three-view sets derived from that concept. Small revisions are handled according to their impact, using existing decisions. Text-to-CAD provides modeling and viewing capabilities. Dimensions, interfaces, and assembly still require checks. [Full workflow](Context/workflow.md)

## Supported environment

Requires macOS 14+. Apple Silicon is recommended. The general workbench runs independently. Device status and print history use a separately installed Bambuddy service.

The automated sending helper targets **X2D, Chinese Bambu Studio 02.08.02.61, 0.4 mm, one main AMS filament, the left main nozzle, and one Textured PEI plate**. Other printers, software versions, and multi-material routes need verification in the user's environment. [Printing and compatibility](docs/PRINTING.md)

This repository contains the workbench source, original workflow documents, role prompts, and empty project templates. Obtain third-party projects, model weights, Bambu applications, and plugins independently from their original authors. Your own objects live in the local `Project/` directory. [Third-party dependencies](docs/DEPENDENCIES.md)

## Development and verification

```bash
Runtime/venv/bin/python -m pytest Harness/tests -q
node --test Harness/tests/native-inspection.test.mjs
cd Harness/studio && npm run build
```

Tests use temporary workspaces and synthetic devices. Read-only integration tests for installed equipment require an explicit `PRINTLAB_LIVE_TEST=1` opt-in. The release verification record documents completed checks, skipped tests, and remaining physical validation. [Verification record](docs/VERIFICATION.md)

## License and attribution

PrintLab-authored source and documentation use **PolyForm Noncommercial 1.0.0**. Use, modification, and redistribution are permitted for the noncommercial purposes defined by that license. Redistribution must include the license terms and required attribution from `NOTICE.txt`. Commercial use requires separate authorization from AFangTeam.

Original author is **AFangTeam / 阿方 (Eric)**. Independently installed third-party software retains its own license. [License](LICENSE.md) · [Required notices](NOTICE.txt) · [Project](https://github.com/AFangTeam/PrintLab)
