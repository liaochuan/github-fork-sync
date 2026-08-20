# GitHub Fork Sync (gfs)

一个用于同步 GitHub fork 仓库与上游（upstream）的命令行与 Web 工具，支持同步前预览差异（落后/超前的 commit 列表及描述）。

## 功能特性

- **差异预览**：同步前展示 fork 相对上游落后和超出的 commit 数量及每条 commit 的描述、作者、日期
- **双向对比**：自动处理 GitHub compare API 的方向性，分别获取落后与超前的 commit
- **安全同步**：通过 GitHub `merge-upstream` API 执行同步，无需本地 git 操作
- **批量管理**：实时从 GitHub API 读取 fork 列表，支持 `config.yaml` 白名单/黑名单过滤
- **双模式交互**：
  - **CLI**：基于 Typer + Rich 的命令行界面，支持表格和 JSON 输出
  - **Web**：基于 FastAPI 的 Web 界面，支持可视化查看差异、单仓/批量同步
- **Token 可选**：Web 模式下 `GITHUB_TOKEN` 为可选 — 已配置则直接进入列表界面，未配置则显示登录页面供用户输入 Token（仅保存在服务端内存，重启后需重新登录）
- **用户信息展示**：Web 界面顶部右侧展示当前登录用户的头像、用户名（可点击跳转 GitHub）和登出按钮。通过环境变量注入 Token 时不显示登出按钮（无法登出环境变量）
- **SSE 流式加载**：Web 界面先即时渲染仓库列表，再通过 Server-Sent Events 逐个推送 diff 结果，避免长时间空白等待
- **同步进度可视化**：批量同步时展示进度条、百分比和逐条成功/失败日志
- **已跳过仓库展示**：因 HTTP 451 等原因无法获取详情的 fork 在页面右上角面板展示，含跳过原因（可通过配置关闭或点击关闭按钮临时隐藏，刷新后恢复）
- **刷新中状态**：同步成功后对应行显示"刷新中"样式（shimmer 动画 + 按钮禁用），后台刷新完成后自动恢复
- **状态筛选**：Web 界面支持下拉筛选落后/超前/分叉/同步/错误/刷新中等状态
- **错误提示**：error 状态的仓库，鼠标悬停在"错误"徽章上会显示具体错误信息（如"无共同祖先，无法与上游比较"）
- **422 自动重试**：同步时若分支名不匹配，自动用上游默认分支名重试；解析 GitHub 422 响应体展示真实错误（如 token 缺少 `workflow` scope）
- **错误处理**：针对 403（权限不足）、404（仓库不存在/无共同祖先）、409（冲突）、422（分支不匹配/workflow scope）等提供清晰错误提示
- **自动重试**：HTTP 客户端内置网络错误重试机制
- **网络代理**：支持 HTTP/HTTPS/SOCKS5 代理，优先级 `config.yaml` > `HTTPS_PROXY` > `HTTP_PROXY`
- **Docker 部署**：提供 Dockerfile，支持容器化构建部署

## 工作原理

1. **发现 fork**：调用 `GET /user/repos` 获取当前用户所有仓库，过滤出 `fork=true` 的仓库。由于该端点不返回 `parent`（上游）字段，对每个 fork 额外调用 `GET /repos/{owner}/{repo}` 详情端点补全上游信息。若详情获取失败（如 HTTP 451 法律限制），则跳过该仓库并记录到 skipped 列表（可在 Web 界面右上角面板查看）
2. **差异对比**：对每个 fork 调用 `GET /repos/{owner}/{repo}/compare/{base}...{head}`：
   - 正向调用（`upstream:branch...fork:branch`）获取 fork 超前的 commit（`ahead_commits`）
   - 当 `behind_by > 0` 时反向调用（`fork:branch...upstream:branch`）获取落后的 commit（`behind_commits`）
   - 若无共同祖先（HTTP 404），返回 `status="error"`，同步时自动跳过
3. **执行同步**：对落后的 fork 调用 `POST /repos/{owner}/{repo}/merge-upstream`，通过 GitHub 的 merge-upstream 机制将上游变更合并到 fork。若返回 422 且 fork 与上游默认分支名不同，自动用上游默认分支名重试

## 安装

### 前置要求

- Python >= 3.11
- GitHub Personal Access Token（需 `repo` 权限）
  - **CLI 模式**：必须通过 `.env` 或环境变量设置 `GITHUB_TOKEN`
  - **Web 模式**：可选 — 未设置时启动后显示登录页面，在页面输入 Token 即可

### 安装步骤

```powershell
# 克隆项目
git clone <repo-url>
cd github-fork-sync

# 安装（含开发依赖）
pip install -e ".[dev]"
```

安装后 `gfs` 命令即加入系统 PATH，可在任意目录使用。

### 更新

由于采用开发模式（`-e`）安装，源码修改后**无需重新安装**，直接运行即可生效。如需拉取最新代码：

```powershell
git pull
# 如有新增依赖，重新安装一次
pip install -e ".[dev]"
```

### 卸载

```powershell
# 卸载包（会移除 gfs 命令）
pip uninstall github-fork-sync

# 如需彻底清理，删除项目目录和配置文件
Remove-Item -Recurse -Force github-fork-sync   # Windows
rm -rf github-fork-sync                         # Linux/macOS
```

> **说明**：`pip uninstall` 仅移除 Python 包和 `gfs` 命令，不会删除项目源码和 `.env` / `config.yaml` 等配置文件，需手动清理。

### Docker 部署

项目提供 `Dockerfile`，支持以 Docker 方式构建和部署（仅 Web 模式）。

#### 构建镜像

```bash
docker build -t github-fork-sync .
```

#### 运行容器

> `GITHUB_TOKEN` 为可选 — 未设置时启动后显示登录页面，在页面输入 Token 即可。

```bash
# 方式一：通过环境变量设置 Token（直接进入列表界面）
docker run -d \
  --name gfs \
  -p 8000:8000 \
  -e GITHUB_TOKEN=ghp_your_token \
  -e HTTPS_PROXY=http://host.docker.internal:7890 \
  github-fork-sync

# 方式二：不设置 Token（启动后显示登录页面）
docker run -d \
  --name gfs \
  -p 8000:8000 \
  -e HTTPS_PROXY=http://host.docker.internal:7890 \
  github-fork-sync
```

浏览器访问 `http://localhost:8000` 即可使用 Web 界面。

#### 挂载配置文件

如需使用 `config.yaml`（白名单/黑名单/代理等），挂载到容器内：

```bash
docker run -d \
  --name gfs \
  -p 8000:8000 \
  -e GITHUB_TOKEN=ghp_your_token \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  github-fork-sync
```

#### 常用配置项

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-e GITHUB_TOKEN` | GitHub Personal Access Token（可选，未设置时显示登录页面） | — |
| `-e HTTPS_PROXY` | 网络代理（也可在 config.yaml 中配置） | — |
| `-p 8000:8000` | Web 服务端口映射 | 8000 |
| `-v config.yaml:/app/config.yaml:ro` | 挂载配置文件 | — |

> **代理注意**：容器内无法直接访问宿主机代理，需使用 `host.docker.internal`（Docker Desktop）或宿主机 IP（Linux）替代 `127.0.0.1`。

#### Docker Compose

也可使用 `docker-compose.yml`（需自行创建）：

```yaml
services:
  gfs:
    build: .
    ports:
      - "8000:8000"
    environment:
      # GITHUB_TOKEN 可选，未设置时启动后显示登录页面
      - GITHUB_TOKEN=ghp_your_token
      - HTTPS_PROXY=http://host.docker.internal:7890
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    restart: unless-stopped
```

```bash
docker compose up -d
```

## 配置

### 1. GitHub Token

> **Web 模式**：Token 为可选配置。若未设置，启动 Web 后会显示登录页面，在页面输入 Token 即可（仅保存在服务端内存，重启后需重新登录）。**CLI 模式**：Token 为必填。

创建 `.env` 文件（参考 `.env.example`）：

```
GITHUB_TOKEN=ghp_your_personal_access_token
```

或通过环境变量设置：

```powershell
# PowerShell
$env:GITHUB_TOKEN = "ghp_your_token"

# Linux/macOS
export GITHUB_TOKEN=ghp_your_token
```

**Token 获取方式**：GitHub → Settings → Access → Credentials → Fine-grained personal access tokens，勾选 `Contents: Read and write`、`Workflows: Read and write` 权限。

### 2. 配置文件（可选）

创建 `config.yaml` 进行仓库过滤和端口配置：

```yaml
# 白名单：仅处理列出的仓库（与 exclude 互斥，include 优先）
include:
  - my-user/project-a
  - my-user/project-b

# 黑名单：排除列出的仓库（当 include 未设置时生效）
exclude:
  - my-user/old-project

# Web 服务端口（默认 8000）
web_port: 8000

# 是否在页面展示被跳过的仓库（如 HTTP 451 等），默认 true
# show_skipped: false
```

**过滤规则**：
- 若设置 `include`，仅处理列表中的 fork
- 若设置 `exclude`，排除列表中的 fork
- 两者均未设置则处理所有 fork
- `include` 优先级高于 `exclude`

### 3. 网络代理（可选）

在国内访问 GitHub API 可能需要代理。支持两种配置方式：

**方式一：环境变量**（在 `.env` 文件中设置）

```
HTTPS_PROXY=http://127.0.0.1:7890
```

也支持 `HTTP_PROXY` 环境变量，`HTTPS_PROXY` 优先。

**方式二：配置文件**（在 `config.yaml` 中设置，优先级高于环境变量）

```yaml
proxy: http://127.0.0.1:7890
```

支持的代理协议：

```yaml
proxy: http://127.0.0.1:7890       # HTTP 代理
proxy: https://proxy.example.com   # HTTPS 代理
proxy: socks5://127.0.0.1:1080     # SOCKS5 代理
```

**优先级**：`config.yaml` 中的 `proxy` > 环境变量 `HTTPS_PROXY` > 环境变量 `HTTP_PROXY`

## 使用方式

### CLI 命令行

所有命令均支持 `--config` 指定自定义配置文件路径。

#### 列出所有 fork

```bash
gfs list
```

输出表格展示所有 fork 的仓库名、上游、默认分支和 URL。

```bash
gfs list --json
```

以 JSON 格式输出，便于脚本处理：

```json
[
  {
    "full_name": "my-user/project-a",
    "default_branch": "main",
    "parent_full_name": "original/project-a",
    "parent_default_branch": "main",
    "html_url": "https://github.com/my-user/project-a"
  }
]
```

#### 查看差异详情

```bash
gfs diff <owner/repo>
```

展示指定 fork 与上游的详细差异，包括：
- 同步状态（behind / ahead / identical / diverged）
- 落后的 commit 列表（同步后会合并进来）
- 超前的 commit 列表（fork 独有）

```bash
gfs diff my-user/project-a --json
```

JSON 输出示例：

```json
{
  "repo": { "full_name": "my-user/project-a", ... },
  "status": "behind",
  "behind_by": 2,
  "ahead_by": 0,
  "behind_commits": [
    {
      "sha": "abc1234",
      "message": "feat: add new feature",
      "author": "Alice",
      "date": "2026-08-15",
      "html_url": "https://github.com/o/r/commit/abc1234"
    }
  ],
  "ahead_commits": []
}
```

#### 同步单个 fork

```bash
gfs sync <owner/repo>
```

执行前会展示落后的 commit 列表并要求确认：

```
repo: my-user/project-a (default: main)
upstream: original/project-a (default: main)
status: behind  | behind: 2  | ahead: 0

落后的 2 个 commit：
  1. [abc1234] feat: add new feature  (2026-08-15, Alice)
  2. [def5678] fix: resolve bug  (2026-08-14, Bob)

确认同步？ [y/N]:
```

跳过确认直接同步：

```bash
gfs sync my-user/project-a --yes
# 或简写
gfs sync my-user/project-a -y
```

若 fork 已是最新（`behind_by == 0`），会提示并退出，不执行同步。

#### 启动 Web 界面

```bash
gfs web
```

启动 FastAPI Web 服务并自动打开浏览器。可选参数：

```bash
gfs web --port 9000              # 指定端口
gfs web --config my-config.yaml  # 指定配置文件
```

### Web 界面

Web 界面提供可视化的 fork 管理体验：

- **登录页面**：未配置 `GITHUB_TOKEN` 时显示，用户输入 GitHub Personal Access Token 登录（Token 仅保存在服务端内存，重启后需重新登录）。支持回车键登录，含 Token 创建链接和权限说明
- **用户信息栏**：页面顶部右侧展示当前登录用户的头像、用户名（可点击跳转 GitHub Profile）和登出按钮。通过环境变量注入 Token 时不显示登出按钮（无法登出环境变量）
- **SSE 流式加载**：先即时渲染仓库列表（状态显示"加载中"），再通过 Server-Sent Events 逐个推送 diff 结果，避免长时间空白等待
- **仓库列表**：表格展示所有 fork 的状态、落后/超前数量，仓库名和上游均为可点击链接
- **状态徽章**：颜色区分 `behind`（落后-黄）、`ahead`（超前-绿）、`diverged`（分叉-红）、`identical`（同步-蓝）、`error`（错误-红）、`loading`（加载中-灰）、`refreshing`（刷新中-灰）
- **错误提示**：error 状态的仓库，鼠标悬停在"错误"徽章上会显示具体错误信息（如"无共同祖先，无法与上游比较"）
- **状态筛选**：下拉框筛选指定状态的仓库（全部/落后/超前/分叉/同步/错误/加载中/刷新中）
- **查看差异**：点击"查看差异"展开行，显示落后和超前的 commit 详情（sha 徽章 + 描述 + 作者 + 日期）
- **单仓同步**：点击"同步"按钮同步单个 fork（自定义确认弹窗）
- **批量同步**：勾选多个仓库后点击"同步选中"批量同步，展示进度模态框（进度条 + 百分比 + 逐条成功/失败日志）
- **刷新中状态**：同步成功后对应行显示"刷新中"样式（shimmer 动画 + 按钮禁用），后台刷新完成后自动恢复
- **已跳过面板**：页面右上角可折叠面板，展示因 HTTP 451 等原因跳过的仓库及原因。面板标题栏含关闭按钮可临时隐藏（刷新后恢复），也可通过 `show_skipped: false` 永久关闭
- **自定义弹窗**：所有确认/提示使用自定义弹窗（带动画、SVG 图标），替代浏览器原生 alert/confirm

### API 接口

Web 模式同时提供 REST API，可供外部调用：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web 界面首页 |
| `GET` | `/api/auth/check` | 检查是否已认证 |
| `POST` | `/api/auth/login` | 验证 Token 并登录（body: `{"token": "ghp_xxx"}`） |
| `POST` | `/api/auth/logout` | 登出，清除运行时 Token |
| `GET` | `/api/user` | 获取当前认证用户信息 |
| `GET` | `/api/repos/basic` | 快速获取 fork 列表和被跳过的仓库（不含 diff），用于即时渲染 |
| `GET` | `/api/repos` | 获取所有 fork 及差异信息（并发） |
| `GET` | `/api/repos/stream` | SSE 流式推送 diff 结果（逐个） |
| `GET` | `/api/repos/{owner}/{repo}/diff` | 获取指定 fork 的差异详情 |
| `POST` | `/api/repos/{owner}/{repo}/sync` | 同步指定 fork |
| `POST` | `/api/sync-all` | 批量同步（body: `{"repos": ["owner/repo", ...]}`） |
| `POST` | `/api/sync-stream` | SSE 流式推送同步进度（逐个） |

> **认证说明**：数据端点（`/api/repos/*`、`/api/sync-*`）需要认证 — 优先使用登录页面输入的运行时 Token，其次使用环境变量中的 `GITHUB_TOKEN`。未认证时返回 `401`。

示例：

```bash
# 检查认证状态
curl http://127.0.0.1:8000/api/auth/check

# 登录（验证 Token 并保存到服务端内存）
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"token": "ghp_your_token"}'

# 获取当前用户信息
curl http://127.0.0.1:8000/api/user

# 获取 fork 列表（含被跳过的仓库）
curl http://127.0.0.1:8000/api/repos/basic

# 获取所有 fork 及差异
curl http://127.0.0.1:8000/api/repos

# 同步单个 fork
curl -X POST http://127.0.0.1:8000/api/repos/my-user/project-a/sync

# 批量同步
curl -X POST http://127.0.0.1:8000/api/sync-all \
  -H "Content-Type: application/json" \
  -d '{"repos": ["my-user/project-a", "my-user/project-b"]}'

# SSE 流式同步（逐个推送进度）
curl -X POST http://127.0.0.1:8000/api/sync-stream \
  -H "Content-Type: application/json" \
  -d '{"repos": ["my-user/project-a"]}'

# 登出
curl -X POST http://127.0.0.1:8000/api/auth/logout
```

## 错误处理

同步失败时会返回明确的错误信息：

| HTTP 状态码 | 含义 | 建议 |
|------------|------|------|
| 403 | 权限不足 | Token 需具备 `repo` 权限 |
| 404 | 仓库不存在或非 fork | 检查仓库名称 |
| 409 | 合并冲突 | fork 已分叉，需本地解决冲突 |
| 422 | 分支不匹配或 token 缺少 `workflow` scope | 检查分支名；若上游 commit 含 `.github/workflows/` 修改，需在 token 设置中勾选 `workflow` scope |

> **422 常见场景**：当上游 commit 包含 `.github/workflows/` 目录下的文件修改时，GitHub 要求 token 具备 `workflow` scope 才能同步。错误响应会解析 GitHub 返回的真实 message（如 `Validation failed: Could not synchronize: The token used does not have workflow access.`），帮助快速定位原因。

> **注意**：部分仓库可能因法律原因被 GitHub 限制访问（HTTP 451），此类仓库会在发现阶段自动跳过并记录到 skipped 列表，不影响其他 fork 的处理。Web 界面右上角面板可查看被跳过的仓库及原因。

## 项目结构

```
github-fork-sync/
├── src/gfs/
│   ├── cli/app.py            # Typer CLI 命令（list/diff/sync/web）
│   ├── web/
│   │   ├── app.py            # FastAPI 应用工厂
│   │   ├── routes.py         # API 路由定义（含 SSE 流式端点、TokenManager、认证端点）
│   │   └── static/index.html # Web 前端单页应用（登录页面、用户信息栏、SSE 流式加载、同步进度模态框、已跳过面板）
│   ├── core/
│   │   ├── models.py         # Pydantic 数据模型（RepoInfo/CommitInfo/DiffResult/SyncResult/SkippedRepo）
│   │   └── service.py        # 业务编排层（含 diff_stream/sync_stream/diff_all_async）
│   ├── github/
│   │   ├── client.py         # GitHub HTTP 客户端（分页、重试、代理）
│   │   ├── repos.py          # fork 仓库发现（含 skipped 收集）
│   │   ├── compare.py        # 差异对比（含 404 无共同祖先容错）
│   │   └── sync.py           # 同步执行（含 422 重试 + 真实错误解析）
│   └── config.py             # 配置加载（.env + config.yaml，含 show_skipped）
├── tests/
│   ├── unit/                 # 单元测试
│   └── integration/          # 集成测试（CLI、Web）
├── Dockerfile                # Docker 构建文件
├── .dockerignore             # Docker 构建排除
├── config.yaml               # 配置文件示例
├── .env.example              # 环境变量示例
└── pyproject.toml            # 项目配置
```

## 开发

### 运行测试

```bash
# 全量测试
pytest -v

# 带覆盖率
pytest -v --cov=gfs --cov-report=term-missing

# 运行特定测试
pytest tests/unit/test_service.py -v
pytest tests/integration/test_cli.py -v
```

### 技术栈

- **HTTP 客户端**：httpx（支持异步、HTTP/2）
- **CLI**：Typer + Rich
- **Web**：FastAPI + Uvicorn
- **数据模型**：Pydantic v2
- **配置**：python-dotenv + PyYAML
- **测试**：pytest + respx（HTTP mock）

## 许可证

MIT
