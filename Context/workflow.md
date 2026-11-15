# From an idea to a physical object

## Handoff and requirements

Read local preferences, the device card and the target project's latest handoff. Run `printlab context` and read current materials. Each object uses a stable project ID. Record purpose, measured dimensions, available accessories, protected interfaces, appearance and acceptance criteria in `brief.md`; record choices and changes in `decisions.md`.

After the user chooses to make the object, use `printlab shop confirm / sync` to collect nonprinted components in the shared shopping list. Check specifications, quantities, stock and the author's instructions. The user decides purchases.

## Shape and spatial interpretation

For a new shape, generate comparable single-image concepts. The user selects one; then provide four sets of front, right and top views of that same design and let the user select a complete set. Save images, hashes, prompts, choices and key features. Resolve inconsistent views before proceeding. A low-detail spatial draft can clarify occlusion when needed. See `image-to-print.md`.

## Actual modeling

Text-to-CAD/build123d can support parametric structures and interfaces; continue existing CadQuery sources, and use Blender where appropriate for organic surfaces. Export views from real geometry and compare them with the selected target. Label assumed dimensions and check critical fits first. Selecting an image confirms the intended appearance only.

Retain the master script, parameters, inputs, sources, millimeter units and export records. Test pieces and finished parts use the same interface geometry. Rebuild affected outputs after changing shared parameters. See `cad-master-design.md`.

## Colors and final manufacture

Read current materials and actual loaded slots. Plan colors, part splits and surfaces using the user's choices. Evaluate orientation, support contact, color changes, nozzle roles and total time. Actually slice promising alternatives before choosing. See `x2d-final-review.md`.

Deliver editable sources, geometry 3MF, the official Bambu project, sliced package and source records, clearly identifying each file's purpose. Read Bambu profiles from the user's installed official Studio and check the actual printer, nozzle, plate, material and AMS mapping.

## Preparation and printing

Tasks that are not yet being printed may enter the prepared list with their version, materials, accessories, estimated time and usage. Before starting, check live device state and existing tasks, obtain approval for the specific job and confirm the plate is currently clear. Approval binds the file SHA, device and material mapping; changes require rechecking. The existing 30-minute plate-clear/approval checks remain in effect.

Official Studio uses the same PrintLab task record: preflight, reserve one send, click Send, then read back the unique task name. Automation operates only within its supported printer/UI scope. Reconcile unknown results before trying again. After each plate, physically remove the part and clear the plate before continuing. See `official-studio-dispatch.md` and `docs/PRINTING.md` from the workspace root.

## Physical feedback and continuation

Record sending, device activity, actual extrusion, first layer, machine completion and physical acceptance separately. Inspect dimensions, assembly, feel, strength, support removal and defects. Associate user feedback with the actual version and material; preserve failed-part causes and uncertainty.

Material remaining may come from device reports, inventory estimates or weighing; identify the source. A software value of 100% does not establish a full physical spool. Save a handoff every session and continue the same project.
