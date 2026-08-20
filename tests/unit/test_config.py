import os
from pathlib import Path

import pytest

from gfs.config import Settings, load_settings


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    s = Settings.from_env()
    assert s.github_token == "ghp_test_token"
    assert s.web_port == 8000
    assert s.proxy is None
    assert s.show_skipped is True


def test_settings_missing_token_returns_none(monkeypatch):
    """from_env 在缺少 token 时不再抛错，github_token 为 None。"""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    s = Settings.from_env()
    assert s.github_token is None


def test_require_token_raises_when_missing(monkeypatch):
    """require_token 在 token 为 None 时抛出 ValueError。"""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    s = Settings.from_env()
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        s.require_token()


def test_require_token_returns_token_when_present(monkeypatch):
    """require_token 在 token 存在时返回 token。"""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    s = Settings.from_env()
    assert s.require_token() == "ghp_test_token"


def test_load_settings_with_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "include:\n  - my-fork/project-a\nweb_port: 9000\n"
    )
    s = load_settings(config_path=str(config_file))
    assert s.github_token == "ghp_test_token"
    assert s.web_port == 9000
    assert s.include == ["my-fork/project-a"]
    assert s.exclude == []
    assert s.proxy is None


def test_load_settings_no_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    s = load_settings(config_path=str(tmp_path / "nonexistent.yaml"))
    assert s.include is None
    assert s.exclude is None
    assert s.web_port == 8000
    assert s.proxy is None


def test_load_settings_with_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("proxy: http://127.0.0.1:7890\n")
    s = load_settings(config_path=str(config_file))
    assert s.proxy == "http://127.0.0.1:7890"


def test_load_settings_proxy_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:1080")
    s = Settings.from_env()
    assert s.proxy == "http://10.0.0.1:1080"


def test_load_settings_config_proxy_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:1080")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("proxy: http://127.0.0.1:7890\n")
    s = load_settings(config_path=str(config_file))
    assert s.proxy == "http://127.0.0.1:7890"


def test_settings_filter_repo_include(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    s = Settings(
        github_token="ghp_test_token",
        include=["my-fork/project-a"],
        exclude=None,
        web_port=8000,
    )
    assert s.should_process("my-fork/project-a") is True
    assert s.should_process("my-fork/project-b") is False


def test_settings_filter_repo_exclude(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    s = Settings(
        github_token="ghp_test_token",
        include=None,
        exclude=["my-fork/old"],
        web_port=8000,
    )
    assert s.should_process("my-fork/old") is False
    assert s.should_process("my-fork/new") is True


def test_settings_no_filter(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    s = Settings(
        github_token="ghp_test_token",
        include=None,
        exclude=None,
        web_port=8000,
    )
    assert s.should_process("any/repo") is True


def test_load_settings_show_skipped_default(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    config_file = tmp_path / "config.yaml"
    config_file.write_text("web_port: 8000\n")
    s = load_settings(config_path=str(config_file))
    assert s.show_skipped is True


def test_load_settings_show_skipped_false(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setattr("gfs.config.load_dotenv", lambda: None)
    config_file = tmp_path / "config.yaml"
    config_file.write_text("show_skipped: false\n")
    s = load_settings(config_path=str(config_file))
    assert s.show_skipped is False
