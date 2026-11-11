# macOS 窗口与发送助手

需要 macOS 14+ 和 Xcode Command Line Tools。

运行 `zsh Harness/macos/build.sh` 构建 PrintLab 窗口，产物在 `Runtime/macos-build/PrintLab.app`。构建时写入本机实际工作空间路径，启动后访问本机 8018 服务。先运行 `scripts/start.sh`。

`StudioBridge.swift` 是单独的发送助手源码，使用 `printlab studio-bridge --help` 查看安装与权限命令。许可和支持范围见 `docs/PRINTING.md`。构建或申请权限本身不会生成具体打印授权。
