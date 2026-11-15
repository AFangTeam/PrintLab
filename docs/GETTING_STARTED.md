# Using PrintLab

## Give the repository to your agent

Use Codex or another agent on this computer with terminal and local file access, then send:

> Install https://github.com/AFangTeam/PrintLab on this computer. Read README.md, AGENTS.md and docs/AGENT_START.md. Create a persistent workspace, install and start the workbench, and run onboarding verification. Create Sarah, the 3D-printing advisor, and Mike, the workflow designer, as two chats sharing that workspace, and record their actual setup status. Create a task-group chat when I choose my first object. Install missing third-party tools independently from their original authors. Tell me the exact actions required for device information, login or system permissions. Report the workspace path, workbench URL, role entry points, verified results and next steps. Communicate in my preferred language.

The agent downloads the repository, installs workbench dependencies, initializes local configuration and opens the page. A fresh installation normally has no projects and no connected device. The agent can then collect preferences/device facts and connect modeling, image and printing tools individually.

Reading the repository in a browser does not give an agent local installation capability. Chat creation is also a host capability. If available, the agent can create and verify chats under the explicit request above. Otherwise, it supplies titles, prompts and the workspace path so the user can create chats in the same workspace.

## Where to interact

The UI currently uses Chinese labels. The exact labels below help you locate controls; the explanations are in English.

| Goal | Entry point | Result |
| --- | --- | --- |
| Discuss requirements, share references, revise dimensions/appearance | Task-group chat in Codex | Agent updates project files and design versions |
| Ask about machines, filament, faults and accessories | Sarah chat | Updates device knowledge, material evidence and shopping list |
| Install tools, diagnose connections, repair the workbench | Mike chat | Updates local configuration and verification records |
| View projects, models, materials, history and handoffs | PrintLab web workbench | Displays data from the current workspace |
| Capture a new idea | “新想法” (New idea), then “复制需求到对话” (Copy requirements to chat) | Paste into the task-group chat; the agent creates the project |
| Start a specific prepared print | Task checks and start control under “待打印” (Prepared prints) | Uses current device state, clear-plate confirmation and task-specific authorization |

The page displays agent outputs through shared files. Chats handle requirements, tools and project updates. The New idea control produces a prompt to paste; the project enters the gallery only after the agent acts on it.

## Create your first object

Create a chat in the same workspace, for example “Task group · Desk headphone hook”, and send:

> I want a desk headphone hook. Create a PrintLab project and record its purpose plus the desk thickness, available space and headphone weight that I need to measure. Establish requirements first; wait for my measurements before shape concepts. Record Sarah's material/accessory checks and Mike's tool checks in the project assignments. Give me the project ID and gallery entry point.

The agent uses `printlab new` to create a folder and an ID such as `P001`, then records requirements and assignments. Refresh the page and open it under “项目图册” (Project gallery) to see requirements, files and handoffs. A new project shows “预览待生成” (Preview not yet generated) until real geometry is exported.

One task-group chat can cover every stage of one object. When collaboration is needed, give Sarah or Mike the same project ID and a specific question. Save actual chat entry points in `Context/team.md` and project tasks in `Review/team.md`.

## Assignments and handoffs

For Sarah:

> Take over P001. Run printlab context P001 first. Check suitable materials I already own, accessories to obtain and unresolved facts. Save results in the corresponding records and Review/team.md, then write a handoff.

For Mike:

> Take over P001 and read the latest handoff. Check local modeling/export tools, repair the current blocker, record actual versions and verification, then save a handoff.

Back in the task group:

> Continue P001. Read the current context, assignments and handoff. Retain confirmed dimensions and appearance, and continue from the next step.

Every chat must point to the same absolute workspace. At session end, use `printlab handoff`; the next session follows `project.json.latest_session`. The current task group coordinates the official version, while collaborators use separate candidate directories.

## Move from design to printing

After requirements are complete, proceed through concepts, three-view selection, actual CAD, comparisons/revisions, colors, final engineering and slicing comparisons. The agent shows results when aesthetic choices or physical measurements are needed. After device connections and material mappings are checked, confirm the exact job and that the plate is clear. Once printing finishes, provide physical photos, measurements and usage feedback for the task group to record.

This repository can establish the workbench, roles, shared records and project continuation. Image generation, CAD, slicing and physical dispatch depend on independently installed tools, account permissions, model and materials. Record each capability's real verification status. See [dependencies](DEPENDENCIES.md), [printing](PRINTING.md) and [language coverage](LANGUAGE.md).
