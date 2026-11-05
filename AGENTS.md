# AGENTS.md

## 项目定位

- Python >= 3.11，src-layout 包 `src/gfs`；同时提供 `gfs` CLI（Typer + Rich）和 FastAPI Web。
- 同步全部通过 GitHub REST API（`merge-upstream`）完成，不操作本地 git。
- 前端是单文件 `src/gfs/web/static/index.html`（原生 JS/CSS，无构建步骤）；必须通过 `gfs web` 访问，不能直接双击打开。
- README、UI 文案以中文为主，新增文案保持中文。

## 常用命令

```powershell
pip install -e ".[dev]"          # 仅依赖变化时需要重装，源码改动即时生效
pytest -q                        # 全量测试，本机约 3 分钟
pytest tests/unit/test_config.py -q
pytest -q --ignore=tests/integration/test_web_server.py   # 跳过慢的 Windows 回归测试
gfs web --config config.yaml
gfs list --config config.yaml
```

- 仓库没有配置 linter、formatter 或 typecheck（无 ruff、mypy 等），不要臆造命令。
- `tests/integration/test_web_server.py` 仅在 Windows 运行，会启动真实子进程并制造连接 RST，约 15 秒。
- 没有 CI 工作流；提交前在本地跑相关测试。

## 架构要点

- 调用链：CLI/Web → `ForkSyncService`（`core/service.py`）→ `GitHubClient` + `github/{repos,compare,sync}.py`。
- Web 每个请求新建一个 `ForkSyncService`，必须调用 `svc.close()` 释放 httpx 客户端。
- `GitHubClient` 是同步 httpx 客户端。`async` 路由和 `diff_all_async` 内部仍调用同步 HTTP，不会真正并行；不要假设加 `async` 就获得并发。
- SSE 端点 `/api/repos/stream`、`/api/sync-stream` 使用同步生成器 + `StreamingResponse`；事件名为 `diff` / `progress` / `done`，改前端时保持协议一致。
- Token 规则：CLI 启动时强制要求 `GITHUB_TOKEN`；Web 允许无 token 进入登录页。优先级为运行时登录 token > 环境变量 token，运行时 token 仅存内存。数据端点无 token 返回 401；登出不会清除环境变量 token。
- `web/server.py::run_server` 在 Windows 必须使用 `SelectorEventLoop`（规避 AcceptEx WinError 64 导致监听套接字关闭），有对应回归测试；不要简化成 `uvicorn.run` 或 `server.run`。

## 配置陷阱

- `config.yaml` 不会自动发现：只有显式传 `--config <path>` 才读取。Dockerfile 的 CMD 没有传，所以挂载的 `config.yaml` 实际不生效。
- 当前实现中，只要加载了配置文件，`load_settings` 就会把 `include` / `exclude` 置为 `[]`；`should_process` 将 `[]` 当作非空白名单，导致没写 `include` 的配置文件排除所有仓库（已复现）。修改这段逻辑时补上对应测试。
- 代理优先级：`config.yaml` 的 `proxy` > `HTTPS_PROXY` > `HTTP_PROXY`。
- `.env` 由 python-dotenv 从 `gfs/config.py` 所在目录向上查找；不要假设它一定读取当前工作目录的 `.env`。
- CLI 启动 Web 时 host 硬编码为 `127.0.0.1`，没有 `--host` 参数；容器部署不能依赖它监听外部接口。

## 打包与部署

- Dockerfile 复制 `src/` 后执行 `pip install .`。当前 wheel 不包含 `src/gfs/web/static/index.html`（缺少 package-data / MANIFEST 配置），非 editable 安装访问 `/` 会找不到前端；改动打包时先检查 wheel 内容。
- `core/service.py` 直接 `import anyio`，但 `anyio` 不是显式依赖（经 httpx/starlette 传递）；不要因此删掉这项依赖。
- 本地开发使用 editable 安装即可，源码改动无需重新安装。

## 测试约定

- 单元/集成测试用 `respx` mock `https://api.github.com`；不要发真实 GitHub 请求。
- CLI 测试通过 `monkeypatch.setenv("GITHUB_TOKEN", ...)` 提供 token；Web 测试用 `create_app(Settings(...))` + `TestClient`。
- 修改同步错误码、同步目标分支（上游默认分支同名）或 include/exclude 过滤时，同步更新 `tests/unit/test_sync.py`、`tests/unit/test_config.py` 和 `tests/integration/test_web.py`。
