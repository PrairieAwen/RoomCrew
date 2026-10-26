"""用真实 WebView 和矢量骨架导出角色素材样例，工具不进入发行包。"""

import base64
import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

sys.path[:0] = [
    str(Path(__file__).resolve().parents[3] / "backend/src"),
    str(Path(__file__).resolve().parents[3] / "desktop/src"),
]

import webview

from roomcrew.assets.library import AvatarLibrary
from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.api import DesktopAPI
from roomcrew_desktop.host import RuntimeThread


def main() -> None:
    """因为自定义素材需要完整可编辑样例，需要通过正式骨架生成 PNG 和真实有效的清单。"""
    # 1、独立本地数据，不读取用户模型配置，也不覆盖已有用户素材。
    root = Path(__file__).resolve().parents[3]
    target = root / "doc/assets/crew-avatar-example"
    if any((target / name).exists() for name in ("avatar.json", "atlas.png")):
        raise ValueError("样例文件已存在，请使用新目录或手动保存自己的副本")
    target.mkdir(parents=True, exist_ok=True)
    data = root / ".cache/avatar-export" / uuid4().hex
    host = RuntimeThread(AppPaths.create(data))
    result: dict = {}
    window = webview.create_window(
        "RoomCrew avatar export",
        str(host.runtime.paths.desktop_ui / "index.html"),
        js_api=DesktopAPI(host),
        hidden=True,
        width=1100,
        height=700,
    )

    def export() -> None:
        """因为页面绘图库在加载后才可用，需要等资源就绪再运行确定性的样例导出。"""
        # 1、仅注入项目自己的开发导出工具，不修改生产状态。
        try:
            window.events.loaded.wait(20)
            window.evaluate_js((root / "desktop/tools/web/export-avatar.js").read_text("utf-8"))
            for _ in range(500):
                value = window.evaluate_js("window.__avatarExport || null")
                if value:
                    result.update(value)
                    break
                threading.Event().wait(0.1)
        finally:
            window.destroy()

    try:
        # 2、Canvas 光栅化使用当前正式骨架；输出仍按生产导入器再次验证。
        webview.start(export, gui="edgechromium", debug=False, private_mode=True)
    finally:
        host.close()
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error", "导出超时")))
    (target / "avatar.json").write_text(
        json.dumps(result["manifest"], ensure_ascii=False, indent=2), "utf-8"
    )
    (target / "atlas.png").write_bytes(base64.b64decode(result["image"].split(",", 1)[1]))
    summary = AvatarLibrary(data / "template-verification").import_manifest(target / "avatar.json")
    print(
        json.dumps(
            {
                "ok": True,
                "frames": result["frames"],
                "clips": len(result["manifest"]["clips"]),
                "validated": summary["id"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
