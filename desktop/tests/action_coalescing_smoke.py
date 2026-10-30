"""真实 Deep Agents 多次工具调用与桌面动作聚合的联合验收。"""

import argparse
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path
from uuid import uuid4

project = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(project / part) for part in ("backend/src", "desktop/src", "backend/tests")]
os.environ["LANGSMITH_TRACING"] = "false"

import webview
from mcp_fixture import mcp_server
from native_capture import capture_webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def batch_message(mcp_count: int, archive_count: int) -> dict:
    """因为需要证明调用仍逐次执行，需要让合成模型提交多条正式工具请求而不注入假轨迹。"""
    # 1、每次工具都有独立调用 ID，执行器和 MCP 网络路径使用生产实现。
    calls = []
    for index in range(mcp_count + archive_count):
        remote = index < mcp_count
        calls.append(
            {
                "id": f"batch_{mcp_count}_{archive_count}_{index}",
                "type": "function",
                "function": {
                    "name": "math_add_numbers" if remote else "search_archive",
                    "arguments": json.dumps(
                        {"left": index, "right": 1}
                        if remote else {"query": "合成历史记录", "mode": "text"}
                    ),
                },
            }
        )
    return {"role": "assistant", "content": "", "tool_calls": calls}


def main() -> None:
    """因为动画合并不能省略实际工具，需要在两次独立会话中核对网络调用、完整轨迹与演出次数。"""
    # 1、测试根和模型协议均独立，不读取用户 Key；候选 UI 可用于发行资源复验。
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-root", type=Path, default=project / "desktop/ui")
    ui = parser.parse_args().ui_root.resolve(strict=True)
    if not ui.is_relative_to(project) or not (ui / "index.html").is_file():
        raise ValueError("仅验证本项目内的应用界面")
    root = project / ".cache/action-coalescing-smoke" / uuid4().hex
    result: dict = {}
    responses = [
        batch_message(8, 6),
        {"role": "assistant", "content": "首批八次 MCP 和六次档案查询已返回。"},
        batch_message(2, 2),
        {"role": "assistant", "content": "第二轮同一分钟内的调用已返回。"},
    ]
    with mcp_server(delay=0.4) as (url, calls), model_server(responses) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root))
        host.call(host.runtime.save_configuration(
            {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
        ))
        member = host.call(host.runtime.member("assistant"))
        host.call(host.runtime.save_member(
            {"id": "assistant", "mcp_servers": [{"name": "math", "url": url}]}, member["revision"]
        ))
        window = webview.create_window(
            "RoomCrew action coalescing verification", str(ui / "index.html"),
            js_api=DesktopAPI(host), width=1400, height=960,
        )

        def verify() -> None:
            """因为动画与工具执行独立，需要持续观察正式快照并导出当前测试窗口。"""
            # 1、不替换队列、时钟或渲染事实；所有事件都由真实 Loop 和工具提交。
            try:
                window.events.loaded.wait(20)
                window.evaluate_js(
                    (project / "desktop/tests/web/action-coalescing-smoke.js").read_text("utf-8")
                )
                captured = set()
                for _ in range(1800):
                    stage = window.evaluate_js("window.__coalescingStage || null")
                    if stage and stage not in captured:
                        capture_webview(window, root / (stage + ".png"))
                        captured.add(stage)
                        window.evaluate_js("window.__coalescingCaptured=" + json.dumps(stage))
                    status = window.evaluate_js("window.__coalescingResult || null")
                    if status:
                        result.update(status)
                        break
                    threading.Event().wait(0.1)
                else:
                    result.update(ok=False, error="action coalescing verification timeout")
                # 2、重读实际持久队列，并核对真实网络调用次数而不是模型口头结论。
                with sqlite3.connect(root / "data/scene-actions.sqlite") as db:
                    groups = [
                        {
                            "kind": value["kind"], "count": value["aggregation"]["count"],
                            "status": row[1],
                        }
                        for row in db.execute(
                            "SELECT body,status FROM actions WHERE status!='coalesced' ORDER BY seq"
                        )
                        for value in [json.loads(row[0])]
                    ]
                result.update(mcp_calls=len(calls), model_requests=len(requests), groups=groups)
                result["ok"] = bool(
                    result.get("ok") and len(calls) == 10 and len(requests) == 4
                    and len(groups) == 2
                    and {item["kind"]: (item["count"], item["status"]) for item in groups}
                    == {"mcp": (10, "played"), "archive": (8, "played")}
                )
                if not result["ok"]:
                    capture_webview(window, root / "failure.png")
                (root / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
                )
            finally:
                window.destroy()

        # 2、关闭自己的窗口与服务，不影响当前用户应用，也不留下定时任务。
        try:
            webview.start(verify, gui="edgechromium", debug=False)
        finally:
            host.close()
    print(json.dumps({"root": str(root), **result}, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
