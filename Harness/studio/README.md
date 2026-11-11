# PrintLab 网页工作台

React + Vite，读取本机 FastAPI 数据。生产启动使用仓库根目录 `scripts/start.sh`。

```bash
npm ci
npm run build
npm run dev
```

开发服务器将 `/api` 转发到本机 8018。新项目、库存与具体作品继续通过 Codex 和 PrintLab 共享命令保存，待打印页面提供绑定任务的确认流程。
