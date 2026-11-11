# 独立安装与验证 Bambu Studio

从拓竹官方获取适合本机系统的安装包。工作台自动发送助手当前匹配中文 `02.08.02.61`，本次离线切片验收也使用该版。其他版本需要重新核对配置和界面。[官方版本与下载](https://github.com/bambulab/BambuStudio/releases/tag/v02.08.02.61)

## 设置路径

Mac 将官方应用安装到自己的应用目录。默认路径为 `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio`，配置目录为应用内 `Contents/Resources/profiles`。

Windows 可使用官方安装程序或便携 ZIP。将 `Runtime/config.json` 的 `slicer_path` 设置为实际 `bambu-studio.exe`，`slicer_profiles_path` 设置为同一安装的 `resources/profiles`。路径中的空格可以保留，JSON 推荐使用正斜杠。

首次打开 Studio，按自己的打印机选择机型、喷嘴、耗材与打印板，并完成所选网络通道的连接。登录和网络插件按官方界面提示处理。之后运行 `printlab doctor`，核对它找到的路径。

## 完整配置与切片

官方配置包含继承和模板引用。使用 PrintLab 自带解析器，将实际安装中的目标配置解析到自己的项目目录，并保存其来源校验记录。

```bash
Runtime/venv/bin/python Harness/resolve_bambu_profiles.py '实际官方配置.json' --output '项目配置输出.json'
```

Windows 换用 `Runtime/venv/Scripts/python.exe`。分别解析机型、工艺和材料配置，保留 `.sources.json`，按真实设备修改必要的用户工艺参数。运行 `printlab slice --help` 查看当前参数，再对已完成尺寸和几何核查的项目试切片。

本版正式切片检查面向 X2D。其他机型应先实现和验证对应机型检查，再接入自动流程。切片包生成后，核对机型、喷嘴、板型、材料映射、估时和真实 G-code。具体发送步骤见打印指南。[打印与授权](PRINTING.md)

## 维护者离线验收

`Runtime/venv/bin/python scripts/verify_studio_install.py` 会从官方 Release 独立下载固定包并核对 SHA-256。Mac 只读挂载 DMG，Windows 解压官方便携 ZIP。应用使用临时数据目录，解析 X2D 官方配置，切片临时测试几何，验证真实 3MF、载料升温代码和公开检查器结果，完成后清理。

该测试使用 X2D 0.4 mm、PLA、纹理 PEI 和单盘。测试结果写入 `Runtime/verification/studio-install.json`，日志为 `studio-slicing.log`。切片过程在本机离线进行，Studio 登录、网络插件、真实设备选择与发送助手权限仍需在使用者环境核验。
