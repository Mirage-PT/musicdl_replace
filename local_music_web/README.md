# 本地音乐管理 Web（local_music_web）

基于 musicdl 的本地音乐管理：选择文件夹 → 扫描本地音乐 → 批量搜索（QQ + 网易云）→ 选择最佳匹配 → 批量下载（覆盖原文件，命名：歌名-歌手.后缀名），支持断点继续。

## 技术栈

- **后端**：FastAPI，Python 3
- **前端**：Vite + React
- **库存储**：`local_music_web/libraries/*.json`

## 运行方式

以下命令请按顺序执行。

### 1. 安装依赖（只需执行一次）

若使用 Homebrew Python 3.12，需用虚拟环境（否则会报 externally-managed-environment）。在项目根目录执行：

```bash
cd /Users/mirage/Developer/musicdl_replace
bash local_music_web/setup_venv.sh
cd local_music_web/frontend && npm install
```

`setup_venv.sh` 会在项目下创建 `.venv` 并安装 musicdl 与后端依赖；`start.sh` 会自动使用 `.venv` 里的 uvicorn。

### 2. 启动 / 关闭（推荐）

**一键启动**（在项目根目录执行；前端日志会打在当前终端，**按 Ctrl+C 即关闭前后端**）：

```bash
cd /Users/mirage/Developer/musicdl_replace
bash local_music_web/start.sh
```

启动后访问 http://localhost:5173。需要关闭时在当前终端按 **Ctrl+C** 即可同时结束前后端。

若已用 start.sh 启动后又关掉了终端，可用 **一键关闭** 结束残留进程：

```bash
bash local_music_web/stop.sh
```

---

**手动分步启动**（可选）：

- 终端 1 后端：`cd 项目根 && uvicorn local_music_web.backend.main:app --reload --host 127.0.0.1 --port 8000`
- 终端 2 前端：`cd local_music_web/frontend && npm run dev`

浏览器打开 Vite 提供的地址（如 http://localhost:5173），前端会通过 Vite 代理将 `/api` 请求转发到后端 8000 端口。

### 4. 生产构建（可选）

```bash
cd local_music_web/frontend && npm run build
```

之后可从项目根目录用 uvicorn 挂载静态文件（见 `main.py` 中 `_frontend_dist`），或单独用 nginx 等托管前端并配置 API 代理。

## 使用流程

1. **选择文件夹**：点击「选择文件夹」，在弹窗中从根目录逐级进入，选好目录后点「选择当前文件夹」→ 后端扫描该路径下音频并建库。
2. **开始遍历搜索**：点击「开始遍历搜索」→ 按列表顺序逐首用 QQ 音乐 + 网易云各搜 3 条，结果自动排序（歌名+歌手完全匹配优先），可随时「暂停」「继续」。
3. **选择最佳匹配**：在右侧搜索结果中点击某条的「设为最佳」；再次点击可取消。每首歌只能有一个最佳。
4. **下载所有最佳选择**：点击「下载所有最佳选择」→ 只下载已选最佳且未下载的，覆盖原文件并重命名为 `歌名-歌手.后缀名`；支持暂停/继续，刷新页面后仍可继续。

状态灯：红=未搜索，绿=已搜索，蓝=已选择，紫=已下载，黄=错误。

## API 概览

- `GET /api/local/browse/roots`：获取浏览根目录（如 C:\、/）
- `GET /api/local/browse?path=...`：列出指定路径下的目录
- `POST /api/local/scan`：body `{ "path": "..." }`，扫描并创建/更新库
- `GET /api/local/library-state?library_id=...`：获取库完整状态
- `GET /api/local/library-list`：库列表
- `POST /api/local/search-control`：body `{ "library_id", "action": "start"|"pause"|"continue" }`
- `POST /api/local/select-choice`：设置/取消最佳匹配
- `POST /api/local/download-control`：下载任务控制
- `POST /api/local/reset-downloads`：重置已下载状态
- `GET /api/local/stream?library_id=...&song_id=...`：流式播放本地歌曲
