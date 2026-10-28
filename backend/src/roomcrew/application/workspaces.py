"""多个独立 Runtime 的本机装配与显式空间请求分派。"""

import asyncio
from collections.abc import Callable
from typing import Any

from roomcrew.application.runtime import Runtime
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.workspaces import WorkspaceRepository, offline_workspace_status

WORKSPACE_METHODS = frozenset(
    {
        "overview",
        "configuration",
        "agent_configurations",
        "save_agent_configuration",
        "save_configuration",
        "test_connection",
        "test_mcp_connection",
        "new_conversation",
        "submit",
        "events",
        "native_events",
        "artifacts",
        "read_artifact",
        "member",
        "save_member",
        "member_events",
        "questions",
        "respond",
        "stop",
    }
)


class WorkspaceHub:
    def __init__(
        self,
        paths: AppPaths,
        runtime_factory: Callable[[AppPaths], Runtime] = Runtime,
        extra_methods: frozenset[str] = frozenset(),
    ) -> None:
        """因为会议室要各自保留成员与任务，需要用空间目录装配多个独立执行底座。"""
        # 1、这里只组装现有生产 Runtime，不新增模型循环或跨空间共享可变上下文。
        self.paths = paths
        self._runtime_factory = runtime_factory
        self._methods = WORKSPACE_METHODS | extra_methods
        self.repository = WorkspaceRepository(paths.data / "workspaces.sqlite")
        self.runtimes: dict[str, Runtime] = {}
        self.active_id = self.repository.active()
        self._opening = asyncio.Lock()

    async def start(self) -> None:
        """因为首次窗口需要已有房间，需要只打开上次选择的空间而非遍历全部数据。"""
        # 1、其他房间按需启动；不自动重新执行历史 Run。
        await self.runtime_for(self.active_id)

    @property
    def current(self) -> Runtime:
        """因为宿主和本机验证需要获取当前实例，需要返回已就绪的运行时引用而不隐式创建。"""
        # 1、界面业务请求仍显式绑定空间 ID，不依赖这个便捷属性路由。
        return self.runtimes[self.active_id]

    async def runtime_for(self, identifier: str) -> Runtime:
        """因为并发查询可能同时打开同一会议室，需要串行初始化并防止重复连接和状态恢复。"""
        # 1、先验证目录，再解析受限路径；空间不能通过请求凭空出现。
        self.repository.get(identifier)
        async with self._opening:
            if identifier not in self.runtimes:
                runtime = self._runtime_factory(self.paths.for_workspace(identifier))
                await runtime.start()
                self.runtimes[identifier] = runtime
            return self.runtimes[identifier]

    async def state(self) -> dict[str, Any]:
        """因为左侧要区分后台工作与人工待办，需要汇总最小计数而不混入其他空间的内容。"""
        # 1、当前进程的在途任务以各实例为准，未打开空间只读查询持久待办。
        rooms = []
        for item in self.repository.list():
            runtime = self.runtimes.get(item["id"])
            if runtime:
                pending = len(await runtime.questions())
                count = len(runtime.active)
                status = {
                    "active_runs": count,
                    "pending_count": pending,
                    "status": "执行中" if count else "待答复" if pending else "空闲",
                }
            else:
                folder = (
                    self.paths.data
                    if item["id"] == "default"
                    else self.paths.root / "workspaces" / item["id"] / "data"
                )
                status = offline_workspace_status(folder / "sessions.sqlite")
            rooms.append({**item, **status})
        return {"active": self.repository.get(self.active_id), "workspaces": rooms}

    async def create(self, name: str) -> dict[str, Any]:
        """因为创建空间应立即进入对应会议室，需要初始化独立数据后保存当前选择。"""
        # 1、创建记录和房间是一对一关系，不复制其他空间成员、轨迹或文件。
        item = self.repository.create(name)
        await self.select(item["id"])
        return await self.state()

    async def select(self, identifier: str) -> dict[str, Any]:
        """因为切换房间不能中断后台任务，需要只改变用户视图的活动 ID。"""
        # 1、先确保新实例可用，失败时保持旧选择；旧实例继续运行。
        await self.runtime_for(identifier)
        self.active_id = identifier
        self.repository.select(identifier)
        return await self.state()

    async def rename(self, identifier: str, name: str) -> dict[str, Any]:
        """因为改名不应重置房间，需要保留空间 ID、任务和布局，仅更新显示名称。"""
        # 1、所有窗口下次读取目录即可得到同一名称。
        self.repository.rename(identifier, name)
        return await self.state()

    async def invoke(self, identifier: str, method: str, args: list[Any]) -> Any:
        """因为切换期间会有迟到请求，需要把每次操作固定到调用时的空间，而不是当前显示房间。"""
        # 1、只允许明确的 Runtime 用例；不接受属性、私有方法、执行器或任意导入。
        if method not in self._methods or not isinstance(args, list) or len(args) > 8:
            raise ValueError("不支持的工作空间请求")
        runtime = await self.runtime_for(identifier)
        if method == "save_configuration" and await self._global_busy():
            raise ValueError("请先完成所有工作空间中的任务或待答复，再修改共享模型配置")
        if (
            method in {"submit", "respond"}
            and not runtime.active
            and sum(bool(item.active) for item in self.runtimes.values()) >= 4
            and not runtime.execution_replay(method, args)
        ):
            raise ValueError("当前最多四个工作空间同时执行任务")
        result = await getattr(runtime, method)(*args)
        # 2、只给画布和概览添加普通空间身份；业务事件和产物依旧保存在各自目录。
        if method == "overview":
            result = {
                **result,
                "workspace": self.repository.get(identifier),
                "workspaces": (await self.state())["workspaces"],
            }
        return result

    async def _global_busy(self) -> bool:
        """因为模型配置由用户统一维护，需要检查所有会议室，避免让未答复任务失去原配置引用。"""
        # 1、未打开的空间也检查待办；判断不读取或公开实际问题正文。
        state = await self.state()
        return any(
            item["active_runs"] or item["pending_count"] or item["status"] == "需要检查"
            for item in state["workspaces"]
        )

    async def close(self) -> None:
        """因为关闭桌面要停止全部后台会议室，需要逐个释放执行、检查点与产品连接。"""
        # 1、继续使用各 Runtime 的安全退出顺序，不遗漏未显示房间的任务。
        errors = []
        for runtime in self.runtimes.values():
            try:
                await runtime.close()
            except Exception as error:
                errors.append(error)
        # 2、一个房间关闭失败仍继续释放其余房间，最终向宿主报告异常。
        self.repository.close()
        if errors:
            raise ExceptionGroup("部分工作空间关闭失败", errors)
