"""正式 SDK 并行派发和历史检索的原生顺序演出验收。"""

import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4

project = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(project / folder) for folder in ("backend/src", "desktop/src", "backend/tests")]
os.environ["LANGSMITH_TRACING"] = "false"

import webview
from native_capture import capture_webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为两个子任务可以在动画前结束，需要验证实际并行工具之后仍逐个递文件并去档案库。"""
    # 1、真实 Loop 和工具不替换；合成模型只控制请求，表现不能延迟任务完成。
    root = project / ".cache/performance-queue-smoke" / uuid4().hex
    result: dict = {}
    messages: list[dict] = []
    with model_server(messages, delay=0.4) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        workers = [
            host.call(host.runtime.save_member({"name": name}, 0)) for name in ("员工A", "员工B")
        ]
        calls = []
        for index, worker in enumerate(workers):
            calls.append(
                {
                    "id": f"delegate_{index}",
                    "type": "function",
                    "function": {
                        "name": "task",
                        "arguments": json.dumps(
                            {
                                "subagent_type": "member_" + worker["id"],
                                "description": "写一份合成协作记录",
                            }
                        ),
                    },
                }
            )
        messages.extend(
            [
                {"role": "assistant", "content": "", "tool_calls": calls},
                tool_message(
                    "write_file", {"file_path": "/worker-a.txt", "content": "原生并行子任务产物A"}
                ),
                tool_message(
                    "write_file", {"file_path": "/worker-b.txt", "content": "原生并行子任务产物B"}
                ),
                {"role": "assistant", "content": "子任务已返回"},
                {"role": "assistant", "content": "子任务已返回"},
                {"role": "assistant", "content": "两个子任务均已汇总"},
                tool_message("search_archive", {"query": "合成历史记录", "mode": "text"}),
                {"role": "assistant", "content": "档案检索已返回"},
            ]
        )
        window = webview.create_window(
            "RoomCrew queued performance verification",
            str(project / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1500,
            height=1000,
        )

        def verify() -> None:
            """因为事件顺序与动画速度独立，需要在正式窗口观察递文件和翻档并导出实际画面。"""
            # 1、不注入假轨迹、假队列或计时器；所有动作来自正式业务提交。
            script = (project / "desktop/tests/web/performance-queue-smoke.js").read_text("utf-8")
            window.evaluate_js(script)
            captured = set()
            try:
                for _ in range(1800):
                    stage = window.evaluate_js("window.__performanceStage || null")
                    if stage and stage not in captured:
                        capture_webview(window, root / (stage + ".png"))
                        captured.add(stage)
                        window.evaluate_js("window.__performanceCaptured=" + json.dumps(stage))
                    status = window.evaluate_js("window.__performanceResult || null")
                    if status:
                        result.update(status)
                        if not status.get("ok"):
                            capture_webview(window, root / "failure.png")
                        break
                    threading.Event().wait(0.1)
                else:
                    result.update(ok=False, error="native queued performance timeout")
                result.update(requests=len(requests), captures=sorted(captured))
                (root / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
                )
            finally:
                window.destroy()

        # 2、结束时释放窗口与运行时，所有合成文件留在本次测试根便于核对。
        webview.start(verify, gui="edgechromium", debug=False)
        host.close()
    print(json.dumps({"root": str(root), **result}, ensure_ascii=False))
    if not result.get("ok") or len(requests) != 8:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
