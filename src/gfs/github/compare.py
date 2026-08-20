import logging

import httpx

from gfs.core.models import CommitInfo, DiffResult, RepoInfo
from gfs.github.client import GitHubClient

logger = logging.getLogger(__name__)


def compare_fork(client: GitHubClient, repo: RepoInfo) -> DiffResult:
    base = f"{repo.parent_full_name.split('/')[0]}:{repo.parent_default_branch}"
    head = repo.default_branch

    try:
        forward = client.get(
            f"/repos/{repo.full_name}/compare/{base}...{head}"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(
                "compare %s: no common ancestor with upstream, skipping",
                repo.full_name,
            )
            return DiffResult(
                repo=repo,
                status="error",
                behind_by=0,
                ahead_by=0,
                behind_commits=[],
                ahead_commits=[],
                error_message="无共同祖先，无法与上游比较",
            )
        raise

    status = forward["status"]
    behind_by = forward["behind_by"]
    ahead_by = forward["ahead_by"]
    ahead_commits = _parse_commits(forward.get("commits", []))

    behind_commits: list[CommitInfo] = []
    if behind_by > 0:
        reverse = client.get(
            f"/repos/{repo.full_name}/compare/{head}...{base}"
        )
        behind_commits = _parse_commits(reverse.get("commits", []))

    return DiffResult(
        repo=repo,
        status=status,
        behind_by=behind_by,
        ahead_by=ahead_by,
        behind_commits=behind_commits,
        ahead_commits=ahead_commits,
    )


def _parse_commits(commits: list[dict]) -> list[CommitInfo]:
    result: list[CommitInfo] = []
    for c in commits:
        commit_data = c.get("commit", {})
        author_data = commit_data.get("author", {})
        result.append(
            CommitInfo(
                sha=c.get("sha", ""),
                message=commit_data.get("message", "").split("\n")[0],
                author=author_data.get("name", "unknown"),
                date=author_data.get("date", ""),
                html_url=c.get("html_url", ""),
            )
        )
    return result
