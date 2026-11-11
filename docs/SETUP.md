# 安装 PrintLab

Windows 使用 [Windows 安装与工作流](WINDOWS.md)。以下命令适用于 Mac。

## 准备

需要 macOS 14+、Python 3.11+、Node.js 22+（包含 npm）、Git 和可用的 Codex。首次安装只需工作台依赖，建模与设备连接按下面步骤逐项接入。依赖原作者链接见 `DEPENDENCIES.md`。

## 安装工作台

```bash
git clone https://github.com/AFangTeam/PrintLab.git
cd PrintLab
bash scripts/setup.sh
bash scripts/start.sh
```

浏览器打开 <http://127.0.0.1:8018>。终端退出时服务结束。若 8018 已被占用，先核对正在运行的服务身份，避免启动两个工作台写同一份资料。独立工作空间可运行 `bash scripts/start.sh --port 18018`，访问相应端口。`setup.sh` 在本仓库创建 Python 虚拟环境，通过 PyPI/npm 下载工作台依赖并构建网页，随后生成空本机配置。

Python 版本不够时，安装 Python 3.11 或更新版，用绝对路径运行 `PRINTLAB_PYTHON=/path/to/python3 bash scripts/setup.sh`。安装完成可运行 `./Harness/bin/printlab doctor`。

## 让 Codex 接手

观众的日常操作见 [交互指南](GETTING_STARTED.md)，Agent 的执行步骤及完成标准见 [Agent 接手指南](AGENT_START.md)。

在 Codex 打开本仓库，使用 README 中的接手提示词。首次补充 `Context/profile.md` 中的用途和偏好，选择当前可用的 Codex 模型。模型偏好写入 `Context/agent-policy.json`。角色提示词见 `ROLES.md`。

创建空项目的示例命令如下。

```bash
./Harness/bin/printlab new '我的第一件作品' --kind functional --brief '填写用途、尺寸和完成标准'
./Harness/bin/printlab context P001
```

## 连接 Bambuddy 和打印机

1. 使用者从 Bambuddy 原项目独立安装，按上游说明运行服务并添加自己的打印机。它管理设备连接、库存和历史。
2. 在 Bambuddy 设置中创建只读 API key，读取其打印机 ID。写入 `Runtime/private/bambuddy.json` 的 `read_api_key`，保持文件权限 600。需要实际发送时，才配置具有相应权限的 `write_api_key`。
3. 编辑 `Runtime/config.json`，填写 `bambuddy_url` 和 `printer_id`。默认 URL 是 `http://127.0.0.1:8017`，应按自己实际安装的地址调整。
4. 更新 `Library/Devices/X2D/device.json`，核实型号、喷嘴、板型、AMS/外挂以及 FTS 情况。该目录沿用首版 X2D 的设备卡路径，填写内容必须对应自己的机器。
5. 运行 `./Harness/bin/printlab status` 和 `./Harness/bin/printlab materials`，确认设备身份、实时状态和材料映射。把核验结果写入 `Library/Devices/X2D/installed.md`。

以上下载、安装、配置检查和故障修复可以由具备本机终端能力的 Agent 执行。登录、密钥授权、macOS 权限选择和实体装料由使用者在实际界面或设备上完成，再让 Agent 读取结果继续。

API key 只保存在本机受限文件中，填写时不要把真实 key 粘进公开 issue 或运行日志。PrintLab 通过 HTTP API 访问独立运行的 Bambuddy，相关数据由使用者本机管理。

## 安装建模和切片工具

- **Text-to-CAD** 从原项目的安装指南独立安装 Codex 插件。先用其当前帮助验证建模、导出和 CAD 查看器，再开始具体作品。`Harness/bin/text2cad` 会调用已安装的 `cad` 或 `cadgen`，也可用 `PRINTLAB_CAD_COMMAND` 指定可执行文件。
- **CadQuery 导出链** 如果需要运行 PrintLab 的 `build --engine cadquery`，在本地虚拟环境独立安装 `cadquery`、`trimesh`、`numpy`、`pillow`。命令为 `Runtime/venv/bin/python -m pip install cadquery trimesh numpy pillow`，实际版本保存到自己项目的工具记录。
- **Blender** 从官网安装，`Runtime/config.json` 中的 `blender_path` 默认指向 `/Applications/Blender.app/Contents/MacOS/Blender`。
- **Bambu Studio** 从官方来源安装，登录和连接自己的设备。`slicer_path` 默认指向 `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio`。切片配置从这份本机安装读取。

各工具都准备好后，运行 `doctor`，让 Codex 在临时项目中验证真实尺寸、单位、导出和预览。首版当前 build 引擎为 CadQuery/Blender，Text-to-CAD 生成的 STEP 可以通过同版本 CadQuery 桥接导出，须保留源脚本和输入。

## 可选 Mac 窗口

安装 Xcode Command Line Tools 后，执行 `zsh Harness/macos/build.sh`，得到 `Runtime/macos-build/PrintLab.app`。把生成的应用拖入自己的应用目录。窗口使用本机 8018 工作台，先保持 `scripts/start.sh` 运行。移动工作空间后重新构建，应用会记录实际路径。

## 首次打印

按 `PRINTING.md` 逐项验证。工作台发送助手需要独立构建与用户授予辅助功能、屏幕读取权限。`studio_printer_name` 填写自己 Bambu Studio 中的准确设备名称，发送时还会检查序列号匹配。

## 更新与备份

更新前保存本机项目与配置。`python3 Harness/backup.py backup --help` 查看当前备份参数，备份含私人配置，保存在自己的受限目录。Git 更新源码后重跑 `setup.sh`，初始化会保留已有配置和资料。第三方工具升级后，重新核对接口和切片行为。
