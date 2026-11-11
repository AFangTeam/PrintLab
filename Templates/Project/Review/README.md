# 实物复盘

每次打印单独记录：批次 ID、设计和切片版本、材料、喷嘴、方向、层高、设备回执、照片、尺寸偏差、配合/外观/支撑反馈、结论与下一步。照片必须来自真实成品。未验收前保持待检查。


## 打印前制作审查

每个最终模型按 `Context/x2d-final-review.md` 做一次制作Review，填写本目录 `x2d-final-review.md` 模板并保留实际模型/切片证据。模板未填写不算已审查，实物复盘与打印前审查分别记录。

## 每轮选图归档

每次比较图片并收到选择/反馈后，按 `Library/Taste/README.md` 用 `taste-choice.example.json` 的字段建立独立轮次记录，归档全部呈现候选，不只选中图；使用 `printlab taste record` 保存不可覆盖的图片快照。用户未说明理由留空；新反馈用于修正 `Context/taste.md`，不自动升格推测。

## 选图、改装与建模接续

默认按 `Context/image-to-print.md` v3先选外形、再从四套三视图中选一整套，随后建模、真实预览对照、配色与正式3MF。建模模型按 `Context/agent-policy.json` 与使用者当前可用环境选择。

已有模型改装填写 `remix-plan.md`；两次选择写 `design-target.json` 与 `design-reference.md`。`model-routing.md` 区分默认/计划与实际执行，实际模型读回证据另存 `model-routing.json`。模板存在不表示选型或检查已完成；当前项目已确认选择直接接续。

<!-- PRINTLAB_TEXT2CAD_TRIAL:BEGIN -->
## 参数化 CAD 接入

共享入口为仓库根目录的 `Harness/bin/text2cad`。先按 `docs/DEPENDENCIES.md` 独立安装并用当前 `--help` 核验，再填写 `text2cad-trial.md`。工具版本和几何检查结果来自本机实际执行，具体打印沿用 PrintLab 任务确认流程。
<!-- PRINTLAB_TEXT2CAD_TRIAL:END -->
