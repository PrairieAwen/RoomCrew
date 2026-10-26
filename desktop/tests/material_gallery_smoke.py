"""实际 WebView2 素材展厅验收，不访问用户数据或模型。"""

import json
import threading
from pathlib import Path

import webview


def main() -> None:
    """因为浏览器代码检查不足以证明图片可见，需要原生打开正式展厅执行控件回归。"""
    # 1、独立窗口没有桌面桥、账号数据库或真实模型凭据。
    root = Path(__file__).resolve().parents[2]
    result: dict = {}
    window = webview.create_window(
        "RoomCrew material gallery integration",
        str(root / "desktop/ui/index.html"),
        width=1200,
        height=850,
    )

    def verify() -> None:
        """因为绘制与加载有异步时序，需要观察真实控件结果后退出测试窗口。"""
        # 1、脚本驱动实际展厅按钮，不覆盖素材或绘制函数。
        try:
            window.events.loaded.wait(20)
            # 2、从应用资源根导航，保证共享动作选择器与正式 iframe 使用相同相对地址。
            window.evaluate_js("location.replace('studio/assets/library-v1/index.html')")
            for _ in range(200):
                if window.evaluate_js("Boolean(window.materialGallery)"):
                    break
                threading.Event().wait(0.1)
            window.evaluate_js(
                (root / "desktop/tests/web/material-gallery-smoke.js").read_text("utf-8")
            )
            for _ in range(400):
                snapshot = window.evaluate_js("window.__materialResult || null")
                if snapshot:
                    result.update(snapshot)
                    break
                threading.Event().wait(0.1)
            else:
                result.update(ok=False, error="material gallery timeout")
        except Exception as error:
            result.update(ok=False, error=type(error).__name__)
        finally:
            window.destroy()

    # 2、成功只由实际页面报告；异常或空结果使验证进程失败。
    webview.start(verify, gui="edgechromium", private_mode=True)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
