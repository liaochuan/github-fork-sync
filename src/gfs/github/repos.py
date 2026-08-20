import logging

import httpx

from gfs.core.models import RepoInfo, SkippedRepo
from gfs.github.client import GitHubClient

logger = logging.getLogger(__name__)


def list_forks(client: GitHubClient) -> tuple[list[RepoInfo], list[SkippedRepo]]:
    """返回 (forks, skipped)。

    forks: 成功获取 parent 信息的 fork 列表。
    skipped: 因详情端点失败或无 parent 而跳过的 fork，含跳过原因。
    """
    repos = client.get_all(
        "/user/repos", params={"per_page": 100, "type": "all"}
    )
    forks: list[RepoInfo] = []
    skipped: list[SkippedRepo] = []
    for repo in repos:
        if not repo.get("fork"):
            continue
        parent = repo.get("parent")
        if not parent:
            # /user/repos 列表端点不返回 parent，需调用详情端点补全
            try:
                detail = client.get(f"/repos/{repo['full_name']}")
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Skipping %s: unable to fetch details (HTTP %s)",
                    repo["full_name"],
                    e.response.status_code,
                )
                skipped.append(SkippedRepo(
                    full_name=repo["full_name"],
                    reason=f"无法获取详情 (HTTP {e.response.status_code})",
                ))
                continue
            parent = detail.get("parent")
            if not parent:
                skipped.append(SkippedRepo(
                    full_name=repo["full_name"],
                    reason="详情端点无 parent 字段",
                ))
                continue
            # 用详情端点的 default_branch 补全（列表端点可能不准）
            repo = detail
        forks.append(
            RepoInfo(
                full_name=repo["full_name"],
                default_branch=repo.get("default_branch", "main"),
                parent_full_name=parent["full_name"],
                parent_default_branch=parent.get(
                    "default_branch", "main"
                ),
                html_url=repo["html_url"],
            )
        )
    return forks, skipped
