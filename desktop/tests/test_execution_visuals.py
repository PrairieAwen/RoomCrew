"""MCP 电脑动作与整轮完成的确定性表现回归。"""

from roomcrew_desktop.accounts import interaction_profile
from roomcrew_desktop.presentation.animation import animation_hint, visual_cue
from roomcrew_desktop.presentation.reducer import actor_view, reduce_event


def trace(seq: int, kind: str, scope: str = "main", **payload) -> dict:
    """因为动画只应消费已提交事实，需要用稳定身份构造可重放的阶段事件。"""
    # 1、正文可包含任意文字，但不参与任务状态判定。
    return {
        "seq": seq,
        "kind": kind,
        "run_id": "run",
        "scope": scope,
        "member_id": "assistant",
        "created_at": "2026-10-30T00:00:00Z",
        "payload": payload,
    }


def test_mcp_keeps_computer_operation_until_real_tool_completion() -> None:
    """因为远程工具可能长时间等待，需要验证整个调用期间保持电脑动作而非正面手机或完成。"""
    # 1、启动 MCP 后模型文本不能解除工具工作，只有匹配的工具结束事件才能解除。
    actors = {}
    for event in [
        trace(1, "run.started"),
        trace(2, "tool.started", call_id="mcp1", name="search", tool_kind="mcp"),
        trace(3, "assistant.message", text="我干完了"),
    ]:
        reduce_event(actors, event)
    view = actor_view(actors["assistant"])
    assert view["activity"] == "executing"
    assert view["animation"]["gesture"] == "type"
    cue = visual_cue(trace(2, "tool.started", call_id="mcp1", name="search", tool_kind="mcp"))
    assert cue is None  # 特殊 MCP 行为由持久队列消费，不能在短线索队列中重复播放。
    reduce_event(actors, trace(4, "tool.completed", call_id="mcp1"))
    assert actor_view(actors["assistant"])["activity"] != "reporting"


def test_child_and_model_messages_cannot_finish_parent_run() -> None:
    """因为子任务结束后主 Agent 还需汇总，需要保证 task/model 结束都不能触发整轮汇报。"""
    # 1、覆盖主 scope 的任务消息与子 scope 的伪终态，主运行上下文始终保留。
    actors = {}
    for event in [
        trace(1, "run.started"),
        trace(2, "task.completed"),
        trace(3, "model.completed"),
        trace(4, "run.completed", scope="child"),
    ]:
        reduce_event(actors, event)
        view = actor_view(actors["assistant"])
        assert view["active_contexts"] == 1 and view["activity"] != "reporting"
    assert visual_cue(trace(4, "run.completed", scope="child")) is None
    # 2、只有主 Run 正式结束后才报告本轮回复已就绪，不冒充业务验收成功。
    reduce_event(actors, trace(5, "run.completed"))
    assert actor_view(actors["assistant"])["activity"] == "reporting"
    assert "干完" not in interaction_profile({})["completed_bubble"]
    assert interaction_profile(
        {"completed_bubble": "老板，我干完了，你看看。"}
    ) == interaction_profile({})
    assert (
        interaction_profile({"completed_bubble": "自定义提示"})["completed_bubble"] == "自定义提示"
    )
    assert animation_hint("executing", ["search"], 0, 0, ["mcp"])["gesture"] == "type"
