# 复刻体验审查（2026-11-12）

审查源码：2491037bbff7c4d037e3e7b1c4c86e37e0e3aa72，版本 0.2.0。本文记录调查和待修复项，不表示问题已修复、重新完成虚拟机验收或已发布新版。

## 官方资料带来的发布要求

- [Agent Skills 规范](https://agentskills.io/specification)：独立技能以带 name、description 的 SKILL.md 为入口；兼容性、脚本、参考资料和资源应可找到。AGENTS.md 是仓库协作入口，不能代替可独立分发的 Skill。
- [Skill 脚本指南](https://agentskills.io/skill-creation/using-scripts)：声明前提、固定工具版本、使用相对路径，把复杂操作收敛到可测试脚本。第三方工具可以引用独立安装，不必复制到本仓库。
- [GitHub 仓库建议](https://docs.github.com/en/repositories/creating-and-managing-repositories/best-practices-for-repositories)：README、许可、贡献与问题报告入口共同构成使用体验。
- [GitHub Release](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)：发布物应对应明确 tag。本项目应额外验收实际下载的发布 ZIP，不能仅验收源码 checkout。
- [GitHub 托管运行器](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners)：新的 VM 仍预装工具。因此云端绿色结果不等于裸机前提齐全，更不证明打印机硬件和桌面发送权限可用。

## 本仓库核验结果

| 优先级 | 当前事实与证据 | 应完成的修改及验收 |
| --- | --- | --- |
| P0 | prepared.py 的 check 和 official.py 的 submit 默认调用 native.run_client；native.py 要求发布包没有的 Harness/native-client.mjs | 补上独立安装、可验证的检查通路；缺依赖时提前明确禁用发送。必须在不注入成功 inspector 的情况下走真实检查。不能跳过安全检查解堵 |
| P0 | verify_browser.py 只访问空待打印列表和其他页面；verify_onboarding.py 只验收空工作空间、项目、交接与 API | 覆盖已准备任务、检查、按钮、后台预约与单次发送；仅模拟硬件与 GUI 边界，加入未配置、版本不符、重复点击、未知回执等失败场景 |
| P0 | desktop.yml 在 checkout 源码上安装；独立 CAD、Bambuddy、Studio 安装没有进入完整验收 | 从候选发布 ZIP 在新目录安装，按文档走配置；区分真实依赖、模拟设备和实机待验证，保存错误、修复与结果 |
| P1 | README、AGENT_START、角色提示词齐全，但仓库没有 SKILL.md | 提供原创 PrintLab Skill 入口，说明何时使用、实际仓库路径、初始化与接续步骤、打印授权边界；独立安装后验证能发现和触发 |
| P1 | SETUP 将设备填写集中于步骤4；缺少结构化首次访谈 | 先问操作系统、Agent 能力、机型/固件、喷嘴/板型、AMS/外挂、材料与连接方式；未知保持未知。让设计小组读取同一设备档案 |
| P1 | Text-to-CAD 仅有上游安装链接和历史版本；Python 使用范围依赖，只有前端有 package-lock.json | 提供已验证版本清单、对应安装步骤及最小导出验收；锁定可复现的 Python 依赖，仍允许有记录的升级 |
| P1 | doctor 与文档已承认工具路径存在不足以证明可用 | 将版本、CLI 最小调用、配置、只读连通性和发送能力分开诊断；输出具体失败原因、修复命令及复验结果，不打印密钥 |
| P1 | PRINTING 中官方界面、Mac助手、队列并列；Windows 文档限制与主打印表述不够一致 | 建立系统 × 机型 × 入口 × 验证级别矩阵；明确 ChatGPT 需要本机执行/桌面能力，手机网页、Handy、Studio 是不同入口；分别解释云与 LAN 路线的条件 |
| P2 | 有许可、署名、更新提示；无问题表单和贡献说明 | 增加收集系统、版本、复现步骤、脱敏诊断的模板；说明备份、升级失败回退及用户数据保留 |

## 新版验收完成标准

1. 先产出候选 ZIP 和 SHA-256，VM 从该包开始，使用 README 命令，不使用维护者的私人路径和缓存环境。
2. 工作台启动、重复安装保留配置、中文空格路径、实际网页操作及跨进程接续通过。
3. 外部工具独立安装并记录版本；实际生成临时测试几何和导出，测试生成物不作为模型资源打包分享。
4. 真实检查链不靠假的成功返回；硬件/GUI模拟边界明确，发一次、未知不重发等条件必须保留。
5. 每项记录已验证、模拟验证、未验证、失败。Windows Server VM 不写成 Windows 10/11 实机验收。
6. 打印机连接、真实 Studio 操作、出料与成品另行现场核验；安装/发布授权不当作实体打印授权。
7. 发布 tag、ZIP、验证提交和文档一致；下载读回后核对 SHA-256。未完成步骤不能写进已验证范围。

建议先修 P0，再完成 Skill 与首次配置；不以增加文档数量代替打通核心流程。

## 修复进展（候选分支，尚未作为新版发布）

- `942917a`：公开上游 1.1.33 独立安装与 MCP 文件检查已替换缺失客户端的 inspect 路径；原生直接发送仍不提供。Python 和检查器下载依赖已锁定，新增标准 Skill 与首次设备访谈。
- `dfea729`：真实文件检查接入工作台 API、批准、官方预约和模拟界面单次发送；新增从 git archive 候选 ZIP 全新安装验收及连接方式文档。
- 本机从 dfea729 ZIP 全新安装通过，ZIP SHA-256 为 `9ff491b7f423733e4105adad2406eafbd33097b1e34b871b4e28b2798dfe6537`。完整软件测试保留设备/GUI模拟边界。
- 新增固定版 Text-to-CAD 隔离安装/真实建模/STEP/STL 导出验收，首次运行发现 Agent 环境禁止自动拉起引擎，改为显式启动获准的独立服务。状态、缓存、启动器及进程通信目录均单独配置。

- `f0f8d87` 在 Mac、Windows Server 2022、Windows Server 2025 的全新安装、ZIP 安装、真实 CAD 建模和导出检查全部通过。[云端记录](https://github.com/AFangTeam/PrintLab/actions/runs/43092718752)
- `644b6a6` 增加真实 Chromium 待打印按钮测试，本机已验证检查、清板、提交和刷新后保持单次发送记录。设备与桌面发送边界使用模拟对象，测试图片明确标为合成数据。该提交的云端验证正在进行。
- 独立 Bambuddy `v1.2.5.7` 服务端在全新本机虚拟环境安装通过，真实 HTTP 客户端验证六个只读接口，临时 key 已撤销。已加入可复用安装验收脚本、配置指南和更新回退说明。

仍需完成：最终候选 Mac/Windows 云端结果读回、独立 Bambuddy 的 Windows 验收、CAD 宿主插件与查看器验证边界、独立 Studio 配置与切片验证、最终发布包一致性复核。硬件连接与实物打印需使用者现场验证。
