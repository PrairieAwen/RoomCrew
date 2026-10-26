"""Windows 独立应用入口；用户原有 main.py 保持不变。"""

import argparse
import ctypes
import msvcrt
from pathlib import Path


def main() -> None:
    """因为用户需要双击即可运行，需要完成本机数据定位、单实例控制、后端与桌面窗口启动。"""
    # 1、创建原生桌面所需的进程、路径和数据根。
    from roomcrew.desktop.api import DesktopAPI
    from roomcrew.desktop.host import RuntimeThread
    from roomcrew.platform.paths import AppPaths

    parser = argparse.ArgumentParser(description="RoomCrew · 一间事务所")
    parser.add_argument("--data-dir", type=Path, help="开发验证使用的独立数据目录")
    paths = AppPaths.create(parser.parse_args().data_dir)
    # 2、同一数据根只运行一个实例，避免两个进程并发消费同一会话 checkpoint。
    lock = (paths.private / "instance.lock").open("a+b")
    lock.seek(0)
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        ctypes.windll.user32.MessageBoxW(
            None, "RoomCrew 已在运行，请使用已经打开的窗口。", "RoomCrew", 0x40
        )
        lock.close()
        return
    host = None
    # 3、明确使用 WebView2，不在缺少依赖时静默打开外部浏览器充当桌面程序。
    try:
        import webview

        host = RuntimeThread(paths)
        window = webview.create_window(
            "RoomCrew · 一间事务所",
            str(paths.frontend / "index.html"),
            js_api=DesktopAPI(host),
            width=1380,
            height=900,
            min_size=(1000, 680),
            background_color="#161719",
        )
        if window is None:
            raise RuntimeError("无法创建应用窗口")
        webview.start(gui="edgechromium", debug=False, private_mode=True)
    except Exception:
        ctypes.windll.user32.MessageBoxW(
            None,
            "应用启动失败。请确认已安装 Microsoft Edge WebView2 Runtime，且应用数据目录可写。\n"
            "首次运行请保持完整的 RoomCrew 程序目录，不要只移动 exe。",
            "RoomCrew",
            0x10,
        )
    finally:
        # 4、窗口退出时一并停止后端，保证独立应用不遗留后台服务。
        if host:
            host.close()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()
