import json
import logging

import httpx

from gfs.core.models import RepoInfo, SyncResult
from gfs.github.client import GitHubClient

logger = logging.getLogger(__name__)

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
    branches_to_try = [repo.default_branch]
    if repo.parent_default_branch != repo.default_branch:
        branches_to_try.append(repo.parent_default_branch)

    for branch in branches_to_try:
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
            if code == 422 and branch != branches_to_try[-1]:
                logger.info(
                    "sync %s: branch '%s' failed with 422, retrying with '%s'",
                    repo.full_name,
                    branch,
                    branches_to_try[-1],
                )
                continue
            message = _extract_error_message(code, e.response)
            return SyncResult(
                repo_full_name=repo.full_name,
                success=False,
                merge_type=None,
                message=message,
                error_code=str(code),
            )
    return SyncResult(
        repo_full_name=repo.full_name,
        success=False,
        merge_type=None,
        message="Branch mismatch: check default branch",
        error_code="422",
    )
