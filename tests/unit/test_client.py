import httpx
import pytest
import respx

from gfs.github.client import GitHubClient


@pytest.fixture
def client():
    return GitHubClient(token="ghp_test_token")


@respx.mock
def test_get_single_page(client):
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 1, "full_name": "o/r"}],
        )
    )
    data = client.get("/user/repos", params={"per_page": 100})
    assert data == [{"id": 1, "full_name": "o/r"}]


@respx.mock
def test_get_with_pagination(client):
    respx.get("https://api.github.com/user/repos?page=2").mock(
        return_value=httpx.Response(200, json=[{"id": 2}])
    )
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 1}],
            headers={
                "Link": '<https://api.github.com/user/repos?page=2>; rel="next"'
            },
        )
    )
    data = client.get_all("/user/repos", params={"per_page": 100})
    assert data == [{"id": 1}, {"id": 2}]


@respx.mock
def test_post(client):
    respx.post("https://api.github.com/repos/o/r/merge-upstream").mock(
        return_value=httpx.Response(
            200,
            json={
                "merge_type": "merge",
                "base_branch": "main",
                "head_branch": "main",
                "commit_message": "Merged upstream",
            },
        )
    )
    data = client.post(
        "/repos/o/r/merge-upstream", json={"branch": "main"}
    )
    assert data["merge_type"] == "merge"


@respx.mock
def test_get_404(client):
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get("/repos/o/r")


@respx.mock
def test_retry_on_network_error(client):
    route = respx.get("https://api.github.com/user/repos").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    with pytest.raises(httpx.ConnectError):
        client.get("/user/repos")
    assert route.call_count == 3


@respx.mock
def test_client_with_proxy():
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[{"id": 1}])
    )
    c = GitHubClient(token="ghp_test_token", proxy="http://127.0.0.1:7890")
    data = c.get("/user/repos")
    assert data == [{"id": 1}]
    c.close()


@respx.mock
def test_client_without_proxy():
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[{"id": 1}])
    )
    c = GitHubClient(token="ghp_test_token", proxy=None)
    data = c.get("/user/repos")
    assert data == [{"id": 1}]
    c.close()
