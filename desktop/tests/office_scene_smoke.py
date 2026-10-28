"""真实模型协议、Python、人工恢复和新办公场景的原生验收。"""

import argparse
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
from native_capture import capture_webview
from test_runtime import TEST_KEY, TEST_MODEL, model_server, tool_message

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为动作正确必须同时符合真实工具状态与素材方向，需要通过原生场景完整执行并导出画面。"""
    # 1、模型仅使用本机合成服务，脚本和人工恢复仍由真实框架执行。
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-root", type=Path)
    ui_root = parser.parse_args().ui_root
    if ui_root:
        ui_root = ui_root.resolve(strict=True)
        if not ui_root.is_relative_to(project / "dist") or not (ui_root / "index.html").is_file():
            raise ValueError("发行界面验收仅允许项目 dist 内完整界面目录")
    root = project / ".cache/office-scene-smoke" / uuid4().hex
    root.mkdir(parents=True)
    script = (
        "import time\nfrom pathlib import Path\ntime.sleep(12)\n"
        "Path('proof.txt').write_text('office verified',encoding='utf-8')\n"
    )
    responses = [
        tool_message("write_file", {"file_path": "/verify.py", "content": script}),
        tool_message("execute_python", {"script_path": "/verify.py", "timeout_seconds": 15}),
        tool_message(
            "ask_user",
            {
                "question": "办公方向和交互已检查，是否继续？",
                "choices": ["继续", "暂停"],
                "interaction_type": "choice",
                "allow_other": True,
            },
        ),
        {"role": "assistant", "content": "已执行 Python 并生成 proof.txt。"},
    ]
    result: dict[str, object] = {}
    with model_server(responses, delay=1) as (endpoint, requests):
        host = RuntimeThread(AppPaths.create(root))
        host.call(
            host.runtime.save_configuration(
                {"base_url": endpoint, "model": TEST_MODEL, "api_key": TEST_KEY}
            )
        )
        for role, name in (("employee", "资料员"), ("owner", "开发员")):
            asset = host.call(host.runtime.import_avatar_bundle(role))
            host.call(
                host.runtime.save_member(
                    {"name": name, "agent_id": "agent_assistant", "avatar_id": asset["id"]}, 0
                )
            )
        window = webview.create_window(
            "RoomCrew office verification",
            str(
                (ui_root / "index.html")
                if ui_root
                else host.runtime.paths.resources / "desktop/ui/index.html"
            ),
            js_api=DesktopAPI(host),
            width=1500,
            height=1000,
        )

        def verify() -> None:
            """因为素材和真实轨迹异步到达，需要按实际阶段读取布局、动作与产物并导出本测试画面。"""
            # 1、驱动仅操作正式用户入口，不给生产渲染器注入假轨迹。
            window.evaluate_js(
                (project / "desktop/tests/web/office-scene-smoke.js").read_text("utf-8")
            )
            captured = set()
            try:
                for _ in range(1800):
                    stage = window.evaluate_js("window.__officeStage || null")
                    if (
                        stage
                        and stage.startswith(
                            (
                                "working",
                                "question",
                                "resting",
                                "walk-",
                                "desk-",
                                "assets",
                                "rotation",
                                "contact-",
                            )
                        )
                        and stage not in captured
                    ):
                        threading.Event().wait(0.25)
                        capture_webview(window, root / (stage + ".png"))
                        captured.add(stage)
                        window.evaluate_js("window.__officeCaptured=" + json.dumps(stage))
                    status = window.evaluate_js("window.__officeResult || null")
                    if status:
                        result.update(status)
                        if not status.get("ok"):
                            capture_webview(window, root / "failure.png")
                            result["diagnostics"] = window.evaluate_js(
                                "({views:studio?.renderer?.views?.size,"
                                "skins:[...(studio?.renderer?.skins?.cache?.keys()||[])],"
                                "errors:[...(studio?.renderer?.skins?.errors||[])],"
                                "actor:studio?.renderer?.motion?.actors?.get('assistant'),"
                                "sprite:{...studio?.renderer?.views?.get('assistant')?.sprite?.dataset},"
                                "fact:studio?.renderer?.facts?.get('assistant'),"
                                "notice:document.getElementById('status')?.textContent})"
                            )
                        break
                    threading.Event().wait(0.1)
                if not result:
                    result.update({"ok": False, "error": "office scene timeout"})
            except Exception as error:
                result.update({"ok": False, "error": str(error)})
            finally:
                # 2、导出只保存原生客户区；关闭测试窗口不影响用户程序。
                window.destroy()

        try:
            webview.start(verify, gui="edgechromium", debug=False, private_mode=True)
        finally:
            host.close()
        result.update({"model_requests": len(requests), "screenshots": str(root)})
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
