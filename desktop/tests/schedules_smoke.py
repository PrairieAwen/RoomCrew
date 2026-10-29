"""定时任务管理的原生 WebView 验证；独立数据，无真实模型或周期付费任务。"""

import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / folder) for folder in ("backend/src", "desktop/src")]

import webview
from native_capture import capture_webview

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为 DOM 单测不能覆盖原生桥和真实保存，需要用自己的窗口验证暂停、恢复、取消和空间隔离。"""
    # 1、本测试没有模型配置，规则一小时后到期，窗口结束时取消计划并关闭宿主。
    root = ROOT / ".cache/schedules-smoke" / uuid4().hex
    host = RuntimeThread(AppPaths.create(root))
    result: dict = {}
    window = webview.create_window(
        "RoomCrew schedule management verification",
        str(host.runtime.paths.resources / "desktop/ui/index.html"),
        js_api=DesktopAPI(host), width=1380, height=960,
    )

    def verify() -> None:
        """因为页面初始化和点击异步更新，需要驱动正式控件并导出自身窗口的管理面板。"""
        # 1、生产 API、存储和页面均不替换，等待只控制验证采样频率。
        try:
            window.events.loaded.wait(20)
            window.evaluate_js((ROOT / "desktop/tests/web/schedules-smoke.js").read_text("utf-8"))
            captured = False
            for _ in range(500):
                if window.evaluate_js("window.__schedulesStage === 'capture'") and not captured:
                    capture_webview(window, root / "schedules.png")
                    window.evaluate_js("window.__schedulesCaptured = true")
                    captured = True
                snapshot = window.evaluate_js("window.__schedulesResult || null")
                if snapshot:
                    result.update(snapshot)
                    break
                threading.Event().wait(0.1)
            else:
                raise TimeoutError("定时任务界面验证超时")
        except Exception as error:
            result.update(ok=False, error=str(error))
        finally:
            # 2、测试失败也取消自己的所有活动安排，只关闭测试窗口。
            for runtime in host.hub.runtimes.values():
                plans = host.call(runtime.list_schedules())
                for plan in plans:
                    host.call(runtime.set_schedule_state(
                        plan["id"], "deleted", plan["revision"], uuid4().hex
                    ))
            window.destroy()

    try:
        webview.start(verify, gui="edgechromium", private_mode=True)
    finally:
        host.close()
    result["screenshots"] = str(root)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
