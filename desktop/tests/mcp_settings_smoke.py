"""MCP Agent 配置入口的原生 WebView2 完整验证；仅用独立合成数据。"""

import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / folder) for folder in ("backend/src", "desktop/src", "backend/tests")]
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import webview
from mcp_fixture import mcp_server
from native_capture import capture_webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为浏览器单测无法验证原生桥、DPAPI 和框架装配，需要启动自己的测试窗口验收。"""
    # 1、所有数据和凭据均为本测试生成，不读取、修改或关闭用户原应用。
    root = ROOT / ".cache/mcp-settings-smoke" / uuid4().hex
    root.mkdir(parents=True)
    result = {}
    key = "synthetic-native-mcp-secret-12345678"
    replies = [
        tool_message("math_add_numbers", {"left": 20, "right": 22}),
        {"role": "assistant", "content": "MCP 返回 42，任务完成。"},
    ]
    with (
        mcp_server(api_key=key, echo_key=True) as (url, calls),
        model_server(replies) as (endpoint, requests),
    ):
        host = RuntimeThread(AppPaths.create(root))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        window = webview.create_window(
            "RoomCrew MCP configuration verification",
            str(host.runtime.paths.resources / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1450,
            height=1000,
        )

        def verify() -> None:
            """因为配置表单和场景均异步初始化，需要驱动正式控件并导出自己的窗口画面。"""
            # 1、测试只传入合成端点和 Key，不替换生产配置用例或 MCP 适配器。
            try:
                window.events.loaded.wait(20)
                window.evaluate_js("window.__mcpInputs=" + json.dumps({"url": url, "key": key}))
                window.evaluate_js(
                    (ROOT / "desktop/tests/web/mcp-settings-smoke.js").read_text("utf-8")
                )
                captured = set()
                for _ in range(800):
                    stage = window.evaluate_js("window.__mcpStage || ''")
                    if stage == "mcp-config" and stage not in captured:
                        capture_webview(window, root / (stage + ".png"))
                        captured.add(stage)
                        window.evaluate_js("window.__mcpCaptured=" + json.dumps(stage))
                    status = window.evaluate_js("window.__mcpResult || null")
                    if status:
                        result.update(status)
                        break
                    threading.Event().wait(0.1)
                else:
                    raise TimeoutError("MCP 配置原生验收超时")
            except Exception as error:
                result.update(ok=False, error=str(error))
            finally:
                # 2、只关闭本次测试窗口，真实用户窗口与配置保持原样。
                window.destroy()

        try:
            webview.start(verify, gui="edgechromium", private_mode=True)
            if result.get("ok"):
                assert calls == [{"left": 20, "right": 22}]
                assert len(requests) == 2
                assert key not in json.dumps(requests)
                events = host.call(host.runtime.events(result["conversation"]))
                assert any(event["payload"].get("tool_kind") == "mcp" for event in events)
                assert key not in json.dumps(events)
                result.update(model_requests=2, mcp_calls=1, screenshots=str(root))
        finally:
            host.close()
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
