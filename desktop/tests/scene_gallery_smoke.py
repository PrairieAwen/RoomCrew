"""素材总览的原生加载验收；不读取模型配置或用户会话。"""

import argparse
import json
import threading
from pathlib import Path
from uuid import uuid4

import webview
from native_capture import capture_webview

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """因为总览也必须能查看实际新图集，需要在独立 WebView 中验证家具、四角色和动作帧。"""
    # 1、只允许本仓库源码或发行 UI，截图另存测试目录，不访问任何私有业务文件。
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-root", type=Path, default=ROOT / "desktop/ui")
    ui = parser.parse_args().ui_root.resolve(strict=True)
    if ui != ROOT / "desktop/ui" and not ui.is_relative_to(ROOT / "dist"):
        raise ValueError("素材验收目录越界")
    output = ROOT / ".cache/scene-gallery-smoke" / uuid4().hex
    output.mkdir(parents=True)
    window = webview.create_window(
        "RoomCrew asset gallery verification",
        str(ui / "index.html"),
        width=1400,
        height=1000,
    )
    result: dict[str, object] = {}

    def inspect() -> None:
        """因为图片解码异步完成，需要逐类切换后检查真实画布像素，并记录加载失败。"""
        # 1、操作正式选择器，让其调用正式刷新函数；不注入伪造素材或跳过 Image.decode。
        try:
            base = window.get_current_url().rsplit("/", 1)[0]
            window.load_url(base + "/studio/assets/scene-v1/index.html")
            for _ in range(100):
                if window.evaluate_js("typeof refreshSceneInspector==='function'"):
                    break
                threading.Event().wait(0.1)
            else:
                raise RuntimeError("素材总览未加载")
            window.evaluate_js(
                "window.galleryFailures=[];window.originalFailure=showAssetFailure;"
                "/** 因为卡片失败需要可定位，需要在验收窗口保留原始异常。 */"
                "showAssetFailure=function captureGalleryFailure(card,error){"
                "/* 1、仍调用正式失败处理，不隐藏错误或修改图片加载结果。 */"
                "window.galleryFailures.push(String(error));window.originalFailure(card,error);};"
            )
            for kind, count, frame in (
                ("furniture", 14, 0),
                ("paired", 4, 2),
                ("transition", 4, 4),
            ):
                window.evaluate_js(
                    f"document.getElementById('kind').value='{kind}';"
                    f"document.getElementById('frame').value='{frame}';refreshSceneInspector();"
                )
                for _ in range(100):
                    state = window.evaluate_js(
                        "({count:document.querySelectorAll('.card').length,"
                        "errors:[...document.querySelectorAll('.card p')].map("
                        "node=>node.closest('.card').querySelector('strong').textContent),"
                        "painted:[...document.querySelectorAll('.card canvas')].every("
                        "canvas=>canvas.getContext('2d').getImageData(0,0,280,200).data.some("
                        "(value,index)=>index%4===3&&value>100))})"
                    )
                    if state["errors"]:
                        details = window.evaluate_js("window.galleryFailures")
                        raise RuntimeError(f"素材加载失败: {kind} {state['errors']} {details}")
                    if state["count"] == count and state["painted"]:
                        break
                    threading.Event().wait(0.1)
                else:
                    raise RuntimeError(f"素材预览为空: {kind}")
                capture_webview(window, output / f"{kind}.png")
            # 2、成功和失败都可观察；本机真实窗口关闭后才输出结果供外层读取。
            result.update(ok=True, screenshots=str(output), groups=3)
        except Exception as error:
            result.update(ok=False, error=str(error))
        finally:
            window.destroy()

    webview.start(inspect, gui="edgechromium", private_mode=True)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
