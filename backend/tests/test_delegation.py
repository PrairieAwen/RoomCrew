"""配置人数、并发租约、取消释放及空间名单边界。"""

import asyncio
from typing import Any, cast

import pytest
from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import ToolMessage

from roomcrew.contracts.agents import ActorRef, AgentSpec
from roomcrew.middleware.delegation import ConfiguredDelegationMiddleware


def request(target: str, identifier: str) -> ToolCallRequest:
    """因为入口参数需要与真实 task 工具一致，需要构造只含公开目标与模型调用 ID 的请求。"""
    # 1、没有构造假的模型执行结果，只验证确定性调用边界。
    return ToolCallRequest(
        tool_call={"name": "task", "args": {"subagent_type": target}, "id": identifier},
        tool=None,
        state={},
        runtime=cast(Any, None),
    )


async def test_single_member_cannot_be_cloned_and_cancel_releases_slot() -> None:
    """因为同一已配置成员不能被并发克隆，需要验证重复调用被拒绝且取消后可以重新使用。"""
    # 1、固定两个已配置身份；通用外援与其他会议室 ID 不在当前名单。
    policy = ConfiguredDelegationMiddleware(
        [
            AgentSpec(ActorRef("worker", "definition", "同事"), "member_worker", "工作", ""),
        ]
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def execute(call: ToolCallRequest) -> ToolMessage:
        """因为需要观察租约覆盖真正执行期间，需要用事件控制工具处理时间。"""
        # 1、记录已进入的实际 handler，未知目标不能到达这里。
        calls.append(call.tool_call["id"])
        entered.set()
        await release.wait()
        return ToolMessage(content="完成", tool_call_id=call.tool_call["id"])

    first = asyncio.create_task(policy.awrap_tool_call(request("member_worker", "one"), execute))
    await entered.wait()
    # 2、同成员重复、默认外援和跨空间猜测都不能进入工具执行。
    for target in ("member_worker", "general-purpose", "member_other_room"):
        result = await policy.awrap_tool_call(request(target, "rejected"), execute)
        assert isinstance(result, ToolMessage) and result.status == "error"
    assert calls == ["one"]
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    # 3、取消释放租约，不会永久锁住成员；也没有无界等待或盲重试。
    release.set()
    result = await policy.awrap_tool_call(request("member_worker", "next"), execute)
    assert isinstance(result, ToolMessage) and result.status != "error"
    assert calls == ["one", "next"]
