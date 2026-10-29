"""手动任务、人工恢复与定时触发共用的受理闸门。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from roomcrew.application.runtime import Runtime
from roomcrew.contracts.schedules import DispatchBusy


class TaskDispatcher:
    def __init__(
        self, runtime_for: Callable[[str], Awaitable[Runtime]], runtimes: dict[str, Runtime]
    ) -> None:
        """因为内部定时调用也必须遵守并发上限，需要把准入从桌面请求路由下沉为共用能力。"""
        # 1、锁只覆盖受理，不覆盖模型网络执行，避免一个慢任务阻塞所有空间。
        self._runtime_for = runtime_for
        self._runtimes = runtimes
        self._admission = asyncio.Lock()

    async def invoke(
        self,
        workspace_id: str,
        method: str,
        args: list[Any],
        validate: Callable[[], None] | None = None,
    ) -> Any:
        """因为空间初始化会让出循环，需要在持锁受理点重新验证计划并检查全局容量。"""
        # 1、所有真正执行入口走同一闸门；计划变更回调不能自行创建 Runtime。
        async with self._admission:
            runtime = await self._runtime_for(workspace_id)
            if validate is not None:
                validate()
            if method in {"submit", "submit_chat", "respond", "_submit_scheduled"}:
                if (sum(len(item.active) for item in self._runtimes.values()) >= 8
                    and not runtime.execution_replay(method, args)):
                    raise DispatchBusy("当前最多八个会话同时执行任务")
                if (
                    not runtime.active
                    and sum(bool(item.active) for item in self._runtimes.values()) >= 4
                    and not runtime.execution_replay(method, args)
                ):
                    raise DispatchBusy("当前最多四个工作空间同时执行任务")
                if method == "_submit_scheduled" and runtime.active:
                    raise DispatchBusy("目标工作空间正在执行任务，定时任务继续排队")
            # 2、此方法仅由应用装配代码传入已校验的方法名，不直接暴露给桌面桥。
            return await getattr(runtime, method)(*args)
