"""面向通用 Agent 的专用计划工具；只经受限服务合同执行，不读写数据库。"""

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool

from roomcrew.contracts.schedules import ScheduleCommands


class ScheduleToolset:
    def __init__(self, service: ScheduleCommands, member_id: str, conversation_id: str) -> None:
        """因为同一定义可由多个形象执行，需要给本次工具闭包固定真实成员和会话身份。"""
        # 1、服务已经绑定空间，不发布可由模型修改的 workspace_id 或配置路径。
        self._service = service
        self._member = member_id
        self._conversation = conversation_id

    def _command(self, runtime: ToolRuntime) -> str:
        """因为框架恢复会重放工具，需要用模型工具调用 ID 生成稳定且不含秘密的命令标识。"""
        # 1、同一次工具恢复命中原写入结果，不让重启或重试创建重复日程。
        if not runtime.tool_call_id:
            raise ValueError("定时工具缺少实际调用标识")
        return hashlib.sha256(
            (self._conversation + ":" + runtime.tool_call_id).encode()
        ).hexdigest()

    @staticmethod
    async def _result(operation: Awaitable[Any]) -> dict[str, Any]:
        """因为参数错误应允许模型有限修正，需要返回可理解的工具结果而不把整轮任务直接变成异常。"""
        # 1、只公开服务的确定性校验错误，未知错误不返回堆栈、路径或内部对象。
        try:
            return {"ok": True, "result": await operation}
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        except Exception:
            return {"ok": False, "error": "定时任务操作失败，请查看本地任务列表后重试"}

    async def list_schedules(
        self, query: str = "", include_inactive: bool = False
    ) -> dict[str, Any]:
        """因为取消或修改前需要准确目标，需要列出本工作空间的定时任务、接单成员与 revision。"""
        # 1、query 可匹配标题或任务正文，include_inactive 可查看已取消和已结束记录。
        return await self._result(self._service.list_schedules(query, include_inactive))

    async def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        """因为同名计划可能有多个，需要按准确 ID 获取配置版本和最近执行历史。"""
        # 1、服务验证空间归属，返回结果不包含目标 Agent 的秘密或系统提示词。
        return await self._result(self._service.get_schedule(schedule_id))

    async def create_schedule(
        self,
        title: str,
        instruction: str,
        trigger: dict[str, Any],
        runtime: ToolRuntime,
        target_member_id: str = "",
    ) -> dict[str, Any]:
        """因为用户可要求未来由某个已配置 Agent 工作，需要新增持久计划，成功后才可宣称已安排。

        trigger 示例：每五分钟 {"type":"interval","seconds":300}；每天两点半
        {"type":"daily","time":"14:30","timezone":"Asia/Shanghai"}；每周另加
        weekdays:[0,1,2,3,4]（周一为0）；一次性 {"type":"once","at":"带偏移的ISO时间"}。
        target_member_id 留空为当前成员；正文须描述未来真正要做的工作，不在本次会话等待。
        """
        # 1、真实成员 ID 与服务空间共同确定接单身份，不复制当前对话上下文或 MCP 配置。
        return await self._result(
            self._service.create_schedule(
                {
                    "title": title,
                    "instruction": instruction,
                    "trigger": trigger,
                    "target_member_id": target_member_id or self._member,
                },
                self._command(runtime),
            )
        )

    async def update_schedule(
        self, schedule_id: str, changes: dict[str, Any], revision: int, runtime: ToolRuntime
    ) -> dict[str, Any]:
        """因为用户会调整时间、任务或执行者，需要先查询 revision，再修改同一空间计划。

        changes 支持 title、instruction、trigger、target_member_id、grace_seconds。
        修改只影响尚未受理的未来执行，不改已经运行的任务。
        """
        # 1、版本冲突时先重新查询，不能覆盖别的人工修改。
        return await self._result(
            self._service.update_schedule(schedule_id, changes, revision, self._command(runtime))
        )

    async def pause_schedule(
        self, schedule_id: str, revision: int, runtime: ToolRuntime
    ) -> dict[str, Any]:
        """因为临时停用与永久取消不同，需要暂停后续触发并保留可恢复的安排。"""
        # 1、不会停止已经受理的 Run，停止当前任务应由用户明确提出。
        return await self._result(
            self._service.set_schedule_state(
                schedule_id, "paused", revision, self._command(runtime)
            )
        )

    async def resume_schedule(
        self, schedule_id: str, revision: int, runtime: ToolRuntime
    ) -> dict[str, Any]:
        """因为用户可能恢复暂停的计划，需要重新校验目标与未来时间后再启用。"""
        # 1、已经删除的计划不能通过恢复复活。
        return await self._result(
            self._service.set_schedule_state(
                schedule_id, "active", revision, self._command(runtime)
            )
        )

    async def delete_schedule(
        self, schedule_id: str, revision: int, runtime: ToolRuntime
    ) -> dict[str, Any]:
        """因为用户可能说取消某项定时任务，需要永久停止后续安排并保留历史记录。

        先 list_schedules/get_schedule 确认准确 ID 和 revision；多个匹配时先询问用户。
        该操作不回滚历史文件，也不停止已经运行的任务。
        """
        # 1、删除由后端同事务废弃尚未受理的触发，不能只在聊天中口头确认取消。
        return await self._result(
            self._service.set_schedule_state(
                schedule_id, "deleted", revision, self._command(runtime)
            )
        )


def schedule_tools(
    service: ScheduleCommands, member_id: str, conversation_id: str, allow_write: bool = True
) -> list[BaseTool]:
    """因为主子 Agent 共用同一配置机制，需要在装配点生成独立工具并限制自动运行的长期写权限。"""
    # 1、自动触发的 Run 只读计划，避免任务递归产生更多定时安排；用户对话允许专用管理工具。
    tools = ScheduleToolset(service, member_id, conversation_id)
    methods: list[Callable[..., Awaitable[dict[str, Any]]]] = [
        tools.list_schedules,
        tools.get_schedule,
    ]
    if allow_write:
        methods.extend(
            [
                tools.create_schedule,
                tools.update_schedule,
                tools.pause_schedule,
                tools.resume_schedule,
                tools.delete_schedule,
            ]
        )
    return [
        StructuredTool.from_function(
            coroutine=method, name=method.__name__, metadata={"roomcrew_tool_kind": "tool"}
        )
        for method in methods
    ]
