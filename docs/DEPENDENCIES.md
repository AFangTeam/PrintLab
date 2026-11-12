# 第三方工具与独立安装

PrintLab 发布包保留原创工作台、流程、适配接口与项目模板。下面的程序、插件、源码、权重和技能由使用者从原作者渠道下载，各自遵守原许可。

| 项目 | 在流程中的作用 | 获取与版本说明 |
| --- | --- | --- |
| [Bambuddy](https://github.com/maziggy/bambuddy) | 设备、材料库存、队列与已捕获历史 | 按原项目安装指南独立运行。PrintLab 本地适配基线为 v1.2.5.7，当前上游接口需重新验证。通过独立 HTTP API 连接。 |
| [Text-to-CAD](https://github.com/earthtojake/text-to-cad) | Codex 建模、模型查看、导出与制造检查 | 按原项目 `docs/install.md` 安装。本地历史验证基线为 0.8.2，当前上游入口已使用 `cad`，以实际 `--help` 为准。 |
| [Bambu Studio](https://github.com/bambulab/BambuStudio) | 正式工程、切片与官方发送 | 从拓竹官方获取应用及其插件。首版发送助手的本地验证版本为 02.08.02.61。 |
| [Blender](https://www.blender.org/download/) | 有机外形、同源预览和动画视图 | 从官网安装。原工作流使用 Blender 4.5 系列，当前安装需检查导出接口。 |
| [CadQuery](https://github.com/CadQuery/cadquery) | 参数化结构和 STEP 桥接 | 在使用者虚拟环境中从 PyPI 安装。 |
| [build123d](https://github.com/gumyr/build123d) | Text-to-CAD 的参数化几何能力 | 按 Text-to-CAD 原项目环境要求独立取得。 |
| [bambu-printer-mcp](https://github.com/DMontgomery40/bambu-printer-mcp) | 独立离线切片检查；历史原生发送研究来源 | 安装脚本从 npm 独立下载固定 1.1.33，通过公开 MCP inspect_print_file 调用，不提供打印机凭据，不导入上游内部模块。历史原生发送仍不可用。 |
| [Hunyuan3D-Swift](https://github.com/ZimengXiong/Hunyuan3D-Swift) / [Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) | 可选图生外形候选 | 代码和模型权重分别从原作者取得并检查许可。`image3d` 保留本地适配源码，需要自行准备对应隔离环境和来源清单。 |

## 许可归属

核对过的上游许可包括 Text-to-CAD 的 MIT、Bambuddy 的 AGPL-3.0 和 bambu-printer-mcp 的 GPL-2.0。使用者应以自己下载版本的 LICENSE 为准。上游的许可与署名继续适用，PrintLab 的非商用许可只覆盖 PrintLab 原创部分。

旧原生客户端通过进程内载入 `bambu-printer-mcp` 内部模块工作。首版发布包移除了该客户端、上游补丁和相关运行环境，保留本项目的历史任务读回与独立检查逻辑。首版 `bambu_native` 发送返回明确的不可用原因，官方 Studio 工作流在 `PRINTING.md` 中说明。

## 工作台软件依赖

Python 包在 `Harness/pyproject.toml` 声明。网页依赖在 `Harness/studio/package.json` 与 `package-lock.json` 声明，包括 React、Three.js、Lucide、react-markdown 与 Vite。安装时由包管理器从 PyPI/npm 获取，下载的 `node_modules`、虚拟环境和构建产物保存在使用者本机。

## 升级方法

先阅读原项目新版本说明，在独立目录安装，验证 CLI/MCP、模型尺寸、导出和设备只读接口，再更新本机配置。保存实际版本和验证结果，已确认的打印任务继续绑定其原文件和参数。

## 独立检查器与版本锁

工作台安装脚本会运行 `scripts/install_inspector.py`，从 npm 独立获取检查器及依赖，保存于被 Git 忽略的 `Runtime/third-party/bambu-inspector`。仓库仅保存下载清单与完整性校验，不分发第三方源代码、插件或模型。检查器保留其 GPL-2.0 许可。需要单独重装时使用工作台虚拟环境的 Python 执行该脚本。

Python 依赖使用 `scripts/requirements.lock` 的版本和 SHA-256；前端与检查器分别使用自己的 package-lock.json。升级时更新锁文件并重跑跨平台验收，不能直接改为 latest。

Text-to-CAD 的固定版本、Mac/Windows 安装命令、宿主接入和最小建模验收见 [CAD 安装指南](CAD_SETUP.md)。
