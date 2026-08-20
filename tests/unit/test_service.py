import anyio
import httpx
import pytest
import respx

from gfs.config import Settings
from gfs.core.service import ForkSyncService
from gfs.core.models import DiffResult, SyncResult


@pytest.fixture
def settings():
    return Settings(github_token="ghp_test_token")


def _fork_json(name="me/project-a", parent="original/project-a"):
    return {
        "id": 1,
        "full_name": name,
        "fork": True,
        "default_branch": "main",
        "html_url": f"https://github.com/{name}",
        "parent": {
            "full_name": parent,
            "default_branch": "main",
        },
    }


@respx.mock
def test_list_forks_applies_filter(settings):
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                _fork_json("me/project-a"),
                _fork_json("me/project-b"),
            ],
        )
    )
    settings.include = ["me/project-a"]
    svc = ForkSyncService(settings)
    forks = svc.list_forks()
    assert len(forks) == 1
    assert forks[0].full_name == "me/project-a"
    svc.close()


@respx.mock
def test_diff_all(settings):
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[_fork_json()])
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "behind",
                "behind_by": 1,
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
                "ahead_by": 1,
                "commits": [
                    {
                        "sha": "abc",
                        "commit": {
                            "message": "upstream",
                            "author": {"name": "A", "date": "2026-08-15"},
                        },
                        "html_url": "https://github.com/o/r/commit/abc",
                    }
                ],
            },
        )
    )
    svc = ForkSyncService(settings)
    diffs = svc.diff_all()
    assert len(diffs) == 1
    assert isinstance(diffs[0], DiffResult)
    assert diffs[0].behind_by == 1
    svc.close()


@respx.mock
def test_sync_all_only_behind(settings):
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[_fork_json()])
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"status": "behind", "behind_by": 1, "ahead_by": 0, "commits": []},
        )
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/main...original:main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"status": "ahead", "behind_by": 0, "ahead_by": 1, "commits": []},
        )
    )
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"merge_type": "merge", "commit_message": "ok"},
        )
    )
    svc = ForkSyncService(settings)
    results = svc.sync_all()
    assert len(results) == 1
    assert results[0].success is True
    svc.close()


@respx.mock
def test_sync_all_skips_identical(settings):
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[_fork_json()])
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"status": "identical", "behind_by": 0, "ahead_by": 0, "commits": []},
        )
    )
    svc = ForkSyncService(settings)
    results = svc.sync_all()
    assert results == []
    svc.close()


@respx.mock
def test_diff_all_async(settings):
    """diff_all_async 应并发执行并返回与 diff_all 相同顺序的结果。"""
    forks = [_fork_json("me/proj-a", "orig/proj-a"), _fork_json("me/proj-b", "orig/proj-b")]
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=forks)
    )
    for name, parent in [("me/proj-a", "orig/proj-a"), ("me/proj-b", "orig/proj-b")]:
        respx.get(
            f"https://api.github.com/repos/{name}/compare/{parent.split('/')[0]}:main...main"
        ).mock(
            return_value=httpx.Response(
                200, json={"status": "behind", "behind_by": 2, "ahead_by": 0, "commits": []}
            )
        )
        respx.get(
            f"https://api.github.com/repos/{name}/compare/main...{parent.split('/')[0]}:main"
        ).mock(
            return_value=httpx.Response(
                200, json={"status": "ahead", "behind_by": 0, "ahead_by": 1, "commits": []}
            )
        )
    svc = ForkSyncService(settings, max_concurrency=2)
    diffs = anyio.run(svc.diff_all_async)
    assert len(diffs) == 2
    assert diffs[0].repo.full_name == "me/proj-a"
    assert diffs[1].repo.full_name == "me/proj-b"
    assert all(d.behind_by == 2 for d in diffs)
    svc.close()


@respx.mock
def test_diff_stream(settings):
    """diff_stream 应逐个 yield DiffResult。"""
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[_fork_json()])
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200, json={"status": "behind", "behind_by": 1, "ahead_by": 0, "commits": []}
        )
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/main...original:main"
    ).mock(
        return_value=httpx.Response(
            200, json={"status": "ahead", "behind_by": 0, "ahead_by": 1, "commits": []}
        )
    )
    svc = ForkSyncService(settings)
    diffs = list(svc.diff_stream())
    assert len(diffs) == 1
    assert diffs[0].behind_by == 1
    svc.close()


@respx.mock
def test_sync_stream(settings):
    """sync_stream 应 yield (result, current, total)。"""
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[_fork_json()])
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/original:main...main"
    ).mock(
        return_value=httpx.Response(
            200, json={"status": "behind", "behind_by": 1, "ahead_by": 0, "commits": []},
        )
    )
    respx.get(
        "https://api.github.com/repos/me/project-a/compare/main...original:main"
    ).mock(
        return_value=httpx.Response(
            200, json={"status": "ahead", "behind_by": 0, "ahead_by": 1, "commits": []},
        )
    )
    respx.post(
        "https://api.github.com/repos/me/project-a/merge-upstream"
    ).mock(
        return_value=httpx.Response(
            200, json={"merge_type": "merge", "commit_message": "ok"},
        )
    )
    svc = ForkSyncService(settings)
    results = list(svc.sync_stream(["me/project-a"]))
    assert len(results) == 1
    result, current, total = results[0]
    assert result.success is True
    assert current == 1
    assert total == 1
    svc.close()


def test_service_with_runtime_token():
    """ForkSyncService 接受运行时 token 覆盖 settings 中的 token。"""
    settings_no_token = Settings(github_token=None)
    svc = ForkSyncService(settings_no_token, token="ghp_runtime_token")
    assert svc.client._client.headers["Authorization"] == "Bearer ghp_runtime_token"
    svc.close()


def test_service_no_token_raises():
    """无 token 时 ForkSyncService 抛出 ValueError。"""
    settings_no_token = Settings(github_token=None)
    with pytest.raises(ValueError, match="No GitHub token"):
        ForkSyncService(settings_no_token)
