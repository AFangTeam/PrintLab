# 独立连接 Bambuddy

PrintLab 通过 HTTP API 读取独立运行的 Bambuddy。当前适配验证版本为 `v1.2.5.7`，源码提交 `188df76f8a7342542c0876dac68990ea2a8c8313`。请从原作者获取并按对应操作系统的安装方式运行。[官方安装说明](https://wiki.bambuddy.cool/getting-started/installation/)

## 首次连接

1. 打开自己的 Bambuddy 页面，先确认服务能独立访问。官方安装常用 `http://localhost:8000`，PrintLab 示例配置沿用 `http://127.0.0.1:8017`。将 `Runtime/config.json` 的 `bambuddy_url` 改成实际地址。
2. 按 Bambuddy 的添加打印机流程填写自己的设备信息，等待状态与材料读回。网络模式、固件与开发者模式按自己机型核对，具体路线见连接指南。[添加打印机](https://wiki.bambuddy.cool/getting-started/first-printer/) · [连接方式](CONNECTIONS.md)
3. 为 PrintLab 新建专用 API key，启用读取状态权限，用于设备、库存和 Bambuddy 已保存历史。填写到本机 `Runtime/private/bambuddy.json` 的 `read_api_key`。已有 API key、账号云登录、同步设置与其他应用权限按使用者现有用途保留。云访问和模型导入各自按实际功能配置，见 [同步排查](SYNC_TROUBLESHOOTING.md)。
4. 读取打印机 ID，写入 `Runtime/config.json` 的 `printer_id`。设备型号、喷嘴、打印板与实际供料路线写入设备档案。
5. 运行 `printlab status` 和 `printlab materials`。核对目标机器、在线状态、数据更新时间和槽位。首次连接结果写入自己的 `Library/Devices/X2D/installed.md`。

需要通过 Bambuddy 发送具体任务时，再按所选通道配置独立写入凭据。官方 Studio 通道的控制条件见打印指南。[打印能力](PRINTING.md)

## 可复现的接口验收

维护者可执行 `Runtime/venv/bin/python scripts/verify_bambuddy_install.py`，Windows 使用 `Runtime/venv/Scripts/python.exe`。脚本从原仓库下载上述版本，在临时虚拟环境安装服务端，使用独立数据库与本机随机端口，通过真实 PrintLab 客户端检查设备列表、库存、槽位、队列、历史与打印日志。

测试创建临时只读 key，验证后撤销，关闭服务并清理临时数据。结果和实际依赖版本写入 `Runtime/verification`。测试范围为服务端安装和空数据接口，前端安装、添加真实打印机及遥测读取需在使用者环境核对。
