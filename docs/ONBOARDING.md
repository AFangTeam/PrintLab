# 首次配置与中断接续

主 Agent 负责首次配置，Mike 和 Sarah 接续同一个工作空间。先完成 `AGENT_START.md` 的安装与启动，然后运行 `printlab onboarding status --refresh`。其中 `version` 用于防止两个会话同时覆盖配置进度。所有示例的版本、哈希、项目 ID 和路径均替换为实际读回值。Windows 使用 `Harness/bin/printlab.ps1`。

## 收集已经存在的答案

先读 `printlab context`、`Context/team.md` 和现有宿主聊天。工作空间已有用户答案时，带原记录出处登记进度。向使用者只问尚缺的信息。系统、可用工具和服务端设备列表由 Agent 自行检查。

围绕这次使用收集三件事，每项用 `onboarding answer` 保存。用户原话保留在共享记录中。

```bash
./Harness/bin/printlab onboarding answer usage_goals --text '用户实际目标' --source '用户消息或已确认文档位置' --expect 0
./Harness/bin/printlab onboarding answer cloud_needs --text '用户现有 Handy、Studio 与云连接需要' --source '实际出处' --expect 1
```

接通后再询问其他库存，读回补录结果后保存 `additional_materials` 答案，并在文本里注明实际料卷 ID 或尚待补录的事实。每次写入后使用返回的新版本。设备的当前网络选择按 `CONNECTIONS.md` 处理。

## 核对设备与耗材

在用户的独立 Bambuddy 中接入设备，凭据放 `Runtime/private/bambuddy.json`，操作见 `BAMBUDDY_SETUP.md`。既有服务先读取配置。列表发现使用只读 API。

```bash
./Harness/bin/printlab onboarding discover
./Harness/bin/printlab workspace connection
./Harness/bin/printlab workspace connect --url http://127.0.0.1:8017 --printer-id 1 --expect-sha 当前配置哈希
./Harness/bin/printlab workspace show device
./Harness/bin/printlab onboarding adopt-device --expect-sha 当前设备卡哈希
./Harness/bin/printlab status
./Harness/bin/printlab materials
```

只有一台符合用户描述的设备时可直接采用，多台且用途不明确时询问目标。`adopt-device` 记录实际身份和读回时间，保留用户确认字段。历史路径 `Library/Devices/X2D/device.json` 可以保存用户自己的型号。出现身份冲突时核对旧设备与新选择。

按已安装官方 Studio 配置及用户实际设备核对可用空间、喷嘴、打印板与供料连接。软件模板的可选能力与现场已安装设备分别记录。通过 `workspace device --file 确认字段.json --source 事实出处 --expect-sha 当前哈希` 追加用户确认。文件示例如下，数值必须来自本机事实。

```bash
./Harness/bin/printlab workspace profiles --model 实际机型
./Harness/bin/printlab workspace profile --name '上一步实际列出的预设名称' --expect-sha 当前设备卡哈希
```

该入口解析已安装官方配置的继承与包含关系，保存来源哈希。打印空间从实际配置读取，已装喷嘴仍由设备读回或用户确认。Studio 更新导致来源变化时，项目约束提示重新核对。

```json
{"user_confirmed":{"model":"实际型号","build_plate_description":"实际打印板"}}
```

已装载材料从实时状态读取，其他现有料卷保存在 Bambuddy 库存。用户确认要登记一卷后使用 `material-intake`，支持材料、品牌、系列、颜色、产品号、存放位置及已知标签克数。需要该服务的 `inventory:read` 和 `inventory:update` 权限。首次权限不足时给出对应权限项，保留其他应用的凭据。

```json
{"material":"PLA","brand":"用户确认品牌","color_name":"白色","storage_location":"材料柜"}
```

```bash
./Harness/bin/printlab material-intake --file spool.json --source '用户确认拥有这一卷的原话与出处' --request-id 同一卷的稳定录入标识
```

先检查库存是否已有同一实物。两个真实料卷分别登记，外观相近不代表同一卷。请求标识在超时和接续时保持相同，命令会查回原操作标记。结果不明确时保留待对账状态。余量未知时保持未知，名义标签克数仅供账面估算。

## 自动建立两个独立聊天

先检查宿主当前实际可用的工具，写一份宿主能力 JSON。只有真实暴露且能使用的能力写 `true`。

```json
{
  "name":"实际宿主名称",
  "capabilities":{"local_files":true,"terminal":true,"chat_create":true,"chat_read":true},
  "evidence":"实际工具名称、参数帮助与本工作空间读取结果"
}
```

```bash
./Harness/bin/printlab onboarding host --file host.json --expect 当前版本
```

依次处理 Mike 与 Sarah。已有 Sara 视为 Sarah 的旧名称。先按实际工作空间搜索已有聊天并读回，核对 `Context/team.md` 中的历史入口。

1. 已有相符聊天时，读取它的工作空间、真实 ID 和首条介绍，通过下述回执加 `--adopt-existing` 登记。已有介绍不足时，在该聊天发送完整首次任务并等待回复。
2. 缺少角色时执行 `onboarding reserve-role Mike --request-id 稳定建立标识 --expect 当前版本`。只有返回 `create_allowed: true` 的这一执行者负责创建。
3. 由主 Agent 调用宿主真实创建工具，把返回的 `role.prompt` 作为首条任务，使用同一个绝对工作空间。Codex 宿主以当前工具帮助中的 `prompt` 和实际 project target 为准。脚本本身不具备聊天创建能力。
4. 取得最终真实 thread ID 后登记回执。宿主临时客户端 ID、仅有标题或计划文本不足以作为完成证据。
5. 等待并读回角色回复及文件读取记录，再补充 `first_reply` 和实际 `context_paths`。工作台达到 `introduced` 后显示它的介绍。
6. 通过带版本检查的 `workspace note team` 保存实际入口与验收结果。`onboarding.json` 保存机器可读的当前状态，team 文档保存说明及历史交接。

```json
{
  "request_id":"与预留相同的标识",
  "thread_id":"宿主实际聊天 ID",
  "host_id":"实际宿主与本地环境",
  "workspace":"与主会话完全一致的绝对根目录",
  "source":"宿主创建和读回结果的位置",
  "first_reply":"实际回复原文",
  "context_paths":["AGENTS.md","Context/profile.md","Context/workflow.md"]
}
```

```bash
./Harness/bin/printlab onboarding record-role Mike --file role-receipt.json --expect 当前版本
```

Sarah 用同样步骤完成。创建中断时 `creating` 会阻止重复创建，先用保存的 request ID 和工作空间在宿主找回结果。确定已有聊天后继续登记。缺少宿主工具时，工作台显示具体待办，提供角色提示词和工作空间路径供用户在支持环境继续。

## 共同事实与第一件作品

宿主明确返回创建失败且按建立标识搜索确认没有创建结果后，可用 `onboarding release-role 角色 --request-id 原标识 --evidence 宿主错误与搜索证据 --expect 当前版本` 解除未绑定预留，再重新建立。已有 thread ID 的绑定不能通过此入口解除。结果仍未知时继续查询宿主。

Mac 的 `Harness/bin/printlab` 是可直接执行的 shell 启动器，Windows 使用 PowerShell 启动器。它们会选择已安装环境。Python 直接入口为 `Runtime/venv/bin/python -m printlab.cli`，Windows 对应 `Runtime/venv/Scripts/python.exe -m printlab.cli`。

偏好、经验和队伍说明使用 `workspace show 名称` 读取哈希后，通过 `workspace note 名称 --text 内容 --source 出处 --request-id 稳定更新标识 --expect-sha 当前哈希` 追加。名称支持 `profile`、`taste`、`lessons`、`team`。文件尚无内容时用 `missing`。冲突后重读合并，重试同一更新使用同一请求标识。

结合用户用途、已有材料和设备给出少量简单作品方向。选定作品后查已有项目或创建稳定 ID，填写需求与已确认尺寸。生图前保存设备材料约束，进入 CAD 和切片前重读变化。

```bash
./Harness/bin/printlab constraints show 项目ID
./Harness/bin/printlab constraints capture 项目ID --source '此次需求与设备材料核对记录' --expect-sha missing
./Harness/bin/printlab context 项目ID
```

`manufacturing_context` 返回当前事实、已保存快照、缺项及变化来源。材料包含未装入 AMS 的库存，装载状态另读实时设备。离线时保留上次库存并标明时间。每次更新快照保留历史。用途、实测尺寸、保护接口写 `brief.md`，选图和同款三视图沿用 `design-target.json`，可编辑几何按 `CAD_SETUP.md` 接入 Text-to-CAD。

最终检查应覆盖真实模型与所选图、尺寸/壁厚/装配、材料适用性、当前打印板和供料路线。切片和自动发送的实际支持范围查询 `PRINTING.md` 与本机能力结果。具体打印继续沿用统一批准与任务回执。
