"""发行与源码共用的最小入口。"""

import logging
import os


def main() -> None:
    """因为 SDK 导入前必须关闭外发日志，需要先配置进程再延迟加载桌面组合入口。"""
    # 1、仅修改当前应用进程，不读取或修改用户全局系统设置。
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["PYWEBVIEW_LOG"] = "WARNING"
    for logger_name in ("openai", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    # 2、桌面层负责窗口生命周期，模型框架不进入入口文件。
    from roomcrew.desktop.window import main as run_window

    run_window()


if __name__ == "__main__":
    main()
