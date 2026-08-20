import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    github_token: str | None = None
    include: list[str] | None = None
    exclude: list[str] | None = None
    web_port: int = 8000
    proxy: str | None = None
    show_skipped: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.environ.get("GITHUB_TOKEN")
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        return cls(github_token=token, proxy=proxy)

    def require_token(self) -> str:
        """返回 token，若不存在则抛出 ValueError。CLI 模式使用。"""
        if not self.github_token:
            raise ValueError(
                "GITHUB_TOKEN not found. Set it in .env or environment."
            )
        return self.github_token

    def should_process(self, repo_full_name: str) -> bool:
        if self.include is not None:
            return repo_full_name in self.include
        if self.exclude is not None:
            return repo_full_name not in self.exclude
        return True


def load_settings(config_path: str | None = None) -> Settings:
    settings = Settings.from_env()
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        settings.include = data.get("include", [])
        settings.exclude = data.get("exclude", [])
        if "web_port" in data:
            settings.web_port = data["web_port"]
        if "proxy" in data:
            settings.proxy = data["proxy"]
        if "show_skipped" in data:
            settings.show_skipped = data["show_skipped"]
    return settings
