import asyncio
import sys
from typing import Any

import uvicorn


def run_server(
    app: Any, host: str, port: int, log_level: str = "info"
) -> None:
    """用平台合适的事件循环运行 uvicorn。

    Windows 默认的 Proactor 事件循环使用 AcceptEx 接收连接：若客户端在 accept
    完成前就断开（浏览器预连接、刷新、本地安全软件/代理重置连接等），AcceptEx
    会返回 WinError 64 (ERROR_NETNAME_DELETED)。asyncio 的 Proactor 实现把这种
    情况当成致命错误，直接关闭监听套接字（asyncio/proactor_events.py 中
    "Accept failed on a socket" 分支），之后 uvicorn 进程还在，但所有新连接都
    被拒绝。Selector 事件循环把该情况当作正常 abort 忽略并继续 accept。
    """
    config = uvicorn.Config(app, host=host, port=port, log_level=log_level)
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        # SelectorEventLoop 在 Windows 上不支持子进程，这里的 uvicorn 不启用
        # reload / workers，因此不受影响。
        asyncio.Runner(loop_factory=asyncio.SelectorEventLoop).run(server.serve())
    else:
        server.run()
