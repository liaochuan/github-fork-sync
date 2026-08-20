import httpx
import respx
from typer.testing import CliRunner

from gfs.cli.app import app

runner = CliRunner()


def _fork_json(name="me/project-a", parent="original/project-a"):
    return {
        "id": 1,
        "full_name": name,
        "fork": True,
        "default_branch": "main",
        "html_url": f"https://github.com/{name}",
        "parent": {"full_name": parent, "default_branch": "main"},
    }


@respx.mock
def test_list_command(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(
            200,
            json=[_fork_json("me/a"), _fork_json("me/b")],
        )
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "me/a" in result.stdout
    assert "me/b" in result.stdout


@respx.mock
def test_list_json_command(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=[_fork_json()])
    )
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    assert "me/project-a" in result.stdout


@respx.mock
def test_diff_command(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
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
                        "sha": "abc1234",
                        "commit": {
                            "message": "feat: upstream change",
                            "author": {"name": "Alice", "date": "2026-08-15"},
                        },
                        "html_url": "https://github.com/o/r/commit/abc1234",
                    }
                ],
            },
        )
    )
    result = runner.invoke(app, ["diff", "me/project-a"])
    assert result.exit_code == 0
    assert "behind" in result.stdout.lower()
    assert "feat: upstream change" in result.stdout


@respx.mock
def test_sync_command_with_yes(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
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
    result = runner.invoke(app, ["sync", "me/project-a", "--yes"])
    assert result.exit_code == 0
    assert "success" in result.stdout.lower() or "synced" in result.stdout.lower()


def test_sync_no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    result = runner.invoke(app, ["list"])
    assert result.exit_code != 0
