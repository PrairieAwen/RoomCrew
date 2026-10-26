"""桌面与异步运行时之间的线程生命周期。"""

import asyncio
import concurrent.futures
import threading
import time
from collections.abc import Coroutine
from typing import Any

from roomcrew.application.runtime import Runtime
from roomcrew.platform.paths import AppPaths


class RuntimeThread:
    def __init__(self, paths: AppPaths) -> None:
        """因为桌面窗口必须占用主线程，需要用独立事件循环承载异步模型和工具调用。"""
        # 1、用就绪事件确认后端真正可用，避免窗口先接受任务再发现初始化失败。
        self._ready = threading.Event()
        self._closing = threading.Event()
        self._error: Exception | None = None
        self._paths = paths
        self.loop: asyncio.AbstractEventLoop
        self.runtime: Runtime
        self._thread = threading.Thread(target=self._serve, name="roomcrew-runtime", daemon=True)
        self._thread.start()
        if not self._ready.wait(60) or self._error:
            raise RuntimeError("RoomCrew 本地运行时启动失败") from self._error

    def _serve(self) -> None:
        """因为 asyncio 对象不能跨线程随意使用，需要在同一后台线程创建、运行并关闭服务。"""
        # 1、初始化本线程循环和运行时，错误通过启动握手返回主线程。
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.runtime = Runtime(self._paths)
            self.loop.run_until_complete(self.runtime.start())
        except Exception as error:
            self._error = error
            self._ready.set()
            self.loop.close()
            return
        self._ready.set()
        # 2、停止时关闭所有异步任务、数据库和执行器，再释放事件循环。
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.runtime.close())
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()

    def call[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        """因为 WebView 桥方法在工作线程触发，需要把请求提交到后端所属循环并等待结果。"""
        # 1、统一跨线程调度；连接探测最长遵循模型配置的有界超时。
        if self._closing.is_set():
            coroutine.close()
            raise ValueError("应用正在关闭")
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        deadline = time.monotonic() + 620
        # 2、等待期间也观察退出状态，避免关闭窗口后桥接工作线程仍等待数分钟。
        while not self._closing.is_set():
            try:
                return future.result(timeout=0.25)
            except concurrent.futures.TimeoutError:
                if time.monotonic() >= deadline:
                    future.cancel()
                    raise ValueError("本地请求等待超时，请停止任务后重试") from None
        future.cancel()
        raise ValueError("应用正在关闭")

    def close(self) -> None:
        """因为关闭窗口需要同时结束本地后端，需要通知循环退出并等待资源释放。"""
        # 1、退出流程由主线程触发，不把关闭动作暴露为 Agent 工具。
        if self._thread.is_alive():
            self._closing.set()
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout=20)
