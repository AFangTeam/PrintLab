# 公开上传准备（按需）

本项目的 `record.json` 默认 `local_only`，不影响设计、收藏、私人打印或原有打印批准。

用户提出公开上传时，执行 `printlab publish init 项目 --kind original|remix|print_profile`，按 `<PRINTLAB_ROOT>/Library/Publishing/README.md` 保存全部来源许可、实质改动、上传文件与实拍证据，再执行 `publish check / prepare`。

检查结果是已核对、缺失或不允许，不适用项解释原因。任何核对通过仅表示可交用户审查；公开上传确认独立于设计/打印确认。当前工具只生成本地待审资料，没有自动上传能力。
