# 实物复盘

每次打印单独记录：批次 ID、设计和切片版本、材料、喷嘴、方向、层高、设备回执、照片、尺寸偏差、配合/外观/支撑反馈、结论与下一步。照片必须来自真实成品。未验收前保持待检查。


## 打印前制作审查

每个最终模型按 `Context/x2d-final-review.md` 做一次制作Review，填写本目录 `x2d-final-review.md` 模板并保留实际模型/切片证据。模板未填写不算已审查，实物复盘与打印前审查分别记录。

## 每轮选图归档

每次比较图片并收到选择/反馈后，按 `Library/Taste/README.md` 用 `taste-choice.example.json` 的字段建立独立轮次记录，归档全部呈现候选，不只选中图；使用 `printlab taste record` 保存不可覆盖的图片快照。用户未说明理由留空；新反馈用于修正 `Context/taste.md`，不自动升格推测。

## 选图、改装与建模接续

默认按 `Context/image-to-print.md` v3先选外形、再从四套三视图中选一整套，随后建模、真实预览对照、配色与正式3MF。建模默认GPT-6.1 Terra，策略见 `Context/agent-policy.json`。

已有模型改装填写 `remix-plan.md`；两次选择写 `design-target.json` 与 `design-reference.md`。`model-routing.md` 区分默认/计划与实际执行，实际模型读回证据另存 `model-routing.json`。模板存在不表示选型或检查已完成；当前项目已确认选择直接接续。

<!-- PRINTLAB_TEXT2CAD_TRIAL:BEGIN -->
## 参数化CAD试用（已配置，适合项目优先使用）

共享入口 `<PRINTLAB_ROOT>/Harness/bin/text2cad`；已安装text-to-cad 0.8.2且软件验证通过，调用前读 `Harness/Experiments/text2cad/USAGE.md` 与trial.json。填写 `text2cad-trial.md` 区分尺寸/干涉检查与实物结果。既有选型和Terra默认继续，插件不另行调度打印。
<!-- PRINTLAB_TEXT2CAD_TRIAL:END -->
