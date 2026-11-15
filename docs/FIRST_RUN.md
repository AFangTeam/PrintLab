# First setup: understand the user's printer

The onboarding agent follows [resumable onboarding](ONBOARDING.md), reading existing configuration before asking questions. Discover devices and materials where possible; ask only for missing facts. Never fill gaps with the author's equipment configuration.

1. Mac or Windows? Can the agent run local commands, read/write files and control the desktop? Where should the persistent workspace live?
2. Exact printer model and firmware, installed nozzle diameter/type, plate, AMS count/connections, external spool and FTS configuration.
3. Owned material types, colors, specific products and loaded slots. Unknown remaining quantities stay unknown. Is dedicated support filament available?
4. Can the computer and printer communicate on the same network? Cloud or LAN Only? Are Studio/Bambuddy already in use? Must Handy cloud printing, account history and MakerWorld collections remain usable? Is the account on the mainland-China or international service?
5. Typical objects; dimension/strength/surface priorities; acceptance of extra accessories; multicolor time/material costs; support-material preferences.

Save device facts in `Library/Devices/X2D/device.json` (a legacy path, not an assumed model), tool versions/checks in `installed.md`, and preferences in `Context/profile.md`. Do not mark unknowns as verified. Keep IP addresses, access codes and API keys in restricted local configuration, not shared documents.

Each task group reads the same device/material records and rereads live status. Check current model/feeding support with `dispatch-plan` and `PRINTING.md`; the dedicated Mac Studio sending helper has a specific X2D/Studio scope, and eligible Bambuddy routes have their own constraints. Entering another model in the device card does not establish support. A1 external-spool automatic dispatch remains unadapted.

Record existing network mode, cloud login, synchronization and credential consumers. Preserve working features during installation. Explain concrete effects and obtain the user's choice before changing network mode or authorization scope. Check history/collection coverage using [sync troubleshooting](SYNC_TROUBLESHOOTING.md).

## Manufacturing decisions for each object

Establish purpose, critical dimensions and acceptance criteria first. For a new shape, use `Context/image-to-print.md` to select a concept and matching views. Protect functional interfaces under `Context/cad-master-design.md`; tests and finished parts share source geometry. Small changes retain confirmed decisions.

The final review compares orientation, part/plate splits, materials, supports, nozzle roles and color-change overhead, including all plates, startup, flushing, plate changes and post-processing. Prioritize quality and reliability; thinner walls or higher speeds do not replace engineering judgment. Dedicated supports depend on the actual feeding system, material compatibility and user preferences, not the author's dual-nozzle setup.

## Initial verification record

Record versions, real commands, results and gaps for the workbench, CAD, slicing, device reads and sending helper separately. Mark unexecuted steps as unverified and synthetic-device checks as simulated. Installation, modeling and verification do not authorize physical printing.
