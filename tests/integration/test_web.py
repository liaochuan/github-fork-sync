import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from gfs.config import Settings
from gfs.web.app import create_app


def _fork_json(name="me/project-a", parent="original/project-a"):
    return {
        "id": 1,
        "full_name": name,
        "fork": True,
        "default_branch": "main",
        "html_url": f"https://github.com/{name}",
        "parent": {"full_name": parent, "default_branch": "main"},
    }


def _user_json(login="testuser"):
    return {
        "login": login,
        "name": "Test User",
        "avatar_url": "https://avatars.githubusercontent.com/u/1",
        "html_url": f"https://github.com/{login}",
        "public_repos": 10,
        "followers": 5,
    }


@pytest.fixture
def client():
    settings = Settings(github_token="ghp_test_token")
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def no_token_client():
    """无 token 的客户端，用于测试登录流程。"""
    settings = Settings(github_token=None)
    app = create_app(settings)
    return TestClient(app)


@respx.mock
def test_auth_check_with_token(client):
    """settings 中有 token 时，auth/check 返回 authenticated=True, token_source='env'。"""
    resp = client.get("/api/auth/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["token_source"] == "env"


@respx.mock
def test_auth_check_without_token(no_token_client):
    """无 token 时，auth/check 返回 authenticated=False, token_source=None。"""
    resp = no_token_client.get("/api/auth/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False
    assert data["token_source"] is None


@respx.mock
def test_auth_check_token_source_runtime(no_token_client):
    """登录后 token_source 变为 'runtime'。"""
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json=_user_json())
    )
    no_token_client.post("/api/auth/login", json={"token": "ghp_new_token"})
    resp = no_token_client.get("/api/auth/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["token_source"] == "runtime"


@respx.mock
def test_auth_login_success(no_token_client):
    """登录成功后 token 保存到内存，后续请求可用。"""
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json=_user_json())
    )
    resp = no_token_client.post(
        "/api/auth/login", json={"token": "ghp_new_token"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["user"]["login"] == "testuser"
    assert data["user"]["avatar_url"] == "https://avatars.githubusercontent.com/u/1"
    assert data["user"]["token_source"] == "runtime"


@respx.mock
def test_auth_login_invalid_token(no_token_client):
    """无效 token 登录返回 401。"""
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(401, json={"message": "Bad credentials"})
    )
    resp = no_token_client.post(
        "/api/auth/login", json={"token": "invalid_token"}
    )
    assert resp.status_code == 401


@respx.mock
def test_auth_login_empty_token(no_token_client):
    """空 token 登录返回 400。"""
    resp = no_token_client.post("/api/auth/login", json={"token": ""})
    assert resp.status_code == 400


@respx.mock
def test_auth_logout(no_token_client):
    """登出后清除运行时 token。"""
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json=_user_json())
    )
    no_token_client.post("/api/auth/login", json={"token": "ghp_new_token"})
    resp = no_token_client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False


@respx.mock
def test_api_user(client):
    """获取当前用户信息，token_source='env'。"""
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json=_user_json())
    )
    resp = client.get("/api/user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == "testuser"
    assert data["avatar_url"] == "https://avatars.githubusercontent.com/u/1"
    assert data["token_source"] == "env"


@respx.mock
def test_data_endpoint_without_token_returns_401(no_token_client):
    """无 token 时访问数据端点返回 401。"""
    resp = no_token_client.get("/api/repos/basic")
    assert resp.status_code == 401


@respx.mock
def test_get_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@respx.mock
def test_api_repos_basic(client):
    """basic 端点返回 { forks, skipped }，不调用 compare。"""
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[_fork_json()])
    )
    resp = client.get("/api/repos/basic")
    assert resp.status_code == 200
    data = resp.json()
    assert "forks" in data
    assert "skipped" in data
    assert len(data["forks"]) == 1
    assert data["forks"][0]["full_name"] == "me/project-a"
    assert data["forks"][0]["parent_full_name"] == "original/project-a"
    assert "status" not in data["forks"][0]
    assert "behind_by" not in data["forks"][0]
    assert data["skipped"] == []
    assert data["show_skipped"] is True


@respx.mock
def test_api_repos_stream(client):
    """SSE stream 端点应推送 list、diff、done 事件。"""
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
    with client.stream("GET", "/api/repos/stream") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = []
        for line in resp.iter_lines():
            if line.startswith("event: "):
                events.append(line[7:])
        assert "diff" in events
        assert "done" in events
        assert "list" not in events


@respx.mock
def test_api_sync_stream(client):
    """SSE sync-stream 端点应推送 progress 和 done 事件。"""
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
            200, json={"merge_type": "merge", "commit_message": "ok"}
        )
    )
    with client.stream("POST", "/api/sync-stream", json={"repos": ["me/project-a"]}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = []
        for line in resp.iter_lines():
            if line.startswith("event: "):
                events.append(line[7:])
        assert "progress" in events
        assert "done" in events


@respx.mock
def test_api_repos(client):
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
    resp = client.get("/api/repos")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["repo"]["full_name"] == "me/project-a"
    assert data[0]["behind_by"] == 1


@respx.mock
def test_api_diff(client):
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
    resp = client.get("/api/repos/me/project-a/diff")
    assert resp.status_code == 200
    assert resp.json()["status"] == "identical"


@respx.mock
def test_api_sync(client):
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
            200, json={"merge_type": "merge", "commit_message": "ok"}
        )
    )
    resp = client.post("/api/repos/me/project-a/sync")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@respx.mock
def test_api_sync_all(client):
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
            200, json={"merge_type": "merge", "commit_message": "ok"}
        )
    )
    resp = client.post("/api/sync-all", json={"repos": ["me/project-a"]})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["success"] is True
