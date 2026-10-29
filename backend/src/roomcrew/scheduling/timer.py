"""只负责周期唤起回调的时间检查器；不知道工作空间、Agent 或数据库结构。"""

import asyncio
from collections.abc import Awaitable, Callable


class SchedulerTimer:
    def __init__(self, poll: Callable[[], Awaitable[None]], interval: float = 1.0) -> None:
        """因为定时器不应依赖业务对象，需要只注入一个异步检查入口并限制扫描频率。"""
        # 1、实际到期规则与状态由回调管理，定时器不会直接调用模型。
        self._poll = poll
        self._interval = max(0.1, interval)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.failed = False

    def start(self) -> None:
        """因为宿主可能重复初始化，需要只启动一份检查协程。"""
        # 1、定时器与现有运行时共用事件循环，不另起线程访问 SQLite。
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """因为短暂存储异常不能永远停止调度，需要有界退避并保留健康标记。"""
        # 1、单次检查结束后才进入下一次，不会重入或把异常文本写入普通日志。
        while not self._stop.is_set():
            try:
                await self._poll()
                self.failed = False
            except asyncio.CancelledError:
                raise
            except Exception:
                self.failed = True
            try:
                await asyncio.wait_for(self._stop.wait(), 5.0 if self.failed else self._interval)
            except TimeoutError:
                continue

    async def close(self) -> None:
        """因为退出后不能继续生成触发记录，需要先等待检查协程停止，再关闭业务资源。"""
        # 1、幂等关闭且取回取消结果，数据库由宿主随后释放。
        if self._task is not None:
            self._stop.set()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
