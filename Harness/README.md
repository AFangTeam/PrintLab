# PrintLab Harness

统一命令为仓库根目录的 `./Harness/bin/printlab`。首次安装见 `../docs/SETUP.md`。

```bash
./Harness/bin/printlab --help
./Harness/bin/printlab doctor
./Harness/bin/printlab context
./Harness/bin/printlab new '作品名称' --kind functional --brief '用途、尺寸与完成标准'
./Harness/bin/printlab context P001
```

使用当前子命令帮助查看参数。源码包含项目、版本、建模、切片、设计选择、正式 3MF、材料、购物清单、历史、待打印、官方发送和实物复盘。

FastAPI 服务由 `scripts/start.sh` 启动，React 页面由 `studio/` 构建。数据根目录默认当前仓库，Python 接口可用 `PRINTLAB_ROOT` 指定隔离工作空间。网页静态资源来自该工作空间的 `Harness/studio/dist`。

`Runtime/config.json` 存本机工具和服务路径，`Runtime/private/` 存凭据。独立第三方程序从原作者处安装，来源见 `../docs/DEPENDENCIES.md`。历史原生发送客户端在首版中不可用，当前打印路线见 `../docs/PRINTING.md`。
