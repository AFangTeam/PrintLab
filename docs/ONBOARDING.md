# First setup and interruption recovery

The main agent handles initial setup; Mike and Sarah continue the same workspace. Complete installation/startup in `AGENT_START.md`, then run `printlab onboarding status --refresh`. The returned `version` prevents concurrent sessions from overwriting onboarding progress. Replace every example version, hash, ID and path with an actual readback value. Windows uses `Harness/bin/printlab.ps1`.

## Reuse existing answers

Read `printlab context`, `Context/team.md` and existing host chats first. If the workspace already contains an answer, record progress with the original source. Ask the user only for missing facts. Inspect the OS, available tools and server-side printer list directly.

Collect three topics for this installation, saving each with `onboarding answer`. Preserve the user's original words in shared records.

```bash
./Harness/bin/printlab onboarding answer usage_goals --text 'Actual user goals' --source 'User message or confirmed document location' --expect 0
./Harness/bin/printlab onboarding answer cloud_needs --text 'Existing Handy, Studio and cloud needs' --source 'Actual source' --expect 1
```

After connecting, ask about other owned spools. Read back inventory additions before saving `additional_materials`, including actual spool IDs or additions still pending. Use the new version returned after every write. Handle network choices under `CONNECTIONS.md`.

## Recommend permissions and retain a fallback

Check the model and feeding route against [printing routes](PRINTING.md#默认发送路线与后备方案). Run `printlab dispatch-plan --model MODEL --feeding ams` or use `--feeding external`, based on confirmed facts. If supported, recommend the required Bambuddy write permissions and explain LAN Only / Developer Mode effects on existing cloud features. If the user declines or the combination is unsupported, prepare Studio directly; granting control permissions is not a condition of completing installation.

Record the user's choice, specific missing capabilities and fallback. Do not repeatedly ask about permissions already decided. If Studio automation is unavailable, recommend the relevant system permissions; if it still cannot work, hand off the exact sliced package for manual sending. Configuration and permission checks do not start a print.

## Verify devices and filament

Connect the printer in the user's independent Bambuddy service. Credentials belong in `Runtime/private/bambuddy.json`; see `BAMBUDDY_SETUP.md`. Read existing service configuration first. Device discovery uses read-only APIs.

```bash
./Harness/bin/printlab onboarding discover
./Harness/bin/printlab workspace connection
./Harness/bin/printlab workspace connect --url http://127.0.0.1:8017 --printer-id 1 --expect-sha CURRENT_CONFIG_HASH
./Harness/bin/printlab workspace show device
./Harness/bin/printlab onboarding adopt-device --expect-sha CURRENT_DEVICE_HASH
./Harness/bin/printlab status
./Harness/bin/printlab materials
```

If exactly one device matches the user's description, it can be adopted directly. Ask for the target if several are plausible. `adopt-device` records real identity and readback time while retaining user-confirmed fields. The legacy `Library/Devices/X2D/device.json` path can describe the user's own model. Resolve identity conflicts against the previous record and new choice.

Use installed official Studio profiles and actual equipment to check build space, nozzle, plate and feeding connections. Distinguish optional profile capabilities from physically installed hardware. Add user-confirmed facts with `workspace device --file confirmed-fields.json --source SOURCE --expect-sha CURRENT_HASH`.

```bash
./Harness/bin/printlab workspace profiles --model MODEL
./Harness/bin/printlab workspace profile --name 'Exact preset name returned above' --expect-sha CURRENT_DEVICE_HASH
```

This reads inheritance/includes from installed official profiles and preserves source hashes. Build space comes from the actual profile; the installed nozzle still requires device readback or user confirmation. Changed source profiles after a Studio update trigger a recheck in project constraints.

```json
{"user_confirmed":{"model":"Actual model","build_plate_description":"Actual installed plate"}}
```

Read loaded materials from live status. Other owned spools belong in Bambuddy inventory. After the user confirms ownership, use `material-intake` for material, brand, series, color, product code, storage and known nominal label grams. It needs `inventory:read` and `inventory:update`. Identify missing permissions without modifying other apps' credentials.

```json
{"material":"PLA","brand":"User-confirmed brand","color_name":"White","storage_location":"Filament cabinet"}
```

```bash
./Harness/bin/printlab material-intake --file spool.json --source 'Original ownership confirmation and source' --request-id STABLE_SPOOL_REQUEST_ID
```

Check whether the same physical spool already exists. Two real spools require separate records; similar appearance does not make them one spool. Reuse the request ID after timeouts or interruptions so the command can find its previous marker. Keep an unclear result pending reconciliation. Unknown remaining mass stays unknown; label mass is an accounting estimate only.

## Create two independent chats

Inspect the host's actual tools and write a capability JSON. Mark a capability `true` only when it is exposed and usable.

```json
{
  "name":"Actual host",
  "capabilities":{"local_files":true,"terminal":true,"chat_create":true,"chat_read":true},
  "evidence":"Actual tool names, parameter help and workspace readback"
}
```

```bash
./Harness/bin/printlab onboarding host --file host.json --expect CURRENT_VERSION
```

Handle Mike and Sarah in sequence. Sara is Sarah's earlier name. Search and read existing chats by the actual workspace and check historical entries in `Context/team.md`.

1. For a matching existing chat, read its workspace, actual ID and first introduction. Register the receipt below with `--adopt-existing`. If the introduction is insufficient, send the complete first task to that chat and wait for its reply.
2. For a missing role, run `onboarding reserve-role Mike --request-id STABLE_CREATION_ID --expect CURRENT_VERSION`. Only the executor receiving `create_allowed: true` creates it.
3. The main agent calls the real host creation tool with the returned `role.prompt` as the first task and the same absolute workspace. Add the user's requested response language without dropping required steps. For Codex, follow the current tool's `prompt` and actual project-target parameters. The CLI itself cannot create chats.
4. Record the final real thread ID. A temporary client ID, title or plan text alone is insufficient evidence.
5. Wait for and read back the role's reply and file-reading record; add the actual `first_reply` and `context_paths`. The workbench shows the introduction after the state reaches `introduced`.
6. Use hash-checked `workspace note team` to preserve entry points and verification. `onboarding.json` stores machine-readable state; the team document stores explanations and handoff history.

```json
{
  "request_id":"Same ID used for reservation",
  "thread_id":"Actual host thread ID",
  "host_id":"Actual host and local environment",
  "workspace":"Same absolute root as the main chat",
  "source":"Location of host creation and readback evidence",
  "first_reply":"Actual reply, unchanged",
  "context_paths":["AGENTS.md","Context/profile.md","Context/workflow.md"]
}
```

```bash
./Harness/bin/printlab onboarding record-role Mike --file role-receipt.json --expect CURRENT_VERSION
```

Repeat for Sarah. After an interruption, `creating` prevents duplicate creation; search the host using the saved request ID and workspace, then register the recovered result. If host tools are absent, show the concrete pending work and provide prompts/workspace path for continuation in a capable host.

## Shared facts and the first object

Only after the host explicitly reports creation failure and a search by creation ID confirms no result, release an unbound reservation with `onboarding release-role ROLE --request-id ORIGINAL_ID --evidence 'Host error and search evidence' --expect CURRENT_VERSION`. This cannot release a binding that already has a thread ID. Continue querying the host while the outcome remains unknown.

Mac's `Harness/bin/printlab` is an executable shell launcher; Windows uses the PowerShell launcher. They select the installed environment. Direct Python entry points are `Runtime/venv/bin/python -m printlab.cli` and `Runtime/venv/Scripts/python.exe -m printlab.cli` respectively.

Read a document hash with `workspace show NAME`, then append preferences, lessons or team descriptions with `workspace note NAME --text TEXT --source SOURCE --request-id STABLE_UPDATE_ID --expect-sha CURRENT_HASH`. Supported names are `profile`, `taste`, `lessons` and `team`; use `missing` if no content exists. Reread/merge after conflicts and reuse the request ID for the same update.

Offer a small number of simple object directions based on user goals, materials and equipment. After selection, find the existing project or create a stable ID; record requirements and confirmed dimensions. Capture device/material constraints before image generation and reread changes before CAD/slicing.

```bash
./Harness/bin/printlab constraints show PROJECT_ID
./Harness/bin/printlab constraints capture PROJECT_ID --source 'Current requirements and device/material verification' --expect-sha missing
./Harness/bin/printlab context PROJECT_ID
```

`manufacturing_context` returns current facts, saved snapshots, missing fields and sources of change. Materials include inventory not loaded in AMS; read loading separately from live device state. When offline, retain the last inventory with its timestamp. Snapshot updates preserve history. Record purpose, measured dimensions and protected interfaces in `brief.md`; keep concept/three-view choices in `design-target.json`; connect editable geometry through Text-to-CAD as described in `CAD_SETUP.md`.

Final checks compare the real model with selected images, dimensions/walls/assembly, material suitability, the actual plate and feeding route. Read `PRINTING.md` and local capability results for slicing/dispatch support. Specific prints retain unified approval and receipt records.
