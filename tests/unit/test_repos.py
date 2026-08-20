import httpx
import pytest
import respx

from gfs.github.client import GitHubClient
from gfs.github.repos import list_forks
from gfs.core.models import RepoInfo, SkippedRepo


@pytest.fixture
def client():
    return GitHubClient(token="ghp_test_token")


def _repo_summary(name, fork, parent=None):
    """模拟 /user/repos 返回的精简仓库对象（不含 parent 详情）。"""
    repo = {
        "id": 1,
        "full_name": name,
        "fork": fork,
        "default_branch": "main",
        "html_url": f"https://github.com/{name}",
    }
    if parent is not None:
        repo["parent"] = parent
    return repo


def _repo_detail(name, parent_name, parent_branch="main"):
    """模拟 /repos/{owner}/{repo} 返回的完整仓库对象（含 parent 详情）。"""
    return {
        "id": 1,
        "full_name": name,
        "fork": True,
        "default_branch": "main",
        "html_url": f"https://github.com/{name}",
        "parent": {
            "full_name": parent_name,
            "default_branch": parent_branch,
        },
    }


@respx.mock
def test_list_forks_filters_non_fork(client):
    # /user/repos 不返回 parent，需额外调用 /repos/{owner}/{repo}
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                _repo_summary("me/project-a", fork=True),
                _repo_summary("me/my-own-repo", fork=False),
            ],
        )
    )
    respx.get("https://api.github.com/repos/me/project-a").mock(
        return_value=httpx.Response(
            200, json=_repo_detail("me/project-a", "original/project-a")
        )
    )
    forks, skipped = list_forks(client)
    assert len(forks) == 1
    assert isinstance(forks[0], RepoInfo)
    assert forks[0].full_name == "me/project-a"
    assert forks[0].parent_full_name == "original/project-a"
    assert skipped == []


@respx.mock
def test_list_forks_empty(client):
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[])
    )
    forks, skipped = list_forks(client)
    assert forks == []
    assert skipped == []


@respx.mock
def test_list_forks_uses_parent_from_list_when_present(client):
    # 如果 /user/repos 已返回 parent（某些情况），不再额外调用
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                _repo_summary(
                    "me/project-a",
                    fork=True,
                    parent={"full_name": "original/project-a", "default_branch": "main"},
                ),
            ],
        )
    )
    forks, skipped = list_forks(client)
    assert len(forks) == 1
    assert forks[0].parent_full_name == "original/project-a"
    assert skipped == []


@respx.mock
def test_list_forks_fetches_detail_when_parent_missing(client):
    # /user/repos 返回 fork=true 但无 parent，需调用 /repos/{owner}/{repo}
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[_repo_summary("me/orphan", fork=True)],
        )
    )
    respx.get("https://api.github.com/repos/me/orphan").mock(
        return_value=httpx.Response(
            200, json=_repo_detail("me/orphan", "original/orphan", "develop")
        )
    )
    forks, skipped = list_forks(client)
    assert len(forks) == 1
    assert forks[0].full_name == "me/orphan"
    assert forks[0].parent_full_name == "original/orphan"
    assert forks[0].parent_default_branch == "develop"
    assert skipped == []


@respx.mock
def test_list_forks_skips_when_detail_has_no_parent(client):
    # /repos 详情仍无 parent（异常情况），跳过该 fork
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[_repo_summary("me/weird", fork=True)],
        )
    )
    respx.get("https://api.github.com/repos/me/weird").mock(
        return_value=httpx.Response(
            200,
            json={
                "full_name": "me/weird",
                "fork": True,
                "default_branch": "main",
                "html_url": "https://github.com/me/weird",
            },
        )
    )
    forks, skipped = list_forks(client)
    assert forks == []
    assert len(skipped) == 1
    assert skipped[0].full_name == "me/weird"
    assert "parent" in skipped[0].reason


@respx.mock
def test_list_forks_skips_when_detail_fetch_fails(client):
    # /repos 详情端点返回错误（如 451 法律原因、404 等），跳过该 fork
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                _repo_summary("me/blocked", fork=True),
                _repo_summary("me/ok", fork=True),
            ],
        )
    )
    respx.get("https://api.github.com/repos/me/blocked").mock(
        return_value=httpx.Response(451, text="Unavailable for legal reasons")
    )
    respx.get("https://api.github.com/repos/me/ok").mock(
        return_value=httpx.Response(
            200, json=_repo_detail("me/ok", "original/ok")
        )
    )
    forks, skipped = list_forks(client)
    assert len(forks) == 1
    assert forks[0].full_name == "me/ok"
    assert len(skipped) == 1
    assert skipped[0].full_name == "me/blocked"
    assert "451" in skipped[0].reason
