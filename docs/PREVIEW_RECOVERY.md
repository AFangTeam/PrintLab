# 找回已有打印记录的模型预览

`printlab history-recover` 为 Bambuddy 已捕获的档案补图。指定设备后，工具逐页读取档案，匹配配置 ID 和明确板号，将 PNG 与关联表保存在当前工作空间。首次运行默认预演，检查报告后加 `--apply` 写入。

## 可用来源

| 系统 | 来源 | 当前支持范围 |
| --- | --- | --- |
| macOS | Studio 的 CFURL / WebKit 图片缓存 | 自动定位当前用户的 `~/Library/Caches/com.bambulab.bambu-studio`，也支持 `--cache-dir` 指定缓存根目录 |
| Windows / macOS | 本地 PNG 或 3MF 与绑定清单 | `--manifest` 读取明确绑定的设备、档案、配置和板号，从 3MF 提取指定板 PNG |
| 任意系统 | 从 Mac 复制的 CFURL / WebKit 缓存 | `--cache-dir` 读取上述已知格式；Windows 原生 Studio 缓存解析尚未实现 |

缓存可能已被清理、只有 URL 或缺少图片本体，工具会报告 `not_found`。只读取现存图片字节，联网请求限于配置的 Bambuddy 档案 GET 接口。账号旧打印历史与 MakerWorld 账号收藏导入已排除在本轮开发范围外。

## Mac 操作

先配置 Bambuddy 地址、专用读取凭据和设备 ID，按 [安装说明](SETUP.md) 完成基础连接。工作空间根目录执行以下命令。

```bash
./Harness/bin/printlab history --refresh
./Harness/bin/printlab history-recover
./Harness/bin/printlab history-recover --apply
./Harness/bin/printlab history --refresh
```

工具默认使用 `Runtime/config.json` 的 `printer_id`。多设备或缓存副本可显式指定。

```bash
./Harness/bin/printlab history-recover --printer-id 2 --cache-dir "/Volumes/Backup/Studio cache"
./Harness/bin/printlab history-recover --printer-id 2 --cache-dir "/Volumes/Backup/Studio cache" --apply
```

传入的目录应直接包含 `Cache.db` 或 `WebKit/NetworkCache/Version */Records`。版本目录自动枚举。数据库、缓存文件和 Studio 登录状态均保持原状。

旧脚本路径作为兼容入口保留，同样默认预演。

```bash
Runtime/venv/bin/python Harness/tools/recover_studio_covers.py --help
```

## Windows 与本地文件操作

从 Bambuddy 的对应档案确认 `id`、`printer_id`、`extra_data._print_data.raw_data.profile_id` 和 `plate_idx` 或 `plate_id`。清单中的数值须与档案完全一致。档案缺少配置 ID 或板号时，先寻找可核对的任务证据。相似标题不能用于绑定。

把下列内容保存为 `preview-bindings.json`。示例数值需要替换为自己的实际档案。文件相对路径以清单所在目录为基准，也支持本机绝对路径。Windows JSON 路径可以使用 `/`。

```json
{
  "schema_version": 1,
  "previews": [
    {
      "printer_id": 2,
      "archive_id": 8,
      "profile_id": "123",
      "plate": 2,
      "file": "models/my-slice.3mf"
    }
  ]
}
```

```powershell
.\Harness\bin\printlab.ps1 history-recover --printer-id 2 --manifest "D:/PrintLab files/preview-bindings.json"
.\Harness\bin\printlab.ps1 history-recover --printer-id 2 --manifest "D:/PrintLab files/preview-bindings.json" --apply
.\Harness\bin\printlab.ps1 history --refresh
```

PNG 同样通过 `file` 提供。只使用有明确配置和板号来源的模型图片。清单表达使用者确认的关联，工具无法独立证明外部文件就是当次打印文件，因此导入后显示“原模型参考”。已经由 PrintLab 任务和切片包准确关联的图片继续优先显示为“切片模型预览”。Studio 缓存图片显示“配置板预览”，对应公开配置和板号，当次改动与配色仍需实际切片文件核对。

## 报告与冲突处理

| 状态 | 含义与处理 |
| --- | --- |
| `ready` | 预演找到一个有效候选，可加 `--apply` 保存 |
| `recovered` | 图片与关联表已写入 |
| `existing` | 已有有效关联，重复执行保持原条目和时间 |
| `existing_unavailable` | 已有条目存在但匹配、图片或哈希校验失败，保留原条目供调查 |
| `missing_identity` | 档案缺少配置 ID 或明确板号，或两个板号字段冲突 |
| `not_found` | 没有可读取且匹配的图片 |
| `conflict` | 同一匹配出现不同图片内容，或目标文件内容冲突，保留空位供核对 |

`issues` 提供缺少缓存数据库、缺少 WebKit 记录、损坏图片、无法读取来源、模糊缓存记录和清单不匹配计数。先处理这些原因，再运行预演。报告省略签名 URL、原始缓存、账号令牌和本机来源路径。

已有 `recovered-previews.json` 的旧数字键继续读取。新条目使用 `printer_id:archive_id`，同一档案编号在不同设备间独立保存。写入使用跨进程锁、原子图片替换和原子 JSON 提交，重试可复用内容哈希图片。中途失败最多留下尚未被引用的图片，下一次恢复可继续。

冲突处理时先备份关联表并核对源证据。工具自动保留已有条目，包括原模型参考。修正关联表属于显式的数据维护操作。

## 复用给 Agent 的步骤

1. 核对当前工作空间、Bambuddy 设备 ID 和历史覆盖范围。
2. Mac 优先预演本机缓存。Windows 使用有明确档案关联的本地 PNG / 3MF 清单。
3. 检查缺失身份、冲突和读取失败，记录实际可恢复数量。
4. 在补图授权内执行 `--apply`，随后再次运行，核对 `written` 为零及已有记录保留情况。
5. 用 `history --refresh` 和工作台图册检查图片、标签与对应档案，分别记录恢复结果和未覆盖项。

原图和绑定表属于使用者的私人数据，位于 `Library/References/PrintHistory/`，发布 ZIP 只包含工具、说明与合成测试。
