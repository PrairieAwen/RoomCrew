"""测试窗口自身的 WebView2 渲染导出；不读取桌面其他应用或调用系统输入。"""

from pathlib import Path
from typing import Any


def capture_webview(window: Any, path: Path) -> None:
    """因为测试需要目检原生渲染结果，需要由自己创建的 WebView2 导出 PNG，避免截到其他窗口。"""
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
    from System import Action
    from System.IO import MemoryStream

    # 1、捕获必须由本测试 WebView 所属线程发起，异步等待放在测试线程，不能阻塞 UI。
    request: dict[str, Any] = {}

    def begin_capture() -> None:
        """因为 WebView2 对象具有 UI 线程亲和性，需要在所属线程启动只读渲染导出。"""
        # 1、只捕获此窗口的客户区，不操作用户系统窗口、鼠标或剪贴板。
        stream = MemoryStream()
        request["stream"] = stream
        request["task"] = window.native.webview.CoreWebView2.CapturePreviewAsync(
            CoreWebView2CapturePreviewImageFormat.Png, stream
        )

    window.native.Invoke(Action(begin_capture))
    try:
        if not request["task"].Wait(10000):
            raise TimeoutError("原生渲染导出超时")
        # 2、输出为本次测试文件，不修改任何人物素材和用户业务数据。
        path.write_bytes(bytes(request["stream"].ToArray()))
    finally:
        request["stream"].Dispose()
