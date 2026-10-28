"""验证 run_server 的事件循环选择（Windows 必须用 Selector，规避 AcceptEx WinError 64）。"""

import asyncio

from gfs.web import server


class _FakeRunner:
    def __init__(self, *, loop_factory):
        self.loop_factory = loop_factory
        self.ran = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def run(self, coro):
        coro.close()
        self.ran = True


class _FakeServer:
    def __init__(self, config):
        self.config = config
        self.run_called = False

    async def serve(self, sockets=None):
        pass

    def run(self):
        self.run_called = True


def _patch(monkeypatch, platform: str):
    captured = {}

    def make_runner(*, loop_factory):
        captured["runner"] = _FakeRunner(loop_factory=loop_factory)
        return captured["runner"]

    def make_server(config):
        captured["server"] = _FakeServer(config)
        return captured["server"]

    monkeypatch.setattr(server.asyncio, "Runner", make_runner)
    monkeypatch.setattr(server.uvicorn, "Server", make_server)
    monkeypatch.setattr(server.uvicorn, "Config", lambda app, **kwargs: object())
    monkeypatch.setattr(server.sys, "platform", platform)
    return captured


def test_windows_uses_selector_event_loop(monkeypatch):
    captured = _patch(monkeypatch, "win32")

    server.run_server(object(), "127.0.0.1", 8000)

    runner = captured["runner"]
    assert runner.loop_factory is asyncio.SelectorEventLoop
    assert runner.ran is True
    assert captured["server"].run_called is False


def test_non_windows_delegates_to_server_run(monkeypatch):
    captured = _patch(monkeypatch, "linux")

    server.run_server(object(), "127.0.0.1", 8000)

    assert captured["server"].run_called is True
