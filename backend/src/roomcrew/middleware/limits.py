"""模型调用边界的共享额度，覆盖主 Agent、子 Agent 和摘要调用。"""

import threading

from roomcrew.contracts.errors import ExecutionError


class ModelCallBudget:
    def __init__(self, maximum: int = 32) -> None:
        """因为子 Agent 和摘要不能各自重置额度，需要为同一次 Run 建立共享、线程安全的计数器。"""
        # 1、该对象每 Run 新建；绑定模型工具时只共享本 Run 的同一个对象。
        if maximum < 1:
            raise ValueError("模型调用上限必须为正数")
        self._maximum = maximum
        self._calls = 0
        self._lock = threading.Lock()

    def consume(self) -> None:
        """因为收到开始事件时请求可能已经发出，需要在进入 SDK 前原子预占一次调用额度。"""
        # 1、同步和异步模型入口使用相同锁，不在锁内执行网络或摘要。
        with self._lock:
            if self._calls >= self._maximum:
                raise ExecutionError("RUN_LIMIT")
            self._calls += 1

    @property
    def calls(self) -> int:
        """因为终态需要记录实际预占调用数，需要安全读取计数而不暴露模型配置。"""
        # 1、只返回次数，失败请求也计入已发起调用。
        with self._lock:
            return self._calls
