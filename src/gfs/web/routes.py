import json
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from gfs.config import Settings
from gfs.core.service import ForkSyncService
from gfs.github.client import GitHubClient


class TokenManager:
    """运行时 token 管理器（仅内存，重启后丢失）。"""

    def __init__(self) -> None:
        self._token: str | None = None

    def get(self) -> str | None:
        return self._token

    def set(self, token: str) -> None:
        self._token = token

    def clear(self) -> None:
        self._token = None

    def is_authenticated(self) -> bool:
        return self._token is not None


def create_router(settings: Settings, token_manager: TokenManager) -> APIRouter:
    router = APIRouter()

    def _resolve_token() -> str:
        """优先使用运行时 token，其次 settings 中的 token。"""
        token = token_manager.get() or settings.github_token
        if not token:
            raise HTTPException(401, "Not authenticated")
        return token

    def _token_source() -> str:
        """返回当前 token 来源：'runtime'（登录页面输入）或 'env'（环境变量）。"""
        if token_manager.is_authenticated():
            return "runtime"
        return "env"

    def _service() -> ForkSyncService:
        return ForkSyncService(settings, token=_resolve_token())

    # ===== 认证端点 =====

    @router.get("/api/auth/check")
    async def auth_check():
        """检查是否已认证，并返回 token 来源。"""
        authenticated = token_manager.is_authenticated() or bool(
            settings.github_token
        )
        return {
            "authenticated": authenticated,
            "token_source": _token_source() if authenticated else None,
        }

    @router.post("/api/auth/login")
    async def auth_login(body: dict):
        """验证 token 并保存到内存。"""
        token = (body or {}).get("token", "").strip()
        if not token:
            raise HTTPException(400, "Token is required")

        # 验证 token 有效性
        try:
            client = GitHubClient(token=token, proxy=settings.proxy)
            user_data = client.get("/user")
            client.close()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 401:
                raise HTTPException(401, "Invalid token")
            raise HTTPException(code, f"GitHub API error: {code}")
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Network error: {e}")

        token_manager.set(token)
        return {
            "authenticated": True,
            "user": {
                "login": user_data.get("login"),
                "name": user_data.get("name"),
                "avatar_url": user_data.get("avatar_url"),
                "html_url": user_data.get("html_url"),
                "public_repos": user_data.get("public_repos"),
                "followers": user_data.get("followers"),
                "token_source": "runtime",
            },
        }

    @router.post("/api/auth/logout")
    async def auth_logout():
        """清除运行时 token。"""
        token_manager.clear()
        return {"authenticated": bool(settings.github_token)}

    @router.get("/api/user")
    async def get_user():
        """获取当前认证用户信息。"""
        token = _resolve_token()
        try:
            client = GitHubClient(token=token, proxy=settings.proxy)
            user_data = client.get("/user")
            client.close()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 401:
                raise HTTPException(401, "Token invalid or expired")
            raise HTTPException(code, f"GitHub API error: {code}")
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Network error: {e}")

        return {
            "login": user_data.get("login"),
            "name": user_data.get("name"),
            "avatar_url": user_data.get("avatar_url"),
            "html_url": user_data.get("html_url"),
            "public_repos": user_data.get("public_repos"),
            "followers": user_data.get("followers"),
            "token_source": _token_source(),
        }

    # ===== 页面 =====

    @router.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent / "static" / "index.html"
        return FileResponse(
            str(html_path),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    # ===== 数据端点 =====

    @router.get("/api/repos/basic")
    async def list_repos_basic():
        """快速返回 fork 列表和被跳过的仓库（不含 diff 信息），用于前端即时渲染。"""
        svc = _service()
        try:
            forks, skipped = svc.list_forks_with_skipped()
        finally:
            svc.close()
        return {
            "forks": [f.model_dump() for f in forks],
            "skipped": [s.model_dump() for s in skipped],
            "show_skipped": settings.show_skipped,
        }

    @router.get("/api/repos")
    async def list_repos():
        """并发获取所有 fork 的 diff 信息。"""
        svc = _service()
        try:
            diffs = await svc.diff_all_async()
        finally:
            svc.close()
        return [d.model_dump() for d in diffs]

    @router.get("/api/repos/stream")
    async def stream_repos():
        """SSE 流式推送：逐个推送 diff 结果。前端已通过 /api/repos/basic 获取列表。"""
        def generate():
            svc = _service()
            try:
                for diff in svc.diff_stream():
                    yield _sse_event("diff", diff.model_dump())
                yield _sse_event("done", {})
            finally:
                svc.close()

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/repos/{owner}/{repo}/diff")
    async def get_diff(owner: str, repo: str):
        full_name = f"{owner}/{repo}"
        svc = _service()
        try:
            forks = svc.list_forks()
            target = next((f for f in forks if f.full_name == full_name), None)
            if not target:
                raise HTTPException(404, f"fork '{full_name}' not found")
            return svc.diff(target).model_dump()
        finally:
            svc.close()

    @router.post("/api/repos/{owner}/{repo}/sync")
    async def sync_repo(owner: str, repo: str):
        full_name = f"{owner}/{repo}"
        svc = _service()
        try:
            forks = svc.list_forks()
            target = next((f for f in forks if f.full_name == full_name), None)
            if not target:
                raise HTTPException(404, f"fork '{full_name}' not found")
            result = svc.sync(target)
            return result.model_dump()
        finally:
            svc.close()

    @router.post("/api/sync-all")
    async def sync_all(body: dict | None = None):
        repos_to_sync = (body or {}).get("repos", [])
        svc = _service()
        try:
            results = []
            for diff in await svc.diff_all_async():
                if diff.behind_by > 0:
                    if not repos_to_sync or diff.repo.full_name in repos_to_sync:
                        results.append(svc.sync(diff.repo).model_dump())
            return results
        finally:
            svc.close()

    @router.post("/api/sync-stream")
    async def sync_stream(body: dict | None = None):
        """SSE 流式推送同步进度：逐个推送 (result, current, total)。"""
        repos_to_sync = (body or {}).get("repos", [])

        def generate():
            svc = _service()
            try:
                for result, current, total in svc.sync_stream(repos_to_sync):
                    yield _sse_event("progress", {
                        "result": result.model_dump(),
                        "current": current,
                        "total": total,
                    })
                yield _sse_event("done", {})
            finally:
                svc.close()

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router


def _sse_event(event: str, data: dict | list) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
