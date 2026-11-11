# ChatGPT、电脑和手机怎样参与打印

PrintLab 是运行在你自己电脑上的工作台。ChatGPT/Codex 需要宿主提供本机文件、终端或桌面操作工具，才能执行相应工作；只有网页聊天并不自动获得这些能力。

| 入口 | 实际路径 | 条件与边界 |
| --- | --- | --- |
| Agent 设计 | 需求 → Text-to-CAD/参数化源文件 → 真实预览 → Bambu Studio 切片 → PrintLab 登记 | 需要本机执行及对应工具；图像生成和 CAD 查看能力分别核验 |
| Agent 控制打印 | 具体任务批准 → PrintLab 预检与预约 → 官方 Studio 界面发送一次 → 设备读回 | 需要桌面控制能力；Windows 可由具备该能力的 Agent 操作官方界面，尚无 Windows 专用自动发送助手 |
| 工作台一键启动 | 待打印卡片 → 核验 → 清板确认 → 启动 → 本机 Studio 助手 | 仅 PRINTING.md 列明的 Mac/X2D/Studio/材料组合；按钮不绕过预检和授权 |
| 电脑 Studio | 打开已绑定的切片包，核对设备、板型及材料，再按 PrintLab 官方交接发送 | 不重新切片或换包后沿用旧批准，发送不明不得重复点 |
| 手机浏览器 | 私人网络连接电脑上的 PrintLab 网页 | 电脑服务需持续运行；发送仍由电脑执行，Mac助手需已登录且解锁 |
| Bambu Handy | 拓竹官方云服务与手机应用 | 与 PrintLab 手机网页是不同入口；LAN Only 下的可用功能按机型手册核实，不能承诺仍可云打印 |

Bambuddy 捕获的 Studio/Handy 打印历史可以在工作台显示；历史可见不等于 PrintLab 已取得这些客户端的控制能力。

## 先选择连接路线，再修改打印机设置

不能把“所有工作台连接都必须打开 LAN Only”作为统一前提。只读监控、第三方直接控制和官方 Studio 发送有不同条件。先查你当前机型、固件及所选路线。

Bambuddy 文档对较新固件的完整第三方控制要求 LAN Only 与 Developer Mode；仅 LAN Only 而无开发者模式可能只有监控能力。请按对应机型菜单启用，并读取新的访问码，切换模式后旧码可能失效。官方 Studio 路线使用官方应用的连接与授权，不能把原生第三方通道受限说成所有发送都不可用。[Bambuddy 设备与开发者模式说明](https://wiki.bambuddy.cool/reference/printers/)

在 Bambuddy 中添加设备需要对应的地址、序列号、访问码和可通信网络。核对电脑/服务到打印机的连通性，避免访客 Wi-Fi 隔离。只读验收应读回正确机型/身份、当前状态、温度及 AMS 数据；不要通过加热、运动或打印试探连接。[首次设备配置](https://wiki.bambuddy.cool/getting-started/first-printer/)

## 配置 Bambuddy

从 [官方安装页](https://wiki.bambuddy.cool/getting-started/installation/) 独立安装。Windows 有独立安装器，默认服务地址为 `http://localhost:8000`；本项目历史示例 `8017` 并非固定要求。将实际地址写入 `Runtime/config.json` 的 `bambuddy_url`，并填写真实 `printer_id`。

在 Bambuddy 创建所需 API key，保存在 `Runtime/private/bambuddy.json`。先配置只读 key 验收 `status` 和 `materials`，需要队列写入时再配置写入权限。Studio 官方发送不等于调用 Bambuddy 队列。

## 手机访问

本机地址 `127.0.0.1` 在手机上指手机自身，不能拿它访问电脑。按 PRINTING.md 配置私人 Tailscale 连接与本机 `tailscale_ip`，手机登录同一私人网络后访问电脑地址与工作台端口。无需为演示把工作台公开到互联网。网页能打开、能预检、能发送分别验收；锁屏或权限不足会影响 Mac 助手。
