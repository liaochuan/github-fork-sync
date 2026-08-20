import httpx
import pytest
import respx

from gfs.github.client import GitHubClient
from gfs.github.sync import sync_fork
from gfs.core.models import RepoInfo, SyncResult


@pytest.fixture
def client():
    return GitHubClient(token="ghp_test_token")


@pytest.fixture
def repo():
    return RepoInfo(
        full_name="me/project-a",
        default_branch="main",
        parent_full_name="original/project-a",
        parent_default_branch="main",
        html_url="https://github.com/me/project-a",
    )


@respx.mock
def test_sync_success(client, repo):
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "merge_type": "merge",
                "base_branch": "main",
                "head_branch": "main",
                "commit_message": "Merged upstream main into main",
            },
        )
    )
    result = sync_fork(client, repo)
    assert isinstance(result, SyncResult)
    assert result.success is True
    assert result.merge_type == "merge"
    assert result.error_code is None


@respx.mock
def test_sync_conflict(client, repo):
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(
            409,
            json={"message": "Merge conflict"},
        )
    )
    result = sync_fork(client, repo)
    assert result.success is False
    assert result.error_code == "409"
    assert "conflict" in result.message.lower()


@respx.mock
def test_sync_forbidden(client, repo):
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(
            403,
            json={"message": "Forbidden"},
        )
    )
    result = sync_fork(client, repo)
    assert result.success is False
    assert result.error_code == "403"


@respx.mock
def test_sync_not_found(client, repo):
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(
            404,
            json={"message": "Not Found"},
        )
    )
    result = sync_fork(client, repo)
    assert result.success is False
    assert result.error_code == "404"


@respx.mock
def test_sync_422_retry_with_parent_branch(client):
    """422 时应使用上游默认分支名重试。"""
    repo = RepoInfo(
        full_name="me/project-a",
        default_branch="master",
        parent_full_name="original/project-a",
        parent_default_branch="main",
        html_url="https://github.com/me/project-a",
    )
    route = respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    )
    route.mock(
        side_effect=[
            httpx.Response(422, json={"message": "Branch mismatch"}),
            httpx.Response(
                200,
                json={"merge_type": "merge", "commit_message": "ok"},
            ),
        ]
    )
    result = sync_fork(client, repo)
    assert result.success is True
    assert route.calls.last.request.content == b'{"branch":"main"}'


@respx.mock
def test_sync_422_no_retry_when_same_branch(client, repo):
    """fork 与上游分支名相同时 422 不重试，返回 GitHub 真实错误信息。"""
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(422, json={"message": "refusing to allow a Personal Access Token to create or update workflow without workflow scope"})
    )
    result = sync_fork(client, repo)
    assert result.success is False
    assert result.error_code == "422"
    assert "workflow" in result.message.lower()


@respx.mock
def test_sync_422_retry_both_fail(client):
    """两次重试都 422 应返回最后一次的 GitHub 错误信息。"""
    repo = RepoInfo(
        full_name="me/project-a",
        default_branch="master",
        parent_full_name="original/project-a",
        parent_default_branch="main",
        html_url="https://github.com/me/project-a",
    )
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(422, json={"message": "refusing to allow a Personal Access Token to create or update workflow without workflow scope"})
    )
    result = sync_fork(client, repo)
    assert result.success is False
    assert result.error_code == "422"
    assert "workflow" in result.message.lower()
