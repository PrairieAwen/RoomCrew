"""真实 MCP、Deep Agents 与原生 WebView 的动作和完成状态联合验收。"""

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
from mcp_fixture import mcp_server
from native_capture import capture_webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为单元测试无法证明角色真正打字，需要通过真实 MCP 持续调用检查原生图集与提示。"""
    # 1、只创建隔离合成资料，实际 MCP 服务等待九秒，模型协议可控而生产执行器保持原样。
    root = project / ".cache/execution-visuals-smoke" / uuid4().hex
    root.mkdir(parents=True)
    responses = [
        {"role": "assistant", "content": "这是上一轮的合成结果。"},
        tool_message("math_add_numbers", {"left": 17, "right": 25}),
        tool_message(
            "ask_user",
            {
                "question": "结果为42，是否继续整理？",
                "choices": ["继续", "暂停"],
                "interaction_type": "choice",
                "allow_other": True,
            },
        ),
        {"role": "assistant", "content": "本轮 MCP 返回42，已按人工答复整理。"},
        tool_message("math_add_numbers", {"left": 18, "right": 24}),
        {"role": "assistant", "content": "小橘的 MCP 返回42。"},
    ]
    result: dict = {}
    with (
        mcp_server(delay=9) as (url, calls),
        model_server(responses, delay=0.5) as (endpoint, requests),
    ):
        host = RuntimeThread(AppPaths.create(root))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        current = host.call(host.runtime.member("assistant"))
        host.call(
            host.runtime.save_member(
                {"id": "assistant", "mcp_servers": [{"name": "math", "url": url}]},
                current["revision"],
            )
        )
        asset = host.call(host.runtime.import_avatar_bundle("hippo"))
        member = host.call(
            host.runtime.save_member(
                {
                    "id": "hippo_visual_worker",
                    "name": "小橘（合成验收）",
                    "avatar_id": asset["id"],
                    "agent_id": "agent_assistant",
                },
                0,
            )
        )
        window = webview.create_window(
            "RoomCrew execution visuals verification",
            str(project / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1500,
            height=1000,
        )

        def verify() -> None:
            """因为原生帧与 MCP 响应异步，需要在真实阶段导出截图并保留可核对的协议调用记录。"""
            # 1、测试仅调用正式界面入口，不注入假轨迹或直接修改渲染器事实。
            window.evaluate_js(
                (project / "desktop/tests/web/execution-visuals-smoke.js").read_text("utf-8")
            )
            captured = set()
            try:
                for _ in range(1400):
                    stage = window.evaluate_js("window.__executionVisualStage || null")
                    if stage and stage not in captured:
                        capture_webview(window, root / (stage + ".png"))
                        captured.add(stage)
                        window.evaluate_js("window.__executionVisualCaptured=" + json.dumps(stage))
                    status = window.evaluate_js("window.__executionVisualResult || null")
                    if status:
                        result.update(status)
                        if not status.get("ok"):
                            capture_webview(window, root / "failure.png")
                        break
                    threading.Event().wait(0.1)
                else:
                    result.update(ok=False, error="native verification timeout")
                # 2、所有调用均为合成数据；检查实际 MCP 次数，不把模型口头答复作为成功证明。
                result.update(
                    mcp_calls=calls,
                    model_requests=len(requests),
                    member_id=member["id"],
                    captures=sorted(captured),
                )
                result["ok"] = bool(
                    result.get("ok")
                    and calls == [{"left": 17, "right": 25}, {"left": 18, "right": 24}]
                )
                (root / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
                )
            finally:
                window.destroy()

        # 2、测试窗口结束后释放服务和线程，不修改原用户配置或留下计划。
        webview.start(verify, gui="edgechromium", debug=False)
        host.close()
    print(json.dumps({"root": str(root), **result}, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
