"""档案室、无感续聊与并行会话的原生 WebView 验证，使用独立合成数据。"""

import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / folder) for folder in ("backend/src", "desktop/src", "backend/tests")]

import webview
from native_capture import capture_webview
from test_archives import SUMMARY, finish_archive
from test_runtime import TEST_KEY, TEST_MODEL, model_server, wait_finished

from roomcrew.application.workspaces import WorkspaceHub
from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


async def prepare(hub: WorkspaceHub, endpoint: str) -> dict:
    """因为原生界面需读取真实归档结果，需要用正式框架生成会话、压缩、索引和共享目录。"""
    # 1、只用本测试端点和目录，不读取任何用户模型配置。
    runtime = hub.current
    await runtime.save_configuration(
        {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
    )
    first = await hub.invoke(
        "default",
        "submit_chat",
        [
            "assistant",
            "我家里养了一只金毛犬，周五交付报告。",
            uuid4().hex,
        ],
    )
    await wait_finished(runtime)
    record = await hub._archive_worker.request("default", first["conversation"]["id"])
    await finish_archive(hub, record["id"])
    other = await hub.create("共享资料空间")
    await hub.select("default")
    return {
        "archive": record["id"],
        "old_conversation": first["conversation"]["id"],
        "other_workspace": other["active"]["id"],
    }


def main() -> None:
    """因为网页单测不能证明桥和真实渲染工作，需要启动自己的原生窗口并检查档案与并行交互。"""
    # 1、所有模型响应合成，向量模型、归档服务、Deep Agents、会话和页面均为正式实现。
    root = ROOT / ".cache/archive-smoke" / uuid4().hex
    result: dict = {}
    replies = [
        {"role": "assistant", "content": "已记下金毛犬和周五报告。"},
        {"role": "assistant", "content": SUMMARY},
        {"role": "assistant", "content": "独立任务处理完成。"},
    ]
    with model_server(replies, delay=1.2) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root))
        inputs = host.call(prepare(host.hub, endpoint))
        window = webview.create_window(
            "RoomCrew archive and parallel conversations verification",
            str(host.runtime.paths.resources / "desktop/ui/index.html"),
            js_api=DesktopAPI(host),
            width=1480,
            height=1050,
        )

        def verify() -> None:
            """因为页面查询和渲染异步推进，需要操作正式控件并导出自己的目录、语义和共享画面。"""
            # 1、脚本只观察实际服务和界面，不伪造原文、向量、摘要或人物状态。
            try:
                window.events.loaded.wait(20)
                window.evaluate_js("window.__archiveInputs=" + json.dumps(inputs))
                window.evaluate_js((ROOT / "desktop/tests/web/archive-smoke.js").read_text("utf-8"))
                captured = set()
                for _ in range(900):
                    stage = window.evaluate_js("window.__archiveStage || ''")
                    if stage.startswith("capture-") and stage not in captured:
                        capture_webview(window, root / (stage + ".png"))
                        captured.add(stage)
                        window.evaluate_js("window.__archiveCaptured=" + json.dumps(stage))
                    status = window.evaluate_js("window.__archiveResult || null")
                    if status:
                        result.update(status)
                        break
                    threading.Event().wait(0.1)
                else:
                    raise TimeoutError("档案室原生验证超时")
            except Exception as error:
                result.update(ok=False, error=str(error))
            finally:
                # 2、仅关闭本次独立窗口，所有未来检查器随宿主退出，不影响用户原应用。
                window.destroy()

        try:
            webview.start(verify, gui="edgechromium", private_mode=True)
            if result.get("ok"):
                assert len(requests) == 4
                assert "日期" in json.dumps(requests[2]["messages"], ensure_ascii=False)
                result.update(model_requests=4, screenshots=str(root))
        finally:
            host.close()
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
