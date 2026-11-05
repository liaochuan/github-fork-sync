import json

import httpx

from gfs.core.models import RepoInfo, SyncResult
from gfs.github.client import GitHubClient

ERROR_MESSAGES = {
    409: "Merge conflict: fork has diverged, resolve locally",
    403: "Permission denied: token needs 'repo' scope",
    404: "Repository not found or not a fork",
}


def _extract_error_message(status_code: int, response: httpx.Response) -> str:
    """从 GitHub 错误响应中提取有意义的错误信息。"""
    try:
        body = response.json()
        msg = body.get("message", "")
        if msg:
            return msg
    except (json.JSONDecodeError, ValueError):
        pass
    if status_code in ERROR_MESSAGES:
        return ERROR_MESSAGES[status_code]
    return f"HTTP {status_code}: {response.text}"


def sync_fork(client: GitHubClient, repo: RepoInfo) -> SyncResult:
    # merge-upstream 只接受分支名，GitHub 会把上游同名分支合并进 fork 同名分支；
    # 因此目标分支名取上游默认分支，fork 的个人默认分支不参与同步。
    branch = repo.parent_default_branch

    try:
        data = client.post(
            f"/repos/{repo.full_name}/merge-upstream",
            json={"branch": branch},
        )
        return SyncResult(
            repo_full_name=repo.full_name,
            success=True,
            merge_type=data.get("merge_type"),
            message=data.get("commit_message", "Synced successfully"),
            error_code=None,
        )
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        message = _extract_error_message(code, e.response)
        return SyncResult(
            repo_full_name=repo.full_name,
            success=False,
            merge_type=None,
            message=message,
            error_code=str(code),
        )
