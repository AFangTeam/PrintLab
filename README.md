# PrintLab

把一个想法，接着做成一件拿得起来的东西。

PrintLab 是阿方（Eric）在 E41 视频中使用的 3D 打印工作台与协作流程，面向 **Mac + Codex + 拓竹打印机**。你描述需求，Codex 协助选外形、建立模型、比较切片，再把版本、材料、打印记录和实物反馈保存在同一个工作空间。

## 从这里开始

在 Codex 中打开本仓库，把下面这段话发给它。

> 请先读 AGENTS.md 和 docs/SETUP.md，帮我在这台 Mac 安装 PrintLab。向我确认打印机型号、喷嘴、打印板和已有耗材。第三方工具按照 docs/DEPENDENCIES.md 从原项目独立安装，先把工作台跑起来，再逐项验证设备连接和建模能力。完成后告诉我已经验证了哪些功能。

想自己安装，可以使用 Python 3.11+ 与 Node.js 22+，在终端执行以下命令。

```bash
git clone https://github.com/AFangTeam/PrintLab.git
cd PrintLab
bash scripts/setup.sh
bash scripts/start.sh
```

打开 <http://127.0.0.1:8018>。安装程序生成空工作空间与本机配置，重复运行会保留已有配置。系统 Python 版本较旧时，用 `PRINTLAB_PYTHON=/你的/python3路径 bash scripts/setup.sh` 指定解释器。详细步骤见 [安装指南](docs/SETUP.md)。

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

## 首版支持范围

macOS 14+，推荐 Apple Silicon。通用工作台可独立启动，设备状态与历史依赖单独安装的 Bambuddy。发布版的自动发送助手对应 **X2D、中文 Bambu Studio 02.08.02.61、0.4 mm、单主料 AMS、左主喷嘴、纹理 PEI 单盘**。其他机型、软件版本和多材料路线需要 Codex 按现场情况核对，详见 [兼容性与打印](docs/PRINTING.md)。

本仓库提供工作台源码、原创流程文档、角色提示词和空项目模板。第三方项目、模型权重、Bambu 软件和插件从各自官方来源独立获取。你自己的作品保存在本机 `Project/`。第三方来源及职责见 [依赖说明](docs/DEPENDENCIES.md)。

## 开发与验证

```bash
Runtime/venv/bin/python -m pytest Harness/tests -q
node --test Harness/tests/native-inspection.test.mjs
cd Harness/studio && npm run build
```

测试使用临时工作空间与合成设备。已安装设备的只读检查需显式设置 `PRINTLAB_LIVE_TEST=1`。发布版验证记录见 [验证说明](docs/VERIFICATION.md)。

## 使用许可与署名

PrintLab 原创源码和文档采用 **PolyForm Noncommercial 1.0.0**。允许在许可规定的非商业用途下使用、修改和再发布，再发布须附上许可及 `NOTICE.txt` 中的署名声明。商业用途需要另行取得 AFangTeam 授权。

原作者为 **AFangTeam / 阿方（Eric）**，项目地址为 <https://github.com/AFangTeam/PrintLab>。许可全文见 [LICENSE.md](LICENSE.md)，署名要求见 [NOTICE.txt](NOTICE.txt)。独立安装的第三方软件遵循各自的许可。
