"""真实鼠标与 WebView2 的完成/人工泡泡验收；配合 computer-use 操作此测试窗口。"""

import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

project = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(project / folder) for folder in ("backend/src", "desktop/src", "backend/tests")]
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为 element.click 会绕过鼠标捕获，需要保留原生窗口等待真实鼠标并验证已读持久化。"""
    # 1、合成模型仅代替远端响应，任务、人工恢复、轨迹与回执均使用生产逻辑。
    paths = AppPaths.create(project / ".cache/bubble-pointer-smoke" / uuid4().hex)
    responses = [
        {"role": "assistant", "content": "第一轮已完成。"},
        {"role": "assistant", "content": "第二轮已完成。"},
        tool_message(
            "ask_user",
            {
                "question": "需要你选择下一步",
                "choices": ["继续", "停止"],
                "interaction_type": "choice",
                "allow_other": True,
            },
        ),
        {"role": "assistant", "content": "已收到人工答复，最终完成。"},
    ]
    result: dict[str, object] = {}
    with model_server(responses) as (endpoint, requests):
        host = RuntimeThread(paths)
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        window = webview.create_window(
            "RoomCrew pointer verification",
            str(paths.resources / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1440,
            height=960,
        )

        def verify() -> None:
            """因为真实指针需要外部 computer-use 注入，需要公开测试阶段并在有界时间内等待验证。"""
            # 1、不调用 bubbleButton.click；仅等待当前测试窗口实际收到的可信鼠标事件。
            window.evaluate_js(
                (project / "desktop/tests/web/bubble-pointer-smoke.js").read_text("utf-8")
            )
            previous = None
            try:
                for _ in range(3600):
                    stage = window.evaluate_js("window.__pointerStage || null")
                    if stage and stage != previous:
                        print(json.dumps({"stage": stage}), flush=True)
                        previous = stage
                    status = window.evaluate_js("window.__pointerResult || null")
                    if status:
                        result.update(status)
                        break
                    threading.Event().wait(0.1)
                if not result:
                    result.update({"ok": False, "error": "physical pointer timeout"})
            finally:
                # 2、测试结束释放窗口，不结束真实用户程序。
                window.destroy()

        try:
            webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
        finally:
            host.close()
        result["model_requests"] = len(requests)
        # 2、重新创建完整 Runtime 验证回执未依赖临时 DOM，重启后不再弹出已读结果。
        if result.get("ok"):
            reopened = RuntimeThread(paths)
            try:
                snapshot = reopened.call(reopened.runtime.studio_feed())
                persisted = not any(item["bubble"] for item in snapshot["actors"])
                result.update({"restart_persisted": persisted, "ok": persisted})
            finally:
                reopened.close()
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
