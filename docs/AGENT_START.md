# Agent 从 GitHub 接手 PrintLab

## 接手目标与当前能力

目标是让使用者拥有自己的工作台、共同资料、角色分工和可跨会话继续的项目。首先确认当前 Agent 能读取 GitHub、运行本机终端、读写目标目录。浏览器/桌面控制、图像生成、CAD 查看器和聊天管理能力按当前宿主实际暴露的工具记录。

用户给出本仓库链接并要求安装时，先读取 README 和 AGENTS。按下面步骤自主完成授权内的安装、软件验收和故障修复。需要账户登录、密钥授权、系统权限选择、实体测量或装料时，给出具体操作，取得实际结果后继续。

所有相对路径均以仓库根目录为基准。共享目录是本机唯一长期工作空间。示例项目 ID 必须替换为命令实际返回的 ID。

## 下载和安装

先识别操作系统。Windows 使用 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1` 安装，使用同样方式执行 `scripts/start.ps1` 启动。以下 Bash 示例中的 `./Harness/bin/printlab` 在 PowerShell 中替换为 `powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\printlab.ps1`，`Runtime/venv/bin/python` 替换为 `Runtime/venv/Scripts/python.exe`。Windows 完整步骤见 [Windows 指南](WINDOWS.md)。

1. 检查当前目录和已有安装，找到已有工作空间就接续。新安装选择使用者指定路径，未指定时可采用 `~/PrintLab`，已有同名目录时先检查内容。
2. 克隆 `https://github.com/AFangTeam/PrintLab.git`，或下载 Release 的 `PrintLab.zip`。将 Codex 工作空间指向实际仓库根目录。
3. 检查 `python3 --version`、`node --version` 和 `npm --version`。需要 Python 3.11+、Node.js 22+。系统解释器较旧时，使用本机合适的解释器路径设置 `PRINTLAB_PYTHON`。缺少的基础运行时从官方来源安装。
4. 运行 `bash scripts/setup.sh`。安装结果应包含 `Runtime/venv/bin/python`、`Harness/studio/dist/index.html`、本机配置及 `Context/team.md`。
5. 运行下面的入门验收。它使用临时工作空间，通过实际 CLI 子进程检查建项目、分工、交接、重新读取及 API。命令结束输出 JSON，`ok` 应为 `true`。

```bash
Runtime/venv/bin/python scripts/verify_onboarding.py
./Harness/bin/printlab doctor
./Harness/bin/printlab context
```

`doctor` 的工具路径存在检查只能说明文件存在。继续用各工具实际帮助和最小功能调用验证可用性。第一次 `context` 的 `missing` 应为空，设备和材料可以处于待配置状态。

## 启动与检查工作台

运行 `bash scripts/start.sh`，在单独终端或宿主提供的持久进程中保持服务。打开 `http://127.0.0.1:8018`。默认端口被占用时，核对已有服务身份，独立工作空间可使用 `--port 18018`。

检查 `/api/health` 返回 `ok: true`，网页能显示总览、项目图册、资料与设备页。空工作空间应显示待配置设备。先把工作台地址和启动方式交给使用者。服务存活期间网页可持续访问，终端停止后需重新运行启动命令。

## 建立队伍

读取 [角色提示词](ROLES.md)。如果使用者已明确要求创建 Sara 和 Mike 聊天，使用当前宿主实际提供的聊天管理工具执行，给每个聊天设置同一个绝对工作空间路径和角色提示词，随后读回标题与入口。工具名称和参数以宿主当前帮助为准。

宿主缺少聊天管理能力时，提供两个标题、对应提示词及工作空间路径，由使用者手工建立。将已确认的入口写入 `Context/team.md`。状态按实际结果填写“已建立”或“待建立”。角色也可在同一个聊天中按当前任务切换。

只有使用者选择并授权并行代理时，才派发独立协作任务。角色分工平时通过共同文件与交接推进。跨聊天自动调度需要宿主具备相应能力。

## 创建真实项目与分工

先用 `./Harness/bin/printlab status` 查找是否已有对应作品。已有作品继续其 ID。新作品从用途、关键尺寸、外观和验收标准开始，未知事实保持待补充。

```bash
./Harness/bin/printlab new '桌边耳机挂钩' --kind functional --brief '用途为悬挂耳机，桌板厚度和载荷待使用者测量' --summary '桌边挂钩，先整理需求'
```

命令返回项目 ID 后，执行 `./Harness/bin/printlab context 项目ID`。根据返回的 `documents[].path` 找到以下文件并填写。

- `brief.md` 保存需求、已知条件与待确认事项。
- `decisions.md` 记录实际确认及出处。
- `Review/team.md` 记录当前统筹、Sara 的材料/配件任务、Mike 的工具任务，以及实际产出与交接。
- `Context/team.md` 记录这件作品对应的任务小组聊天入口。

在工作台刷新项目图册，检查新项目及需求可见。为作品创建聊天需要使用者要求或当前创建队伍指令中的明确授权，聊天命名采用“任务小组 · 作品名称”。

## 保存与验证交接

在每轮结束运行以下命令，内容使用本轮事实。

```bash
./Harness/bin/printlab handoff 项目ID --note '角色、当前版本、本轮完成、验证证据、用户确认、未解决项、下一步及相关路径'
./Harness/bin/printlab context 项目ID
```

确认返回内容包含本轮交接和 `Review/team.md`。下一位 Agent 以相同工作空间和项目 ID 再运行 `context`，按 `latest_session` 指针继续。项目正式版本由当前统筹者维护，协作候选用独立目录，合入时重新核对来源和输出。

## 接入设计与打印工具

按照 [依赖说明](DEPENDENCIES.md) 阅读上游当前安装方法，在用户授权范围内从原作者渠道独立安装。分别记录工具版本、实际入口、检查结果和未完成项。

| 能力 | 必要条件 | 最小验证 |
| --- | --- | --- |
| 概念图与选图 | 宿主可用的图像生成或使用者提供的参考图 | 能生成/读取图片并保存选择证据 |
| CAD 与预览 | Text-to-CAD、适用的 CadQuery/Blender 环境 | 实际导出、单位/尺寸检查与预览 |
| 材料与设备 | 独立 Bambuddy、用户设备和 API 凭据 | `status` 与 `materials` 读回正确设备和来源 |
| 正式切片 | 官方 Bambu Studio 与本机配置 | 实际切片、板型/材料映射和时间用量检查 |
| 发送助手 | 支持范围内的设备/Studio、助手和系统权限 | `studio-bridge capability` 返回实际结果 |

开始新外形前读取 `Context/image-to-print.md`，在记录用户选择时从 `Templates/Project/Review/design-target.json` 初始化项目对应文件，填写实际图片、哈希和选择。模型选择读取 `Context/agent-policy.json`，空值时使用用户当前可用的模型，并记录实际执行者。

首次设备接入遵循 [安装指南](SETUP.md)。实际打印按 [打印说明](PRINTING.md) 绑定具体文件、设备、材料与清板确认。

## 交付给使用者

报告实际工作空间、工作台地址与再次启动命令、已建立的角色入口、项目 ID 与当前阶段。分别列出工作台、项目接续、图像、CAD、切片、设备和打印的验证结果。为缺失能力写清具体下一步。验收依据包含真实命令结果、网页显示、文件与交接内容。
