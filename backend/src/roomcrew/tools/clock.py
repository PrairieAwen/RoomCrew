"""本机日期时间工具。"""

from datetime import datetime

from langchain_core.tools import tool


@tool
def get_local_time() -> str:
    """因为任务可能依赖真实日期，需要读取本机带时区的当前时间，避免模型猜测。"""
    # 1、提供实际本机日期时间，不写入任何业务预设内容。
    return datetime.now().astimezone().isoformat(timespec="seconds")
