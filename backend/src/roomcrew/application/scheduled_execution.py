"""持久触发记录与通用执行入口的协调；时间检查器不需要理解这些绑定。"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any

from roomcrew.application.dispatcher import TaskDispatcher
from roomcrew.application.runtime import Runtime
from roomcrew.contracts.schedules import DispatchBusy
from roomcrew.scheduling.triggers import next_fire
from roomcrew.storage.schedules import ScheduleStore


class ScheduleCoordinator:
    def __init__(
        self,
        store: ScheduleStore,
        dispatcher: TaskDispatcher,
        runtime_for: Callable[[str], Awaitable[Runtime]],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """因为到期只产生业务触发，需要由应用协调器解析绑定并复用统一受理入口。"""
        # 1、时间检查器仅调用 poll，不持有空间、Agent、提示词或模型对象。
        self._store = store
        self._dispatcher = dispatcher
        self._runtime_for = runtime_for
        self._now = now or self._utc_now

    @staticmethod
    def _utc_now() -> datetime:
        """因为调度需要可验证的真实时钟，需要集中提供带时区的当前 UTC 时间。"""
        # 1、生产使用系统时间，测试可注入独立时钟而不修改系统或生产规则。
        return datetime.now(UTC)

    def _validate(self, occurrence: dict[str, Any]) -> None:
        """因为空间加载期间用户仍可能取消任务，需要在真正受理的线性化点再次检查。"""
        # 1、取消、修改或过期的排队项不能被迟到的唤起重新提交。
        if not self._store.valid(occurrence) or self._now().timestamp() > occurrence["deadline"]:
            raise ValueError("定时任务已经变更、取消或超过执行窗口")

    async def _receipt(self, occurrence: dict[str, Any]) -> dict[str, Any] | None:
        """因为两个产品库无法做跨库原子提交，需要用固定请求 ID 查询实际受理结果。"""
        # 1、先对账再重发；进程崩溃后未知外部效果不会自动创建另一轮执行。
        runtime = await self._runtime_for(occurrence["workspace_id"])
        return runtime.store.run_by_request("schedule:" + occurrence["id"])

    async def poll(self) -> None:
        """因为重启后可能存在未回填状态，需要先对账旧 Run，再物化到期安排并尝试派发。"""
        # 1、已受理和待答复状态以真实 Run 为准，等待人工时同计划不重入。
        failures = 0
        for occurrence in self._store.occurrences(("running", "waiting_user")):
            try:
                run = await self._receipt(occurrence)
                self._store.mark(
                    occurrence["id"],
                    run["status"] if run else "interrupted",
                    run["id"] if run else None,
                    "MISSING_RUN" if run is None else None,
                )
            except Exception:
                failures += 1
        now = self._now()
        for schedule in self._store.due(now.timestamp()):
            try:
                following = next_fire(schedule["trigger"], now)
                self._store.materialize(
                    schedule, following.timestamp() if following else None, now.timestamp()
                )
            except Exception:
                failures += 1
        # 2、坏记录或不可读空间不能阻断其他计划；未知受理状态保留，不误判为尚未执行。
        for occurrence in self._store.occurrences(("pending",)):
            try:
                await self._dispatch(occurrence)
            except Exception:
                failures += 1
        # 3、处理其余正常项后再报告不健康，由通用定时器有界退避，不暴露异常原文。
        if failures:
            raise RuntimeError("部分定时任务暂时无法对账或读取，请检查本地数据")

    async def _dispatch(self, occurrence: dict[str, Any]) -> None:
        """因为重复触发不能制造第二轮外部效果，需要先对账并只对已确认未受理的项尝试执行。"""
        # 1、每次触发使用固定请求和会话 ID，已存在的 Run 只补回状态。
        run = await self._receipt(occurrence)
        if run is not None:
            self._store.mark(occurrence["id"], run["status"], run["id"])
            return
        if self._now().timestamp() > occurrence["deadline"]:
            self._store.mark(occurrence["id"], "expired", error="MISSED_DEADLINE")
            return
        if not self._store.valid(occurrence):
            self._store.mark(occurrence["id"], "cancelled", error="PLAN_CHANGED")
            return
        # 2、排队只因容量不足重试，目标和配置错误则明确阻塞，避免盲目重复业务操作。
        try:
            reply = await self._dispatcher.invoke(
                occurrence["workspace_id"], "_submit_scheduled", [occurrence],
                partial(self._validate, occurrence),
            )
            self._store.mark(occurrence["id"], reply["status"], reply["run_id"])
        except DispatchBusy:
            return
        except Exception:
            run = await self._receipt(occurrence)
            self._store.mark(
                occurrence["id"], run["status"] if run else "blocked",
                run["id"] if run else None,
                "TARGET_OR_CONFIGURATION" if run is None else None,
            )
