"""窗口初始尺寸随 Windows 工作区缩放，避免输入框落到屏幕外。"""

import ctypes
from ctypes.wintypes import RECT


def initial_window_size() -> tuple[int, int, tuple[int, int]]:
    """因为常见笔记本高度低于原始 900 像素，需要按当前工作区限制初始窗口和最小尺寸。"""
    # 1、只读取系统工作区，不改变显示设置或 DPI 配置。
    area = RECT()
    available = ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0)
    width = area.right - area.left if available else 1280
    height = area.bottom - area.top if available else 768
    # 2、打包进程可处于 DPI aware 模式，WebView2 会再次缩放，先统一为逻辑尺寸。
    try:
        scale = max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96)
    except AttributeError:
        scale = 1.0
    width, height = int(width / scale), int(height / scale)
    # 3、给系统边框留出余量，窄屏下仍允许窗口完全显示输入区。
    width, height = max(640, min(1380, width - 32)), max(480, min(900, height - 32))
    return width, height, (min(1000, width), min(640, height))
