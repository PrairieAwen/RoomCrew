"""真实 Windows 窗口、SDK 委派、会议与外援电话的完整验收。"""

import hashlib
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
    """因为配置成员和外援是本轮关键交互，需要真实运行两轮委派并观察正式图形与文件产物。"""
    # 1、回环模型只提供协议响应；真实 Loop、工具、轨迹、关系归约和人物播放器均不替换。
    root = Path(__file__).resolve().parents[2]
    result: dict = {}
    messages: list[dict] = []
    with model_server(messages, delay=4) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root / ".cache/collaboration-smoke" / uuid4().hex))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        employee = host.call(host.runtime.save_member({"name": "原生同事", "leisure_delay": 0}, 0))
        definition = host.call(
            host.runtime.save_agent_configuration({"description": "无形象资料协作者"}, 0)
        )
        collaborator = "definition_" + hashlib.sha256(definition["id"].encode()).hexdigest()[:16]
        messages.extend(
            [
                tool_message(
                    "task",
                    {
                        "subagent_type": "member_" + employee["id"],
                        "description": "把指定记录写入 /meeting.txt",
                    },
                ),
                tool_message(
                    "write_file", {"file_path": "/meeting.txt", "content": "真实会议委派产物"}
                ),
                {"role": "assistant", "content": "同事任务结束。"},
                {"role": "assistant", "content": "请核对会议委派产物。"},
                tool_message(
                    "task",
                    {
                        "subagent_type": collaborator,
                        "description": "把指定记录写入 /external.txt",
                    },
                ),
                tool_message(
                    "write_file", {"file_path": "/external.txt", "content": "真实外援工具产物"}
                ),
                {"role": "assistant", "content": "通用子任务结束。"},
                {"role": "assistant", "content": "请核对外援产物。"},
            ]
        )
        window = webview.create_window(
            "RoomCrew collaboration integration",
            str(host.runtime.paths.resources / "desktop/ui" / "index.html"),
            js_api=DesktopAPI(host),
            width=1280,
            height=800,
        )

        def verify() -> None:
            """因为真实委派和行走有独立时序，需要有界观察实际页面返回的验收结果。"""
            # 1、只使用生产输入表单，不向页面注入伪造关系或轨迹。
            script = (
                (root / "desktop/tests/web/collaboration-smoke.js")
                .read_text("utf-8")
                .replace("EMPLOYEE_ID", json.dumps(employee["id"]))
            )
            try:
                window.events.loaded.wait(20)
                window.evaluate_js(script)
                for _ in range(900):
                    snapshot = window.evaluate_js("window.__collaborationSmoke || null")
                    if snapshot:
                        result.update(snapshot)
                        break
                    threading.Event().wait(0.1)
                else:
                    result.update(ok=False, error="native collaboration timeout")
            except Exception as error:
                result.update(ok=False, error=type(error).__name__)
            finally:
                window.destroy()

        try:
            # 2、合成服务延迟仅用于观察真实行走，不改变生产请求或工具执行速度。
            webview.start(verify, gui="edgechromium", private_mode=True)
        finally:
            host.close()
        result["http_requests"] = len(requests)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok") or result["http_requests"] != 8:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
