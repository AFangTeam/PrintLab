# Codex 找不到 Studio 窗口时怎么办

## 这次修了什么

[Issue #7](https://github.com/AFangTeam/PrintLab/issues/7) 来自 MacBook Air M1 / macOS 15.6.1、中文 Studio 02.08.02.61、A1 0.4 mm、PLA、无 AMS / Ext。`noWindowsAvailable` 由 Codex Computer Use 返回；当时没有调用 PrintLab 发送助手。CLI 和人工界面切片成功。报告中的组合调用不足以确定底层哪一步失败，后来锁屏也不能解释此前错误。

**v0.4.2 增加独立的 Mac Studio 窗口控制入口。** Codex 可以调用 PrintLab 自己的助手读取窗口、恢复指定窗口、打开已有切片和发送准备页，不必一直重试发生故障的 Computer Use 调用。修复了助手对 macOS `/private/tmp` 路径的误判，改为按窗口身份截图，并在点击前检查前台、窗口位置和遮挡。超时保留回执，绝不自动重发。

这不是 Codex 引擎补丁，也不代表已在报告者的 M1 上验证通过。v0.4.1 只有 Windows 修复，不能用它验证本次新增能力。没有证据要求升级或降级 Studio。

## 先判断是否需要操作窗口

发送打印优先按 [默认发送路线](PRINTING.md#默认发送路线与后备方案) 评估 Bambuddy。适配和授权齐全时，直接通过 PrintLab 队列发送，无需修复窗口才能发送。用户拒绝授权、本版未适配或发送前检查失败时，再接续本页的 Studio 后备方案。结果不明先对账，不能把窗口故障当作换通道重发的理由。

报告者的 A1 / Ext 尚不在本版队列适配范围。可以直接在 Studio 复用已有切片完成当前打印。只有需要新增窗口助手时才升级，不让用户为了继续打印长时间 debug。

## 最少操作

让 Codex 按 [更新指南](UPGRADING.md) 升级到 v0.4.2，保留工程、配置、材料和旧任务。然后在新版工作空间执行：

```bash
./Harness/bin/printlab studio-bridge build
./Harness/bin/printlab studio-bridge windows
```

构建需要 macOS 14+ 和 Apple Swift 编译工具。若缺少工具，由 Codex 按系统提示处理；构建成功不等于系统权限已授予。只有 `windows` 显示权限缺失时才执行 `studio-bridge permissions`，按系统要求给 **PrintLab发送助手** 授予辅助功能和屏幕读取权限，再重跑 `windows`。不要删除 TCC 数据或给其他程序反复授权。

`windows` 返回进程 ID、完整窗口标题、Studio 版本和会话状态。后续目标必须来自这次实际返回，不能照抄示例数字。

```bash
# 只观察指定窗口
./Harness/bin/printlab studio-bridge inspect --studio-pid PID --window-title '完整标题'
# 恢复并激活该窗口一次，等待窗口稳定，不点击打印按钮
./Harness/bin/printlab studio-bridge recover --studio-pid PID --window-title '完整标题'
```

需要打开已有的单盘 `.gcode.3mf` 时，先计算当前文件 SHA-256，再运行：

```bash
./Harness/bin/printlab studio-bridge open-file --file '/绝对路径/文件.gcode.3mf' --sha256 '实际64位哈希'
```

该命令保留原工程，在 `Runtime/studio-previews` 生成经过逐项检查的预览副本，刀路和打印参数不变，不重新切片；另开 Studio 实例，返回新的进程 ID 和标题。打开后先 `inspect` 核对实际内容，再用返回的目标打开准备页：

```bash
./Harness/bin/printlab studio-bridge open-panel --studio-pid PID --window-title '文件.gcode'
```

`opened_panel: true` 表示实际读到了“发送打印任务”窗口，**没有点击最终发送**。按钮被其他窗口或通知遮挡时会拒绝点击；先移开遮挡、重新观察，再决定是否重试。超时或读回失败时先看当前窗口，不能假定动作没发生。

## A1 外挂与最终发送

通用窗口命令不要求 X2D、AMS 或打印机名称，因此 A1 无 AMS 也能使用。它们不创建打印批准或发送记录，也不代替机型、材料和清板核验。

**A1 / Ext 的最终自动发送尚未适配和实机验证。** 工作台现有自动发送仍限已验证的 X2D 单料 AMS 组合，Bambuddy 队列仍要求 `use_ams=true`。不能伪造 AMS、删除检查或把 A1 套进 X2D 发送流程。A1 到准备页后核对实际 A1 / Ext 与具体文件，最终发送由使用者在当前任务获得确认后完成；已有任务已发送或结果不明时，先对账，不再发送。

如果用户只需要继续当前已成功切片的打印，可以直接在 Studio 中完成，无需为了排障升级。若希望 Codex 继续自动操作窗口，推荐升级本版，避免要求用户长时间 debug。

## 报错与验证范围

错误包含 `code`、`stage` 和具体原因，区分权限、锁屏、窗口缺失、激活失败、窗口变化、遮挡和动作后未读到结果。未知回执保留在 `Runtime/studio-bridge-ipc` 的私有目录中；核实结果之前不要清理或重试发送。诊断只分享必要的脱敏错误，不能上传整个 Runtime 或项目目录。

本机中文 Studio 02.08.02.61 已实际验证窗口读取、指定窗口捕获、A1 测试切片的发送准备页、遮挡拒绝、独立实例打开以及 X2D 预览。A1、A1 mini、P1S、X1 Carbon、X2D 的合成模型均通过官方 CLI 切片。没有 A1 实体发送验证，也没有复现报告者完全相同的底层错误。详细范围见 [机型说明](MACHINE_SUPPORT.md)。

#7 保持开放，等待报告者用新助手做一次不发送的窗口复验。成功只确认新路径在其电脑可用，不能据此声称 Codex 的窗口引擎已修复。

## 可以直接给观众的 Codex

```text
请将我的 PrintLab 按官方 docs/UPGRADING.md 升级到 v0.4.2，保留工程、配置、设备、材料和任务记录，不重发旧任务。
按 docs/STUDIO_COMPUTER_USE.md 构建 PrintLab发送助手，读取 windows；只在缺权限时引导我完成一次系统授权。
我的配置是 A1、0.4 mm、PLA、无 AMS、Ext。保留实际配置，不套用 X2D/AMS。
复用已有正确切片，计算 SHA-256，通过 studio-bridge open-file 打开独立预览，inspect 核对后用 open-panel 打开发送准备页。不要最终发送，不要反复调用失败的 Computer Use。
报告成功到哪一步；失败只给我 code、stage、脱敏原因和一个最少操作。超时先读回，不重放动作。不要上传凭据或私人工程。
```
