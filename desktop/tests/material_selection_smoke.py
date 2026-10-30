"""真实人物素材选择、保存与会议室显示验收，不使用模型或用户数据。"""

import argparse
import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

project = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(project / name) for name in ("backend/src", "desktop/src")]

import webview
from native_capture import capture_webview

from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为选项存在不代表预览和保存生效，需要用正式事件和原生桥验证完整素材工作流。"""
    # 1、独立资料不包含真实 Key；可选候选 UI 路径用于核对随包资源。
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-root", type=Path, default=project / "desktop/ui")
    ui = parser.parse_args().ui_root.resolve(strict=True)
    if not ui.is_relative_to(project) or not (ui / "index.html").is_file():
        raise ValueError("仅验证本项目内的应用界面")
    root = project / ".cache/material-selection-smoke" / uuid4().hex
    host = RuntimeThread(AppPaths.create(root))
    result: dict = {}
    window = webview.create_window(
        "RoomCrew material selection verification",
        str(ui / "index.html"),
        js_api=DesktopAPI(host),
        width=1300,
        height=960,
    )

    def verify() -> None:
        """因为图像导入和渲染异步，需要观察实际页面条件并导出当前测试窗口截图。"""
        # 1、只驱动真实表单，不替换素材加载器或直接伪造人物绑定。
        try:
            window.events.loaded.wait(20)
            window.evaluate_js(
                (project / "desktop/tests/web/material-selection-smoke.js").read_text("utf-8")
            )
            captured = set()
            for _ in range(1200):
                stage = window.evaluate_js("window.__materialSelectionStage || null")
                if stage and stage not in captured:
                    capture_webview(window, root / (stage + ".png"))
                    captured.add(stage)
                    window.evaluate_js("window.__materialSelectionCaptured=" + json.dumps(stage))
                status = window.evaluate_js("window.__materialSelectionResult || null")
                if status:
                    result.update(status)
                    break
                threading.Event().wait(0.1)
            else:
                result.update(ok=False, error="material selection verification timeout")
            # 2、从正式仓库重读，不能仅凭 DOM 显示名称判断保存成功。
            if result.get("member_id"):
                member = host.call(host.runtime.member(result["member_id"]))
                result["persisted_avatar"] = member["avatar_id"]
                result["ok"] = result.get("ok") and member["avatar_id"] == result["avatar_id"]
            if not result.get("ok"):
                capture_webview(window, root / "failure.png")
            (root / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception as error:
            result.update(ok=False, error=str(error))
        finally:
            window.destroy()

    # 2、结束时释放测试窗口与资料连接，当前用户应用保持运行。
    try:
        webview.start(verify, gui="edgechromium", debug=False)
    finally:
        host.close()
    print(json.dumps({"root": str(root), **result}, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
