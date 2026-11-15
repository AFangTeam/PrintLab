# PrintLab · Agent workspace guide

PrintLab targets Mac / Windows, Codex and Bambu Lab printers. Follow the user's current request. Verify the project state and facts, then choose the simplest viable method.

English is the primary language for maintained project instructions. Communicate in the user's preferred language; preserve original user statements, device UI labels and historical evidence. See `docs/LANGUAGE.md` for remaining Chinese content and migration boundaries.

## First installation

Read `docs/AGENT_START.md` for setup, verification and role creation. Installation details are in `docs/SETUP.md`, third-party sources in `docs/DEPENDENCIES.md`, and device support in `docs/PRINTING.md`. Within the user's authorization, obtain third-party tools independently from their original authors and record versions and verification results. Setup downloads workbench dependencies from PyPI/npm.

The workspace root is this checkout. The Mac CLI is `./Harness/bin/printlab`; Windows uses `Harness/bin/printlab.ps1`. Check current `--help` before choosing arguments. Continue existing models, environments and user configuration.

## Every handoff

1. Read `Context/profile.md`, `Context/workflow.md`, `Context/agent-policy.json`, `Context/taste.md` and `Library/Devices/X2D/device.json`. Some files exist only after initialization.
2. For the target project, read `project.json`, `brief.md`, `decisions.md` and the handoff referenced by `latest_session`. `printlab context PROJECT_ID` gathers the shared context.
3. Report the project, current version, confirmed choices, remaining uncertainties and next action.
4. Finish with `printlab handoff`, recording results, checks, problems and next steps. Use current command help.

## Roles and persistent records

Sarah handles devices, materials, faults and accessories. Mike maintains the workbench, tools and workflow. Each object has its own task group. Prompts are in `docs/ROLES.md`. Roles share files and commands; available models depend on the user's agent environment. Create chats or delegate to subagents only when the user explicitly requests it.

Initialization creates `Context/team.md` for the actual team description. Resumable onboarding, role entry points and readback evidence live in `Context/onboarding.json`. Follow `docs/ONBOARDING.md` to find existing chats, create missing Mike/Sarah roles and read back their real introductions and shared context. An existing Sara entry is the same role under its earlier name. When the installation request explicitly includes automatic team creation, proceed; record a specific pending task if the host lacks the capability. Project assignments remain in `Review/team.md`.

Append shared notes with `workspace note` and confirm devices with `workspace device`, supplying the current hash and rereading after conflicts. Register user-confirmed inventory through `material-intake` in Bambuddy. Before image generation, run `constraints capture PROJECT_ID` to preserve device, material and requirement sources. Before CAD or slicing, use `context` to check changes and update affected design records. Unknown facts remain unverified.

- `Context/`: workflow, preferences and lessons; preferences require explicit user feedback.
- `Project/`: requirements, source models, candidates, released versions, slices, receipts and physical reviews.
- `Library/`: the user's devices, material knowledge, inspiration and sources.
- `Templates/Project/`: templates for new projects.
- `Runtime/`: local configuration, credentials, caches and third-party environments.

User data and credentials stay local. Review staged changes before committing source; exclude real device information, chats and personal records.

## Design and printing

Follow `Context/image-to-print.md`: for a new shape, complete the two image selections before the actual model. Compare real model geometry with the chosen target. Check interfaces, tolerances, insertion paths, wall thickness and loads independently. Preserve editable sources; test pieces and finished parts share interface parameters, as described in `Context/cad-master-design.md`.

For final manufacture, review quality, reliability, total print time, supports, material changes and post-processing. Record actual slicing comparisons using `Templates/Project/Review/x2d-final-review.md`.

Printing approval binds the specific model version, sliced file, device, materials and current clear-plate evidence. Use the same task record through `printlab approve / submit / reconcile`. Installation, modeling, slicing and tests do not operate the device. Before sending, inspect existing tasks; reconcile an unknown outcome to avoid a duplicate print. Before configuring permissions, run `printlab dispatch-plan` with the confirmed model, feeding route and user choices. Evaluate Bambuddy first and recommend only the permissions it needs. Explain the effect of LAN Only / Developer Mode on cloud features and let the user choose. If permission is declined, the combination is unsupported or preflight fails, prepare the official Studio fallback described in `docs/PRINTING.md`; if Studio automation remains unavailable, hand off to manual sending. Unknown upload, queue or send results must be reconciled before changing routes. See `Context/official-studio-dispatch.md`.

After the device finishes, inspect the physical part. Record acceptance only after the user confirms fit, appearance, strength or actual use.

For Studio errors `noWindowsAvailable`, `timeoutReached` or `Computer Use is not active`, read `docs/STUDIO_COMPUTER_USE.md`. Attempt at most one lightweight window-recovery round, with one action per call. Reuse a correct existing slice; prefer a verified official CLI when slicing is needed. On Mac, the general `studio-bridge windows / recover / open-file / open-panel` commands can reach send preparation. Do not apply X2D final-send automation or an AMS queue route to an A1 without AMS / using Ext. Record manual handoff separately from automatic dispatch. Reconcile an unknown result rather than resending through another tool.

## Third-party sources and publishing

Follow `docs/DEPENDENCIES.md`. Obtain third-party code, skills, weights, author models, applications and plugins independently from their original projects, retaining author attribution and licenses. PrintLab's noncommercial license covers only its original code and documentation. Publishing a model is a separate user request: check each model's sources and permissions.

## Existing apps and account synchronization

Before setup, record the Handy, Studio, Bambu Cloud and MakerWorld features the user already relies on. Preserve logins, network mode and existing credential scopes. Create a dedicated read credential for PrintLab. If the user needs cloud features, explain the specific effects of LAN Only / Developer Mode and confirm the chosen route. Use `docs/SYNC_TROUBLESHOOTING.md` to check history/collection sources, coverage dates and continued operation of existing apps. Importing old account history and MakerWorld account collections remains outside the current scope. Recover missing archive images with `printlab history-recover` as described in `docs/PREVIEW_RECOVERY.md`, recording sources and counts.
