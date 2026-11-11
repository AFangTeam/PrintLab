# 验证记录

## v0.2.0 Windows 与 Mac

2026-11-11 在 GitHub 托管 Windows 虚拟机完成独立安装与验收，源码提交 `b5a87c3`。Windows Server 2022 使用 Python 3.11.9，Windows Server 2025 使用 Python 3.13.17，Node.js 22。两台机器各自完成以下检查。

- PowerShell 安装入口、生产网页构建、CLI 入口和真实服务启动。
- Python 测试各 **356 通过、20 跳过**。包含跨进程排他锁、中文文件读写、私人目录 DACL 和 Windows 官方 Studio 提示。
- Node 离线检查各 **12 通过**。
- 独立进程入门验收全部 5 组通过，验证建项目、分工、交接与下一进程接续。
- Chromium 打开总览及七个工作台页面，创建并读取中文项目，在包含空格和中文的临时路径运行实际服务器，页面脚本错误为零。
- 保存 JUnit XML、浏览器结果 JSON、桌面/窄屏截图和服务日志。查看对应 Windows job 与 Artifacts。[云端运行记录](https://github.com/AFangTeam/PrintLab/actions/runs/43027295139)

本机 Mac 对相同源码运行 **368 通过、8 跳过**，Node 12 项通过。此前候选 `adc2619` 的 macOS 云端安装、入门验收与浏览器检查通过。其后的平台代码改动为 Windows DACL 设置与 Mac 专用命令在 Windows 上的错误提示。[Mac 云端记录](https://github.com/AFangTeam/PrintLab/actions/runs/43026694159)

Windows 的 20 项跳过包括 14 项 Mac 专用适配检查，以及 6 项实际设备、已安装切片配置与私人模型样本检查。Mac 的 8 项跳过包括这 6 项与 2 项 Windows 专用检查。

Windows 云端环境为 Server 2022/2025 x64。Windows 10/11 桌面、真实 CAD/切片软件、打印机连接与实体打印待现场验证。自动 Studio 发送助手适用于 macOS，Windows 使用官方 Studio 界面交接。官方 `submit` 预约接口依赖的独立原生检查客户端尚未完成 Windows 安装验收。浏览器合成项目验收覆盖工作台与文件交接，宿主聊天创建仍按实际能力确认。

v0.1.2 验证日期为 2026-11-11。验收使用同一台 Apple Silicon Mac 的全新隔离目录、独立 Python 虚拟环境与独立工作台端口，Python 3.13、Node.js 22.23.2。

## v0.1.2 已完成

- 下载公开 v0.1.1 ZIP 并全新安装，检查原有观众与 Agent 入门流程，据此修复文档、模板及 CLI 缺口。
- 将 v0.1.2 待发布文件复制到另一空目录，运行 `scripts/setup.sh`，安装依赖并完成网页生产构建。
- Python 自动测试 **365 通过、6 跳过**。覆盖项目与版本、文件路径、确认与回执、重复发送防护、重启恢复、材料、购物清单、历史、安装初始化、自定义端口、分工读取及发送助手 CLI 路由。
- Node 离线检查 **12 通过**。
- `scripts/verify_onboarding.py` 通过全部 5 组检查。实际 CLI 子进程完成空工作空间初始化、新建项目、分工记录、两次交接及新进程接手；HTTP API 可读取项目、需求和分工，设备保持待配置，待打印队列为空。
- 使用 `scripts/start.sh --port 18018` 启动全新工作台。在浏览器填写“新想法”，点击复制后显示成功状态；用 CLI 创建该模拟需求，刷新后显示 P001 项目及初始需求。
- 浏览器打开“复盘与接续”，确认 Sara、Mike、任务小组的模拟分工与本轮交接实际可见。下一进程继续相同项目，历史交接保留。
- `printlab studio-bridge capability` 对未安装助手返回对应状态。build、capability、permissions 三条 CLI 路由通过 mock 检查。
- 发布文件检查覆盖个人绝对路径、模型文件扩展名及 Markdown 相对链接。

## 首版已有验证

- 初始化重复执行保留已有配置与用户偏好，私人配置文件权限为 600。
- 独立工作台的健康、项目、总览、设备、历史、购物、资料和待打印接口返回 HTTP 200。
- `Harness/macos/build.sh` 完成可选 Mac 应用构建及本机签名校验。原生窗口交互尚未单独验收。
- 发布文件检查覆盖内网地址、凭据常见格式及嵌入凭据的 URL。

## 验证范围与待验证项

6 项跳过分别对应实机只读集成、两项已安装切片配置和三项私人真实切片样本。相关数据由使用者在自己环境中提供。

本轮角色任务采用模拟记录，验证的是共享文件、CLI、网页与跨进程接续。实际宿主创建 Sara/Mike 聊天和跨聊天调度尚未验收，也尚未开展独立 Agent 仅凭仓库的盲测。

其他 Mac 上的安装、图像生成、真实 CAD、切片、设备连接、Studio 权限与打印，需要按 `AGENT_START.md`、`SETUP.md` 和 `PRINTING.md` 在当地环境逐项验证。其他机型、Bambuddy 新版、其他 Studio 版本与多材料发送路线尚待验证。

构建保留两条非阻断提示。Three.js 分包约 528 kB，Vite 提示超过 500 kB。当前 Starlette 测试客户端提示其 httpx 兼容接口将弃用，全部测试仍通过。

## 复现

```bash
bash scripts/setup.sh
Runtime/venv/bin/python scripts/verify_onboarding.py
Runtime/venv/bin/python -m pytest Harness/tests -q -rs
node --test Harness/tests/native-inspection.test.mjs
cd Harness/studio
npm run build
```

有设备连接时，先核对测试目标与环境，再显式选择 `PRINTLAB_LIVE_TEST=1` 的只读集成测试。实际打印依照当前具体任务的确认流程执行。
