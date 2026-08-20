from collections.abc import AsyncIterator, Iterator

from anyio import create_task_group, Semaphore

from gfs.config import Settings
from gfs.core.models import DiffResult, RepoInfo, SkippedRepo, SyncResult
from gfs.github.client import GitHubClient
from gfs.github.compare import compare_fork
from gfs.github.repos import list_forks
from gfs.github.sync import sync_fork


class ForkSyncService:
    def __init__(
        self,
        settings: Settings,
        max_concurrency: int = 5,
        token: str | None = None,
    ):
        self.settings = settings
        self.max_concurrency = max_concurrency
        effective_token = token or settings.github_token
        if not effective_token:
            raise ValueError("No GitHub token available")
        self.client = GitHubClient(
            token=effective_token, proxy=settings.proxy
        )

    def list_forks_with_skipped(
        self,
    ) -> tuple[list[RepoInfo], list[SkippedRepo]]:
        """返回 (forks, skipped)，forks 已应用 include/exclude 过滤。"""
        all_forks, skipped = list_forks(self.client)
        forks = [
            f for f in all_forks if self.settings.should_process(f.full_name)
        ]
        return forks, skipped

    def list_forks(self) -> list[RepoInfo]:
        """仅返回过滤后的 forks 列表（兼容旧调用方）。"""
        forks, _ = self.list_forks_with_skipped()
        return forks

    def diff(self, repo: RepoInfo) -> DiffResult:
        return compare_fork(self.client, repo)

    def diff_all(self) -> list[DiffResult]:
        return [self.diff(repo) for repo in self.list_forks()]

    def diff_stream(self) -> Iterator[DiffResult]:
        """逐个 diff 并 yield，用于 SSE 流式推送。"""
        for repo in self.list_forks():
            yield self.diff(repo)

    async def diff_all_async(self) -> list[DiffResult]:
        """并发执行所有 fork 的 diff，按 list_forks 顺序返回结果。"""
        repos = self.list_forks()
        results: list[DiffResult | None] = [None] * len(repos)
        sem = Semaphore(self.max_concurrency)

        async def _diff_one(index: int, repo: RepoInfo) -> None:
            async with sem:
                results[index] = self.diff(repo)

        async with create_task_group() as tg:
            for i, repo in enumerate(repos):
                tg.start_soon(_diff_one, i, repo)

        return [r for r in results if r is not None]

    def sync(self, repo: RepoInfo) -> SyncResult:
        return sync_fork(self.client, repo)

    def sync_all(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        for diff in self.diff_all():
            if diff.behind_by > 0:
                results.append(self.sync(diff.repo))
        return results

    def sync_stream(
        self, repos_to_sync: list[str] | None = None
    ) -> Iterator[tuple[SyncResult, int, int]]:
        """逐个同步并 yield (result, current, total)，用于 SSE 流式推送进度。

        仅同步 behind_by > 0 的 fork。若 repos_to_sync 非空，还需在白名单内。
        total 在开始时计算（需先 diff_all），current 从 1 开始。
        """
        diffs = self.diff_all()
        candidates = [
            d for d in diffs
            if d.behind_by > 0
            and (not repos_to_sync or d.repo.full_name in repos_to_sync)
        ]
        total = len(candidates)
        for i, diff in enumerate(candidates, 1):
            yield self.sync(diff.repo), i, total

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
