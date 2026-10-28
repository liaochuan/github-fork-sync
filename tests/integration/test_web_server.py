"""Windows 下 accept 被客户端 abort 的回归测试。

复现路径：浏览器/客户端建立 TCP 连接后立即 RST（预连接、刷新、安全软件重置等），
AcceptEx 返回 WinError 64。Proactor 事件循环会因此关闭监听套接字，导致 Web 服务
此后拒绝所有新连接。
"""

import socket
import struct
import subprocess
import sys
import threading
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="仅 Windows Proactor/AcceptEx 存在该问题"
)

SERVER_SCRIPT = """
import sys

from gfs.web.server import run_server


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-length", b"2")],
        }
    )
    await send({"type": "http.response.body", "body": b"ok"})


run_server(app, "127.0.0.1", int(sys.argv[1]), log_level="critical")
"""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _is_serving(port: int, timeout: float = 2.0) -> bool:
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/", timeout=timeout)
    except httpx.HTTPError:
        return False
    return resp.status_code == 200


def _wait_until_serving(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_serving(port, timeout=0.5):
            return
        time.sleep(0.2)
    raise AssertionError(f"server on port {port} did not become ready")


def _abort_burst(port: int, threads: int = 8, per_thread: int = 50) -> None:
    """并发建连后立刻 RST，制造 accept 完成前的 abort。"""

    def worker() -> None:
        for _ in range(per_thread):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.settimeout(1.0)
                sock.connect(("127.0.0.1", port))
                sock.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_LINGER,
                    struct.pack("ii", 1, 0),
                )
            except OSError:
                pass
            finally:
                sock.close()

    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()


def test_server_keeps_accepting_after_aborted_connections(tmp_path):
    port = _free_port()
    script = tmp_path / "server.py"
    script.write_text(SERVER_SCRIPT, encoding="utf-8")

    proc = subprocess.Popen(
        [sys.executable, str(script), str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    dead_round = None
    try:
        _wait_until_serving(port)
        for round_no in range(1, 4):
            _abort_burst(port)
            time.sleep(0.3)
            if not _is_serving(port):
                dead_round = round_no
                break
    finally:
        proc.terminate()
        try:
            output = proc.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            output = proc.communicate()[0]

    assert dead_round is None, (
        f"第 {dead_round} 轮 abort 后服务不再接受连接\n{output}"
    )
