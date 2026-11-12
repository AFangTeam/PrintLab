# Windows 安装与工作流

Windows 版本提供浏览器工作台、项目与版本管理、中文资料、跨会话交接、材料与打印记录、购物清单和打印包管理。使用 Python 3.11+、Node.js 22+（含 npm）以及有本机终端和文件访问能力的 Codex。

## 安装与启动

从 Release 下载 `PrintLab.zip` 并解压，或克隆仓库。进入 PrintLab 文件夹，在 PowerShell 运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

打开 http://127.0.0.1:8018 。保持启动终端运行。独立工作空间需要其他端口时，在启动命令末尾加 `--port 18018`。执行策略参数仅对该进程生效。

安装脚本优先使用 Python Launcher 的 `py -3`，也支持 PATH 中的 `python`。指定解释器时，先设置 `$env:PRINTLAB_PYTHON = 'C:\你的路径\python.exe'`。重复安装会保留已有配置。使用已下载 ZIP 时可以跳过 Git 安装。

## 验证与接续

```powershell
.\Runtime\venv\Scripts\python.exe scripts/verify_onboarding.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\printlab.ps1 doctor
powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\printlab.ps1 context
```

入门验收创建临时中文项目，通过独立进程检查项目、分工、交接和 API，成功输出 `ok: true`。Sarah、Mike 和任务小组共享同一工作空间，按接手指南建立入口与交接记录。其余文档的 `./Harness/bin/printlab` 命令在 Windows 中使用以上 PowerShell 入口，后面的子命令和参数相同。

## 独立安装设计与打印工具

Bambu Studio、Blender、Text-to-CAD、Bambuddy 和可选建模依赖均从各自上游独立获取。按照上游 Windows 安装说明记录实际版本和可执行文件路径。来源见 [依赖说明](DEPENDENCIES.md)。

独立安装步骤见 [Text-to-CAD](CAD_SETUP.md)、[Bambuddy](BAMBUDDY_SETUP.md) 和 [Bambu Studio](STUDIO_SETUP.md)。

在 `Runtime/config.json` 核对 `slicer_path`、`slicer_profiles_path`、`blender_path` 和 `cad_python`。安装程序会查找 PATH 与 Program Files 中的 Bambu Studio、Blender。JSON 中 Windows 路径可使用正斜杠，例如 `C:/Program Files/Bambu Studio/bambu-studio.exe`。切片配置目录通常为安装目录的 `resources/profiles`，应以实际安装为准。

需要 CadQuery 导出时，使用本机虚拟环境独立安装并检查实际导出。

```powershell
.\Runtime\venv\Scripts\python.exe -m pip install cadquery trimesh numpy pillow
```

MLX 图生模型路线适用于 Apple Silicon。Windows 的图生模型工具需按对应上游说明独立选择和验证。模型权重由使用者从原作者获取。

## 通过官方 Studio 打印

Windows 的待打印页按任务绑定的通道处理。使用 `bambuddy_queue` 的适配机型可以通过工作台按钮发送，条件与当前验证范围见 PRINTING.md。官方 Studio 包按下面步骤交接，Mac 的专用窗口助手仍需 macOS。

1. 在 PrintLab 保存当前版本、切片包、设备、板型、材料映射和用量，确认具体作业及清板状态。
2. 使用 `studio-copy 项目ID 作业ID` 准备官方 Studio 副本，按命令返回内容核对文件与任务记录。先查看当前 `--help`。
3. 使用者或具备桌面控制能力的 Agent 在官方 Studio 打开该副本，核对设备、材料与发送选项。保存用户对具体文件的批准，在 Studio 发送一次，并把任务名、文件哈希、时间与回执写入项目 Session。
4. 单次发送后读取设备状态与任务回执。回执不明确时先对账，再决定下一步。
5. 保存首层、完成状态与实物反馈，继续相同项目。

安装脚本会独立下载固定版本的公开文件检查器。`doctor` 实际运行文件检查，并报告依赖缺失或调用失败。Windows 的文件检查、官方预约和工作台 API 可运行。本候选版新增共用 Bambuddy 队列按钮适配；Mac Studio 助手继续仅在 macOS 使用。Windows 虚拟机中的新通道回归与实体发送验证尚待完成。

具体批准和回执约束见 [打印流程](PRINTING.md)。首次接入自己的打印机需现场验证设备、切片与发送。

## 虚拟机验证

仓库的 Desktop VM verification 工作流在 GitHub 托管 Windows Server 2022、Windows Server 2025 与 macOS 环境执行安装、自动测试、独立进程交接和 Chromium 页面检查。每次运行保存测试结果、服务日志与截图。Windows 10/11 桌面、用户安装的 CAD/切片软件以及实体打印需要相应环境验证。具体已完成结果见 [验证记录](VERIFICATION.md)。
