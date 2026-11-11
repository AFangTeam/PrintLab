# 独立安装 Text-to-CAD

PrintLab 不附带 Text-to-CAD 源码、插件或模型。其官方新版本使用 `cad`；作者原工作台的 0.8.2 使用过 `cadgen`，不要混用命令。以下固定 **cad-server 0.11.9**，从 PyPI 独立获取。该版本的宿主安装行为见 [上游安装指南](https://github.com/earthtojake/text-to-cad/blob/main/docs/install.md)。

## 在工作台之外保留独立工具环境

先完成 PrintLab 安装。在仓库根目录运行：

Mac：

```bash
Runtime/venv/bin/python -m venv Runtime/third-party/cad-bootstrap
Runtime/third-party/cad-bootstrap/bin/python -m pip install uv==0.10.7
Runtime/third-party/cad-bootstrap/bin/python -m uv tool run --no-config --managed-python --python 3.14 --from cad-server==0.11.9 cad setup --only codex --dry-run
```

Windows PowerShell：

```powershell
Runtime/venv/Scripts/python.exe -m venv Runtime/third-party/cad-bootstrap
Runtime/third-party/cad-bootstrap/Scripts/python.exe -m pip install uv==0.10.7
Runtime/third-party/cad-bootstrap/Scripts/python.exe -m uv tool run --no-config --managed-python --python 3.14 --from cad-server==0.11.9 cad setup --only codex --dry-run
```

检查计划，确认操作的是希望配置的 Codex。执行同一条最后命令，移除 `--dry-run`，即可安装；需要关闭遥测时加 `--no-telemetry`。不要对已有可用的个人插件盲目升级：上游安装器可能替换该宿主内的旧副本。按安装器提示重启宿主，再核实插件和技能实际出现。未检测到 Codex 时先处理宿主安装，不能宣称完成了插件接入。

安装后的共享入口在 Mac 为 `./Harness/bin/text2cad`，Windows 为 `powershell -NoProfile -ExecutionPolicy Bypass -File .\Harness\bin\text2cad.ps1`。两者优先查找 `cad`，兼容旧版 `cadgen`。PATH 尚未更新时，将 `PRINTLAB_CAD_COMMAND` 设置为安装器报告的可执行文件完整路径，再通过该入口运行 `--help`。路径可以包含空格。

## 验证顺序

1. 用安装生成的 `cad --help` 与 `cad doctor --check` 检查命令和服务。若 PATH 未刷新，使用安装器报告的实际可执行路径；PrintLab 的 `PRINTLAB_CAD_COMMAND` 可指定它。
2. 要求 Agent 在临时目录创建一个尺寸已知的简单测试体，用 `cad run` 构建，检查实体有效性、毫米尺寸和体积，并导出 STEP/STL。随后删除临时测试产物。命令存在不代表 CAD 内核已下载或能建模。
3. 在当前 Agent 宿主实际打开 CAD 查看器，核对模型及后续修改是否同步。终端建模通过不能代替宿主查看器验收。
4. 正式作品保留参数化源文件、输入与版本。PrintLab 的原生 build 仍是 CadQuery/Blender；Text-to-CAD 的 STEP 桥接需要单独准备 CadQuery 环境。几何 3MF 不是可直接发送的已切片包。

## Agent 环境的启动问题

如果提示沙箱不能自动启动引擎，使用获得相应权限的终端执行 `cad server` 并保持运行，再在同一安装环境运行 `cad run`。不要反复重装插件或停掉另一安装的服务。`cad doctor --check` 用于只读诊断；需要修复时先看具体错误。

本项目的 `scripts/verify_cad_install.py` 会独立下载上述版本，在临时状态、缓存、启动器目录与端口运行真实建模/导出，完成后关闭该测试服务；不安装到你的 Agent 宿主，不连接打印机，不把测试模型打包分享。运行方式为工作台 Python 加此脚本路径，诊断保存在 `Runtime/verification/cad-install.log`。首次运行需下载 CAD 内核，耗时和空间明显高于启动空工作台。
