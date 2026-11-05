import httpx
import pytest
import respx

from gfs.github.client import GitHubClient
from gfs.github.compare import compare_fork
from gfs.core.models import RepoInfo, DiffResult


@pytest.fixture
def client():
    return GitHubClient(token="ghp_test_token")


@pytest.fixture
def repo():
    return RepoInfo(
        full_name="me/project-a",
        default_branch="mine",
        parent_full_name="original/project-a",
        parent_default_branch="main",
        html_url="https://github.com/me/project-a",
    )


def _commit(sha, msg, author="Alice", date="2026-08-15T10:00:00Z"):
    return {
        "sha": sha,
        "commit": {
            "message": msg,
            "author": {"name": author, "date": date},
        },
        "html_url": f"https://github.com/o/r/commit/{sha}",
    }


@respx.mock
def test_compare_identical(client, repo):
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "identical",
                "behind_by": 0,
                "ahead_by": 0,
                "commits": [],
            },
        )
    )
    result = compare_fork(client, repo)
    assert result.status == "identical"
    assert result.behind_by == 0
    assert result.ahead_by == 0
    assert result.behind_commits == []
    assert result.ahead_commits == []


@respx.mock
def test_compare_ahead_only(client, repo):
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ahead",
                "behind_by": 0,
                "ahead_by": 2,
                "commits": [
                    _commit("aaa", "my change 1"),
                    _commit("bbb", "my change 2"),
                ],
            },
        )
    )
    result = compare_fork(client, repo)
    assert result.status == "ahead"
    assert result.behind_by == 0
    assert result.ahead_by == 2
    assert len(result.ahead_commits) == 2
    assert result.ahead_commits[0].sha == "aaa"
    assert result.ahead_commits[0].message == "my change 1"
    assert result.behind_commits == []


@respx.mock
def test_compare_behind_only(client, repo):
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "behind",
                "behind_by": 3,
                "ahead_by": 0,
                "commits": [],
            },
        )
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/main...original:main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ahead",
                "behind_by": 0,
                "ahead_by": 3,
                "commits": [
                    _commit("ccc", "upstream 1"),
                    _commit("ddd", "upstream 2"),
                    _commit("eee", "upstream 3"),
                ],
            },
        )
    )
    result = compare_fork(client, repo)
    assert result.status == "behind"
    assert result.behind_by == 3
    assert result.ahead_by == 0
    assert len(result.behind_commits) == 3
    assert result.behind_commits[0].sha == "ccc"
    assert result.behind_commits[0].message == "upstream 1"
    assert result.ahead_commits == []


@respx.mock
def test_compare_diverged(client, repo):
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "diverged",
                "behind_by": 2,
                "ahead_by": 1,
                "commits": [_commit("aaa", "my change")],
            },
        )
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/main...original:main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ahead",
                "behind_by": 0,
                "ahead_by": 2,
                "commits": [
                    _commit("ccc", "upstream 1"),
                    _commit("ddd", "upstream 2"),
                ],
            },
        )
    )
    result = compare_fork(client, repo)
    assert result.status == "diverged"
    assert result.behind_by == 2
    assert result.ahead_by == 1
    assert len(result.behind_commits) == 2
    assert len(result.ahead_commits) == 1
    assert result.ahead_commits[0].sha == "aaa"


@respx.mock
def test_compare_no_common_ancestor(client, repo):
    # fork 与上游无共同祖先（如上游被重建），compare API 返回 404
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            404,
            json={
                "message": "No common ancestor between original:main and main.",
            },
        )
    )
    result = compare_fork(client, repo)
    assert result.status == "error"
    assert result.behind_by == 0
    assert result.ahead_by == 0
    assert result.behind_commits == []
    assert result.ahead_commits == []
    assert result.error_message == "无法对比：上游默认分支与 fork 同名分支 'main' 无共同祖先，或 fork 中不存在该分支"
