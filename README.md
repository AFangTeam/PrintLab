# PrintLab

简体中文 · [English](README.en.md)

把一个想法，接着做成一件拿得起来的东西。

PrintLab 是阿方（Eric）在 E41 视频中使用的 3D 打印工作台与协作流程，面向 **Mac / Windows + Codex + 拓竹打印机**。你描述需求，Codex 协助选外形、建立模型、比较切片，再把版本、材料、打印记录和实物反馈保存在同一个工作空间。

## 历史与收藏的同步范围

当前发布版汇总 Bambuddy 已捕获的打印记录，并展示本地维护的灵感收藏。安装前的 Bambu Cloud 历史和 MakerWorld 账号收藏自动同步仍待实现。需要保留 Handy、云打印和账号收藏的使用者，应在安装时明确这些需求，按同步排查核对已有功能。

[历史与收藏同步排查](docs/SYNC_TROUBLESHOOTING.md)

## 从这里开始

把仓库链接和下面这段话发给具有本机终端、文件读写能力的 Codex 或其他 Agent。

> 请帮我安装 https://github.com/AFangTeam/PrintLab 。先读 README.md、AGENTS.md 和 docs/AGENT_START.md，在本机建立长期工作空间，启动工作台并运行入门验收。帮我建立 Sara · 3D 打印顾问和 Mike · 工作流设计师两个聊天，全部绑定同一工作空间，记录实际建立状态。第一件作品确定后再建立任务小组。第三方工具从原项目独立安装。需要设备信息、登录或系统权限时告诉我具体操作。最后给我工作空间路径、工作台地址、角色入口、验证结果和下一步。

仓库内提供原创 [PrintLab Skill](.agents/skills/printlab/SKILL.md)。支持仓库 `.agents/skills` 的 Agent 可在此工作空间加载；其他宿主按自身技能安装规则安装该目录，技能仍需指向实际工作台。首次设备信息按 [配置访谈](docs/FIRST_RUN.md) 收集。

观众的聊天、网页操作与分工示例见 [交互指南](docs/GETTING_STARTED.md)。Agent 的执行步骤与完成标准见 [接手指南](docs/AGENT_START.md)。

想自己安装，可以使用 Python 3.11+ 与 Node.js 22+，在终端执行以下命令。

```bash
git clone https://github.com/AFangTeam/PrintLab.git
cd PrintLab
bash scripts/setup.sh
bash scripts/start.sh
```

打开 <http://127.0.0.1:8018>。安装程序生成空工作空间与本机配置，重复运行会保留已有配置。系统 Python 版本较旧时，用 `PRINTLAB_PYTHON=/你的/python3路径 bash scripts/setup.sh` 指定解释器。详细步骤见 [安装指南](docs/SETUP.md)。

也可以从 [Release](https://github.com/AFangTeam/PrintLab/releases/latest) 下载 `PrintLab.zip`。解压得到 `PrintLab/` 文件夹，在 Codex 中打开，或执行以下命令。

```bash
curl -fL -o PrintLab.zip https://github.com/AFangTeam/PrintLab/releases/latest/download/PrintLab.zip
unzip PrintLab.zip
cd PrintLab
bash scripts/setup.sh
bash scripts/start.sh
```

Windows 用户在 PowerShell 中运行以下命令。安装 Python 3.11+ 和 Node.js 22+ 后，打开仓库目录。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Windows 的工具路径、验证命令和官方 Studio 交接见 [Windows 指南](docs/WINDOWS.md)。

## 这支队伍怎样配合

- **Sara · 3D 打印顾问** 了解你的设备、材料和常见故障，帮助核对配件与耗材。购物清单可以跨项目汇总。实际加购物车由你授权后，交给具备浏览器操作能力的 Codex 完成。
- **Mike · 工作流设计师** 维护工具连接、工作台和共用规则，处理安装、版本、接口与流程问题。
- **任务小组 · 作品名称** 每件作品开一个对话，保存需求、选图、源模型、切片与反馈，后续会话接着同一项目继续。

角色可直接从 [角色提示词](docs/ROLES.md) 复制。工作台通过文件和命令向 Codex 提供上下文，具体模型与工具能力取决于使用者当前安装的 Codex 环境。

## 工作台里有什么

- 项目图册、真实 3D 模型预览和设计版本。
- Bambuddy 提供的设备、材料与已捕获打印历史。
- 灵感收藏、个人偏好和每轮选图记录。
- 跨项目配件清单、库存与采购记录。
- 已准备的打印包、材料映射、时间和用量，以及绑定具体任务的确认与回执。

首次安装会显示空项目和未连接设备。按安装指南连接自己的设备后，页面展示相应数据。

## 从需求到实物

描述用途与尺寸 → 选外形 → 确认三视图 → 实际 CAD → 对照修改 → 配色与材料 → 切片比较 → 确认这一版打印 → 实物反馈。

新外形默认先选单张方案，再从同一方案的四套三视图中选一套。小改动按影响范围处理，已有决定接续使用。Text-to-CAD 提供建模和查看能力，尺寸、接口和实际装配仍逐项检查。完整步骤在 [工作流](Context/workflow.md)。

## 支持范围

Mac 使用 macOS 14+，推荐 Apple Silicon。Windows 提供原生 PowerShell 安装、命令行与浏览器工作台。通用工作台可独立启动，设备状态与历史依赖单独安装的 Bambuddy。Mac 自动发送助手对应 **X2D、中文 Bambu Studio 02.08.02.61、0.4 mm、单主料 AMS、左主喷嘴、纹理 PEI 单盘**。其他机型、软件版本和多材料路线需要 Codex 按现场情况核对，详见 [兼容性与打印](docs/PRINTING.md)。

本仓库提供工作台源码、原创流程文档、角色提示词和空项目模板。第三方项目、模型权重、Bambu 软件和插件从各自官方来源独立获取。你自己的作品保存在本机 `Project/`。第三方来源及职责见 [依赖说明](docs/DEPENDENCIES.md)。

## 开发与验证

```bash
Runtime/venv/bin/python scripts/verify_onboarding.py
Runtime/venv/bin/python -m pytest Harness/tests -q
node --test Harness/tests/native-inspection.test.mjs
cd Harness/studio && npm run build
```

测试使用临时工作空间与合成设备。已安装设备的只读检查需显式设置 `PRINTLAB_LIVE_TEST=1`。发布版验证记录见 [验证说明](docs/VERIFICATION.md)。

## 使用许可与署名

PrintLab 原创源码和文档采用 **PolyForm Noncommercial 1.0.0**。允许在许可规定的非商业用途下使用、修改和再发布，再发布须附上许可及 `NOTICE.txt` 中的署名声明。商业用途需要另行取得 AFangTeam 授权。

原作者为 **AFangTeam / 阿方（Eric）**，项目地址为 <https://github.com/AFangTeam/PrintLab>。许可全文见 [LICENSE.md](LICENSE.md)，署名要求见 [NOTICE.txt](NOTICE.txt)。独立安装的第三方软件遵循各自的许可。
