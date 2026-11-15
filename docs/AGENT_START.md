# Taking over PrintLab from GitHub

## Goal and available capabilities

Give the user a persistent workbench, shared records, clear roles and projects that continue across sessions. First confirm that the agent can read GitHub, run a local terminal and read/write the target directory. Record browser/desktop control, image generation, CAD viewing and chat-management capabilities only if the current host actually exposes them.

When the user supplies this repository and asks for installation, read the README and AGENTS first. Complete authorized setup, software checks and repairs using the steps below. For account login, credential authorization, system-permission choices, physical measurement or loading material, give concrete instructions and continue after obtaining the real result.

Paths are relative to the repository root. Use one persistent local workspace. Replace example project IDs with IDs actually returned by commands. Communicate in the user's preferred language; some detailed references and the workbench UI remain Chinese, as documented in [language coverage](LANGUAGE.md).

## Download and install

Identify the OS first. On Windows, install with `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1` and start with the same invocation of `scripts/start.ps1`. In Bash examples below, replace `./Harness/bin/printlab` with `powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\printlab.ps1`, and `Runtime/venv/bin/python` with `Runtime/venv/Scripts/python.exe`. See the [Windows guide](WINDOWS.md).

1. Inspect the current directory and existing installations. Continue an existing workspace. For a new installation, use the user's chosen path; `~/PrintLab` is a possible default, but inspect any existing directory before using it.
2. Clone `https://github.com/AFangTeam/PrintLab.git` or download `PrintLab.zip` from an explicit release. Point the agent workspace at the actual repository root.
3. Check `python3 --version`, `node --version` and `npm --version`. Python 3.11+ and Node.js 22+ are required. If the system interpreter is too old, set `PRINTLAB_PYTHON` to a suitable installed interpreter. Obtain missing runtimes from official sources.
4. Run `bash scripts/setup.sh` on Mac or the Windows equivalent. Expect a virtual environment, `Harness/studio/dist/index.html`, local configuration and `Context/team.md`.
5. Run onboarding verification below. It uses temporary workspaces and real CLI subprocesses to check project creation, assignments, handoffs, rereading and the API. The final JSON must report `ok: true`.

```bash
Runtime/venv/bin/python scripts/verify_onboarding.py
./Harness/bin/printlab doctor
./Harness/bin/printlab context
```

A tool-path existence check only establishes that a file exists. Also exercise each tool's actual help and smallest useful operation. The first `context` result should have no `missing` entries; device and material fields may remain unconfigured.

## Start and inspect the workbench

Run `bash scripts/start.sh` in a separate terminal or a persistent process supplied by the host. Open `http://127.0.0.1:8018`. If the port is occupied, identify the existing service first; a separate workspace can use `--port 18018`.

Check that `/api/health` returns `ok: true` and the overview, project gallery, library and device pages render. An empty workspace should show an unconfigured device. Give the user the URL and launch command. The page remains available while the service runs; restart it after the terminal exits.

## Device and preference setup

Complete the [first-run interview](FIRST_RUN.md), recording confirmed facts in the shared device card and user preferences. Task groups read the same records; never substitute the author's printer configuration.

## Create the team

Follow [resumable onboarding](ONBOARDING.md): inspect host capabilities, find existing chats, reserve missing roles, call real host creation tools and read back the first introductions. When automatic team creation is part of the user's request, the main agent performs it. Use Sarah and Mike for new roles; continue an existing Sara entry. See [role prompts](ROLES.md).

The workbench's configuration/team page displays actual introductions, shared records and pending work. `Context/onboarding.json` stores creation evidence, while `Context/team.md` retains the user's team description. Both roles reuse answers already collected by the main agent and ask only for missing facts.

## Create a real project and assignments

Use `./Harness/bin/printlab status` to find an existing object before creating another. Continue its ID if present. For a new object, establish purpose, critical dimensions, appearance and acceptance criteria; unknowns remain open.

```bash
./Harness/bin/printlab new 'Desk headphone hook' --kind functional --brief 'Hang headphones; desk thickness and load need user measurement' --summary 'Desk hook: establish requirements first'
```

After the command returns an ID, run `./Harness/bin/printlab context PROJECT_ID`. Use the returned `documents[].path` values to locate and fill:

- `brief.md`: requirements, known conditions and open questions.
- `decisions.md`: actual decisions and their sources.
- `Review/team.md`: coordinator, Sarah's materials/accessories work, Mike's tool work, outputs and handoffs.
- `Context/team.md`: the object's task-group chat entry point.

Refresh the gallery and verify the project and requirements are visible. Creating its chat requires the user's request or explicit authorization within team setup. A suitable title is “Task group · Object name”.

## Save and verify handoffs

At the end of a session, use facts from that session:

```bash
./Harness/bin/printlab handoff PROJECT_ID --note 'Roles, current version, completed work, evidence, user decisions, open issues, next steps and relevant paths'
./Harness/bin/printlab context PROJECT_ID
```

Confirm that the result includes the handoff and `Review/team.md`. The next agent uses the same workspace and project ID, reads `context` and follows `latest_session`. The current coordinator maintains the official project version; collaborators use separate candidate directories and recheck sources and outputs at integration.

## Connect design and printing tools

Read [dependencies and sources](DEPENDENCIES.md) and current upstream installation instructions. Install independently from original authors within the user's authorization. Record each tool's version, real entry point, verification result and remaining work.

| Capability | Prerequisites | Minimum verification |
| --- | --- | --- |
| Concepts and selection | Available image-generation tools or user references | Generate/read images and preserve selection evidence |
| CAD and previews | Text-to-CAD and a suitable CadQuery/Blender environment | Actual export, units/dimensions and preview |
| Materials and devices | Independent Bambuddy, user equipment and API credentials | `status` and `materials` return the correct device and sources |
| Final slicing | Official Bambu Studio and local profiles | Actual slice, plate/material mapping and time/usage checks |
| Sending helper | Supported printer/Studio, helper and system permissions | Actual `studio-bridge capability` result |

Before a new shape, read `Context/image-to-print.md`. Initialize the project's selection record from `Templates/Project/Review/design-target.json`, with real images, hashes and choices. Read model preferences from `Context/agent-policy.json`; if unset, use models currently available to the user and record the actual executor.

Follow [setup](SETUP.md) for first device connections. Actual printing must bind the exact file, device, materials and clear-plate confirmation under [printing instructions](PRINTING.md).

## Deliver the workspace

Report the actual workspace path, workbench URL and restart command, created role entry points, project ID and current stage. Separately report verification of the workbench, continuation, images, CAD, slicing, device reads and printing. Give concrete next actions for missing capabilities. Evidence includes real command results, rendered pages, files and handoff content.

See [connections and control](CONNECTIONS.md) for phone/computer/agent routes, and [CAD setup](CAD_SETUP.md) for pinned Text-to-CAD versions, Mac/Windows commands, host integration and a minimal modeling check.

## Existing apps and account synchronization

Record the Handy, Studio, Bambu Cloud and MakerWorld features already in use. Preserve logins, network modes and existing credential scopes; create a dedicated read credential for PrintLab. Explain LAN Only / Developer Mode effects before a user who needs cloud features selects a route. Use [sync troubleshooting](SYNC_TROUBLESHOOTING.md) to check actual sources, coverage dates and existing-app functionality. Importing old account history and MakerWorld account collections remains outside the current scope. Recover missing archive images using `printlab history-recover` and [preview recovery](PREVIEW_RECOVERY.md), recording sources and counts.
