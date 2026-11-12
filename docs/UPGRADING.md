# 更新、备份与回退

更新前记录当前 Release 标签和本机工具版本，结束文件编辑并停止工作台。正在打印或回执未知的任务，先保留记录并读取实际设备状态。

## 保存数据

在当前工作空间执行。Windows 将解释器换成 `Runtime/venv/Scripts/python.exe`。

```bash
Runtime/venv/bin/python Harness/backup.py backup --verify
```

成功结果包含快照位置、恢复验证目录和 `sha256: all_match`。备份含本机凭据，应存放在本人受限目录。该命令验证文件恢复和数据库完整性。Bambuddy 安装在工作空间外时，用 Bambuddy 自身备份功能另行保存它的数据。

另外保留当前版本的完整源码 ZIP。备份脚本只复制其清单列出的目录，环境和第三方安装需要按原版本重建。

## 升级

Git 用户先用 `git status --short` 检查自己修改过的源码与流程文档，保存修改后切换到选定 Release 标签，再运行安装脚本。ZIP 用户将新版解压到独立目录，保留旧目录，迁移 `Project`、个人 `Library`、`Runtime/config.json` 和 `Runtime/private`。将自己修改过的 `Context` 与新版逐项合并，保留设备档案和用户明确决定。

Mac 运行 `bash scripts/setup.sh`。Windows 运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1`。初始化会保留已有配置。然后执行 `doctor`、`context` 和 `scripts/verify_onboarding.py`，核对项目数量、最近交接、设备身份和材料读取。

升级前已批准的任务重新核对文件及设备。文件或材料映射变化时按当前任务重新确认。

## 回退

停止新版工作台，保存升级后新增的项目与任务记录。在独立目录解压旧版源码，用旧版安装脚本重建依赖。先恢复到备份验证目录并核对 SHA-256，再迁移相应数据，检查项目和设备连接。保留新版目录以便找回新增记录。

实际恢复前核对目标路径。Bambuddy 数据库恢复时停止该服务，按其官方恢复流程处理数据库及伴随文件。回退后运行 `doctor` 和只读状态检查，未知发送结果继续使用已有任务记录对账。

## 安装失败

- Python 版本不足时选择 Python 3.11+，使用 `PRINTLAB_PYTHON` 指向解释器后重跑安装。
- PyPI/npm 下载失败时保存错误类型和失败域名，恢复网络后重跑同一安装命令。
- 文件检查器失败时运行 `Runtime/venv/bin/python scripts/install_inspector.py`，Windows 换用对应解释器，再运行 `doctor`。
- 端口占用时核对已有服务。独立工作空间通过启动命令的 `--port` 选择端口。
- 设备读不到时依次核对 Bambuddy 页面、实际服务 URL、只读 key、打印机 ID 和网络模式。接口连接成功后，再核对实时数据时间与材料。

提交问题时使用仓库问题表单，附操作系统、Release、脱敏错误和复现步骤。凭据文件保留在本机。
