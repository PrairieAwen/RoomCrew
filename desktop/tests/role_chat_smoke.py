"""角色点击、配置入口与真实接单身份的原生集成验证。"""

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
from native_capture import capture_webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为角色点击必须关联真实接单人且不能误开配置，需要在原生窗口验证完整任务与切换。"""
    # 1、只在本测试随机目录配置合成模型，执行仍由真实 Deep Agents 和文件工具完成。
    root = ROOT / ".cache/role-chat-smoke" / uuid4().hex
    root.mkdir(parents=True)
    replies = [
        tool_message("write_file", {"file_path": "/role.txt", "content": "角色接单验证"}),
        {"role": "assistant", "content": "已完成角色接单验证，请查看 role.txt。"},
    ]
    result = {}
    with model_server(replies) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        worker = host.call(host.runtime.save_member({"id": "role_worker", "name": "资料员"}, 0))
        window = webview.create_window(
            "RoomCrew role chat verification",
            str(host.runtime.paths.resources / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1450,
            height=950,
        )

        def verify() -> None:
            """因为页面与桥接异步就绪，需要按真实控件状态执行并保存本测试的可见画面。"""
            # 1、测试只驱动正式控件，不替代事件、模型请求或任务产物。
            try:
                window.events.loaded.wait(20)
                window.evaluate_js(
                    (ROOT / "desktop/tests/web/role-chat-smoke.js").read_text("utf-8")
                )
                captured = set()
                for _ in range(600):
                    stage = window.evaluate_js("window.__roleStage || ''")
                    if stage in {"direct-chat", "options"} and stage not in captured:
                        capture_webview(window, root / (stage + ".png"))
                        captured.add(stage)
                        window.evaluate_js("window.__roleCaptured=" + json.dumps(stage))
                    status = window.evaluate_js("window.__roleResult || null")
                    if status:
                        result.update(status)
                        break
                    threading.Event().wait(0.1)
                else:
                    raise TimeoutError("角色对话验收超时")
            except Exception as error:
                result.update(ok=False, error=str(error))
            finally:
                # 2、只关闭本次测试窗口，保留用户原程序与数据。
                window.destroy()

        try:
            webview.start(verify, gui="edgechromium", private_mode=True)
            events = (
                host.call(host.runtime.events(result.get("conversation", "")))
                if result.get("ok")
                else []
            )
            starts = [event for event in events if event["kind"] == "run.started"]
            if result.get("ok"):
                assert len(starts) == 1 and starts[0]["member_id"] == worker["id"]
                assert (
                    host.call(host.runtime.read_artifact(result["conversation"], "/role.txt"))[
                        "text"
                    ]
                    == "角色接单验证"
                )
                assert len(requests) == 2
            result.update(model_requests=len(requests), screenshots=str(root))
        finally:
            host.close()
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
