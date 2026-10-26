"""原生窗口多空间切换、后台运行与实际文件隔离验证。"""

import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

sys.path[:0] = [
    str(Path(__file__).resolve().parents[2] / "backend/src"),
    str(Path(__file__).resolve().parents[2] / "desktop/src"),
    str(Path(__file__).resolve().parents[2] / "backend/tests"),
]
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为后端隔离正确不代表前端不会串画面，需要从生产表单切换房间并核对真实产物。"""
    # 1、每次使用独立测试数据与模拟模型，不触碰用户正式历史或凭据。
    root = Path(__file__).resolve().parents[2]
    messages = [
        tool_message("write_file", {"file_path": "/proof.txt", "content": "甲空间产物"}),
        {"role": "assistant", "content": "甲已完成"},
        tool_message("write_file", {"file_path": "/proof.txt", "content": "乙空间产物"}),
        {"role": "assistant", "content": "乙已完成"},
    ]
    result = {}
    with model_server(messages, delay=0.8) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root / ".cache/workspace-smoke" / uuid4().hex))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        host.call(host.runtime.save_member({"name": "仅甲空间员工"}, 0))
        window = webview.create_window(
            "RoomCrew workspace integration",
            str(host.runtime.paths.desktop_ui / "index.html"),
            js_api=DesktopAPI(host),
            width=1380,
            height=900,
        )

        def verify() -> None:
            """因为脚本与渲染异步推进，需要驱动正式页面并有界等待安全验证结果。"""
            # 1、不替换执行框架、时间、轨迹或动画状态。
            try:
                window.events.loaded.wait(20)
                window.evaluate_js(
                    (root / "desktop/tests/web/workspace-smoke.js").read_text("utf-8")
                )
                for _ in range(500):
                    snapshot = window.evaluate_js("window.__workspaceSmoke || null")
                    if snapshot:
                        result.update(snapshot)
                        break
                    threading.Event().wait(0.1)
                else:
                    result.update(
                        {
                            "ok": False,
                            "stage": window.evaluate_js("window.__workspaceStage || 'not-started'"),
                        }
                    )
            except Exception as error:
                result.update({"ok": False, "error": type(error).__name__})
            finally:
                window.destroy()

        try:
            webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
        finally:
            host.close()
        result["http_requests"] = len(requests)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
