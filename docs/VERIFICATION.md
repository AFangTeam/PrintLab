# 首版验证记录

验证日期为 2026-11-11。发布源码在独立目录安装和运行，环境为 Apple Silicon Mac、Python 3.13、Node.js 22.23.2。

## 已完成

- 从源码运行 `scripts/setup.sh`，通过 PyPI/npm 安装工作台依赖并完成网页生产构建。
- Python 自动测试 **361 通过、6 跳过**。覆盖项目与版本、文件路径、确认与回执、重复发送防护、重启恢复、材料、购物清单、历史、安装初始化及自定义端口的同源校验。
- Node 离线检查 **12 通过**。
- 初始化重复执行保留已有配置与用户偏好，私人配置文件权限为 600。
- 在临时工作空间通过正常 CLI 执行 `new`、`context` 和 `handoff`，确认空模板复制与接手记录。
- 使用 `scripts/start.sh --port 18018` 启动独立工作台，健康、项目、总览、设备、历史、购物、资料和待打印接口均返回 HTTP 200。
- 浏览器检查总览、待打印、购物清单、设备与材料页面。首次运行显示空项目、未连接设备与待安装发送助手。
- `Harness/macos/build.sh` 完成可选 Mac 应用构建及本机签名校验。
- 发布文件检查覆盖个人绝对路径、内网地址、凭据常见格式、嵌入凭据的 URL、模型文件扩展名和 Markdown 相对链接。

## 跳过的测试与验证边界

6 项跳过分别对应实机只读集成、两项已安装切片配置和三项私人真实切片样本。相关数据由使用者在自己环境中提供。

首版的这轮验证覆盖软件安装、工作台和模拟流程。新安装用户的真实建模、真实切片、设备连接、Studio 权限和实际打印需要按 `SETUP.md` 与 `PRINTING.md` 逐项验证。其他机型、Bambuddy 新版、其他 Studio 版本与多材料发送路线尚待验证。

可选 Mac 应用通过构建和签名校验，原生窗口交互尚未单独验收。网页浏览已完成实际检查。

构建保留两条非阻断提示。Three.js 分包约 528 kB，Vite 提示超过 500 kB。当前 Starlette 测试客户端提示其 httpx 兼容接口将弃用，全部测试仍通过。

## 复现

```bash
bash scripts/setup.sh
Runtime/venv/bin/python -m pytest Harness/tests -q -rs
node --test Harness/tests/native-inspection.test.mjs
cd Harness/studio
npm run build
```

有设备连接时，先核对测试目标与环境，再显式选择 `PRINTLAB_LIVE_TEST=1` 的只读集成测试。实际打印依照当前具体任务的确认流程执行。
