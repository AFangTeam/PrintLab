---
name: printlab
description: 安装或使用 PrintLab 3D 打印工作台，接续作品的设计、材料、切片、待打印任务和实物反馈。用于用户要求配置 PrintLab、让 Agent 设计可打印作品或接续已有 PrintLab 项目时。
license: PolyForm Noncommercial 1.0.0; see the PrintLab repository LICENSE.md and NOTICE.txt.
---

需要本机文件与终端能力；工作台支持 macOS 和 Windows。CAD、设备连接及发送支持按实际安装和机型核验。

找到用户实际的 PrintLab 根目录，特征为 AGENTS.md、Harness/printlab 和 Context/workflow.md。当前目录属于已有工作空间时接续它；不要创建第二份项目库。若技能单独安装而工作台尚未安装，从 https://github.com/AFangTeam/PrintLab 的明确 Release 开始，记录版本，按其 README 安装。

所有下列路径相对实际工作台根目录，而非技能安装目录。

- 首次安装：读取 README.md、AGENTS.md、docs/AGENT_START.md、docs/ONBOARDING.md。先识别系统和缺少的前提，运行对应 setup/start 脚本；外部工具从原作者独立安装。不要假定 ChatGPT 有本机执行或聊天管理能力。
- 自动建队与首次访谈：用户的安装请求包含建立角色时，按 docs/ONBOARDING.md 执行宿主工具探测、已有入口查询、预留与真实创建、首条介绍读回。新角色使用 Mike 和 Sarah，已有 Sara 接续。主 Agent 读取设备、已装材料和库存，只问真实缺项。
- 开始设计或接续：读取 Context/profile.md、Context/workflow.md、设备档案；运行当前 CLI 的 --help 和 context，按 project.json 的 latest_session 继续原项目。新作品先了解用途、尺寸、设备、材料和验收标准。生图前用 constraints capture 保存实际来源，进入 CAD/切片前从 context 核对设备材料或需求变化。
- 外形、CAD、切片：按 Context/image-to-print.md 和 Context/cad-master-design.md 继承已选方案；真实源模型导出预览，关键接口与实测独立核对。依据当前机器比较打印方向、材料、支撑、分盘及完整工时。
- 打印：先读 docs/PRINTING.md。只通过工作台/CLI 的统一批准和发送入口，绑定具体模型版本、切片文件、设备、材料与有效清板确认。安装或设计不授权打印。结果未知先对账，不自动重发；不借第三方插件绕过 PrintLab 检查。
- 共同记录：使用 workspace 命令的哈希检查追加偏好、事实与经验，冲突后重读。用户确认拥有的其他耗材通过 material-intake 写入 Bambuddy，超时后使用相同请求标识对账。
- 交接：用 CLI handoff 保存完成项、当前版本、证据、未知项与下一步，再通过 context 读回。设备已结束不等于实物合格。

Mac CLI：`./Harness/bin/printlab`。Windows CLI：`powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\printlab.ps1`。先查当前帮助再选择参数。

报告实际工作空间、启动地址、工具版本、已验证能力和下一步。区分软件实测、模拟设备测试、实机验证；缺少能力应报告具体安装或配置步骤，不写成已完成。

## 既有终端与账号同步

安装先记录使用者正在使用的 Handy、Studio、Bambu Cloud 和 MakerWorld 功能，保留其账号登录、网络模式与现有凭据权限。为 PrintLab 新建专用读取凭据。用户需要云功能时，先说明 LAN Only / Developer Mode 的具体影响并确认所选路线。按 `docs/SYNC_TROUBLESHOOTING.md` 核对历史与收藏的实际来源及覆盖时间，核对原应用功能仍然可用。账号旧历史和 MakerWorld 收藏导入已排除在本轮开发范围外。已有档案缺图时，按 `docs/PREVIEW_RECOVERY.md` 使用 `printlab history-recover`，记录来源和恢复数量。
