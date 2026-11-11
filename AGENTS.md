# PrintLab · Codex 工作入口

本仓库面向 Mac、Codex 与拓竹打印机。执行用户当前要求，先核对事实和项目状态，再选最简单可行的方法。

## 首次安装

读 `docs/SETUP.md`、`docs/DEPENDENCIES.md` 和 `docs/PRINTING.md`。使用 `bash scripts/setup.sh` 安装工作台和初始化本机资料，第三方工具交由使用者从原项目独立安装。安装前先读取原项目当前说明，明确下载内容和许可证。安装程序会从 PyPI/npm 获取工作台的软件依赖。

工作空间根目录为当前 checkout。CLI 是 `./Harness/bin/printlab`，每次用当前 `--help` 确认参数。已有模型、工具环境和用户配置优先接续。

## 每次接手

1. 读 `Context/profile.md`、`Context/workflow.md`、`Context/agent-policy.json`、`Context/taste.md` 和 `Library/Devices/X2D/device.json`。初始化后这些文件才会齐备。
2. 目标项目读 `project.json`、`brief.md`、`decisions.md` 和 `latest_session` 指向的交接。`printlab context 项目` 汇集同一份资料。
3. 报告项目、当前版本、已确认选择、尚待验证的部分与本轮下一步。
4. 收尾用 `printlab handoff` 保存完成结果、检查、问题和下一步。查看当前帮助确认参数。

## 分工与持久化

Sara 负责设备、材料、故障和配件。Mike 负责工作台、工具和流程。任务小组负责具体作品。提示词见 `docs/ROLES.md`。角色通过共同文件和命令协作，模型选择由用户当前可用的 Codex 环境决定。只有用户明确要求时才创建新会话或派发子 Agent。

- `Context/` 存流程、偏好和经验，偏好依据用户明确反馈。
- `Project/` 存需求、源模型、候选、正式版本、切片、回执和实物复盘。
- `Library/` 存使用者的设备、材料知识、灵感和来源。
- `Templates/Project/` 是新项目模板。
- `Runtime/` 存本机配置、凭据、缓存与第三方运行环境。

用户数据与凭据始终在本机维护。修改仓库源码时，检查 Git 暂存区，避免提交真实设备信息、聊天和个人资料。

## 设计与打印

遵循 `Context/image-to-print.md`，新外形两次选图后进入正式模型。真实模型按选定外形比较，接口、公差、装入路径、壁厚和承力分别检查。保留可编辑源，试模与成品共用接口参数，详见 `Context/cad-master-design.md`。

每次最终制作检查质量、可靠性、打印总时间、支撑、材料切换和后处理。记录实际切片比较，模板见 `Templates/Project/Review/x2d-final-review.md`。

打印授权绑定具体模型版本、切片文件、设备、材料与当次清板事实。使用 `printlab approve / submit / reconcile` 的同一任务记录。首次设置、建模、切片、测试均保持无设备动作。准备发送时先核对已有任务，结果不明先对账，避免重复发送。官方 Studio 路线见 `Context/official-studio-dispatch.md`。

设备完成后进入实物检查。使用者确认配合、外观、强度或使用体验后，再登记验收结果。

## 第三方来源与发布

遵循 `docs/DEPENDENCIES.md`。第三方代码、技能、权重、作者模型、应用及插件从原作者处独立取得，保留作者和原许可。PrintLab 自己的非商用许可仅覆盖原创代码和文档。发布模型是使用者另外提出的任务，逐件核对来源与许可。
