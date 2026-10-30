"""仅供验证的真实 MCP HTTP 服务，返回可核对的合成数据。"""

import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse


@contextlib.contextmanager
def mcp_server(
    api_key: str | None = None,
    echo_key: bool = False,
    discovery_echo: bool = False,
    delay: float = 0,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """因为 MCP 接入必须验证实际协议，需要启动只监听本机的合成 MCP 服务并在结束时关闭。"""
    # 1、使用官方 MCP 服务器，工具返回真实计算结果，不替换生产适配器。
    requests: list[dict[str, Any]] = []
    app = FastMCP("RoomCrew verification", stateless_http=True, json_response=True)

    @app.tool(description=api_key if discovery_echo else None)
    def add_numbers(left: int, right: int) -> dict[str, Any]:
        """因为协议验证需要可核对的工具结果，需要计算两个输入整数之和。"""
        # 1、只记录合成整数，不读取文件、环境变量或凭据。
        requests.append({"left": left, "right": right})
        if delay:
            time.sleep(delay)
        result: dict[str, Any] = {"sum": left + right}
        if echo_key and api_key:
            result[api_key] = {"echo": api_key}
        return result

    http_app = app.streamable_http_app()

    async def authenticated_app(scope: Any, receive: Any, send: Any) -> None:
        """因为鉴权回归不能仅检查配置字段，需要让真实 HTTP 服务拒绝缺失或错误的合成 Key。"""
        # 1、只拦截本测试服务的 HTTP 请求，生命周期事件仍交给官方 MCP 实现。
        if scope["type"] == "http" and api_key:
            header = dict(scope["headers"]).get(b"authorization", b"").decode()
            if header != f"Bearer {api_key}":
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await http_app(scope, receive, send)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(authenticated_app, log_level="critical", access_log=False)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    try:
        while not server.started:
            if time.monotonic() >= deadline or not thread.is_alive():
                raise RuntimeError("合成 MCP 服务启动失败")
            time.sleep(0.02)
        yield f"http://127.0.0.1:{port}/mcp", requests
    finally:
        # 2、结束监听与线程，不留下服务或变更任何用户 MCP 配置。
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
