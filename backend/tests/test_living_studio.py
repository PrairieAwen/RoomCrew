"""用户身份分离、随机活动池与真实委派关系的回归。"""

import json
from pathlib import Path

import pytest
from test_studio import event

from roomcrew.accounts.service import AccountService
from roomcrew.agent_loop.event_adapter import EventAdapter
from roomcrew.contracts.agents import ActorRef
from roomcrew.presentation.collaboration import meeting_groups
from roomcrew.presentation.reducer import actor_view, reduce_event
from roomcrew.presentation.scene import anchors, default_room, navigation_map, path_to
from roomcrew.storage.accounts import SqliteAccountRepository


def identity_redactor(value):
    """因为此测试不携带凭据，需要保留协议字段以单独验证身份与作用域转换。"""
    # 1、生产仍使用真实脱敏器，测试只提供最小依赖。
    return value


def test_user_is_not_a_scene_member_and_legacy_record_is_preserved(tmp_path: Path) -> None:
    """因为用户就是老板本人，需要验证新账号仅有助手和监管员且旧用户记录不再成为人物。"""
    # 1、隐藏旧显示身份而保留历史数据，避免升级删除用户资料。
    repo = SqliteAccountRepository(tmp_path / "account.sqlite")
    service = AccountService(repo)
    assert {item["role"] for item in service.members()} == {"assistant", "guardian"}
    repo.save(
        {
            "id": "boss",
            "name": "旧老板",
            "role": "user",
            "agent_id": None,
            "enabled": True,
            "archived": False,
        },
        0,
    )
    assert len(service.members()) == 2 and len(repo.members()) == 3
    with pytest.raises(ValueError):
        service.get("boss")
    assert service.binding()["main"]["actor"]["member_id"] == "assistant"
    repo.close()


def test_activity_pool_is_bounded_persistent_and_not_an_agent_prompt(tmp_path: Path) -> None:
    """因为生活偏好只属于人物，需要验证最多四项、重开持久化与执行上下文隔离。"""
    # 1、轮换池和单动作兼容字段可共存；活动不会成为 Agent 指令。
    path = tmp_path / "account.sqlite"
    repo = SqliteAccountRepository(path)
    service = AccountService(repo)
    member = service.save({"name": "同事", "leisure_actions": ["phone", "game", "wander", "chat"]})
    assert "leisure" not in json.dumps(service.binding(member["id"]))
    for activities in (
        ["phone"] * 2,
        ["phone", "game", "wander", "chat", "water"],
        ["shell"],
        "phone",
        [True],
    ):
        with pytest.raises(ValueError):
            service.save({"name": "无效", "leisure_actions": activities})
    with pytest.raises(ValueError):
        service.save({"id": "guardian", "leisure_actions": ["chat"]}, 1)
    repo.close()
    repo = SqliteAccountRepository(path)
    assert AccountService(repo).get(member["id"])["leisure_actions"] == [
        "phone",
        "game",
        "wander",
        "chat",
    ]
    repo.close()


def test_event_adapter_distinguishes_configured_worker_and_external_scope() -> None:
    """因为通用子任务不能冒充已招募人物，需要从真实工具参数和调用链区分会议与外援。"""
    # 1、同样的 task 工具，只有注册员工名称映射到可见人物。
    worker = ActorRef("employee", "agent_employee", "资料员")
    adapter = EventAdapter(identity_redactor, workers={"member_employee": worker})
    configured = adapter.project(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "child-c",
            "parent_ids": [],
            "data": {"input": {"subagent_type": "member_employee"}},
        }
    )
    assert configured[0].member_id == "employee"
    assert configured[0].payload["delegation_kind"] == "configured"
    external = adapter.project(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "child-e",
            "parent_ids": [],
            "data": {"input": {"subagent_type": "general-purpose"}},
        }
    )
    assert external[0].payload["delegation_kind"] == "external"
    child = adapter.project(
        {
            "event": "on_tool_start",
            "name": "read_file",
            "run_id": "tool-e",
            "parent_ids": ["child-e"],
            "data": {"input": {"file_path": "/note.txt"}},
        }
    )
    assert child[0].member_id == "assistant"
    assert child[0].payload["presentation_external"] is True and "外援" in child[0].actor


def test_groups_merge_by_run_and_external_details_do_not_animate_people() -> None:
    """因为一项任务可能派给多个同事并另请外援，需要验证同 Run 合并、作用域清理与人工优先。"""
    # 1、两项真实配置委派进入同一组，通用外援只让发起人具有电话状态。
    states = {}
    reduce_event(states, event(1, "run.started"))
    for seq, member in ((2, "b"), (3, "c")):
        item = event(
            seq,
            "task.assigned",
            scope="child-" + member,
            from_member_id="assistant",
            target_member_id=member,
            delegation_kind="configured",
        )
        item["member_id"] = member
        reduce_event(states, item)
    reduce_event(
        states,
        event(
            4,
            "task.assigned",
            scope="external",
            from_member_id="assistant",
            target_member_id=None,
            delegation_kind="external",
        ),
    )
    views = [actor_view(state) for state in states.values()]
    assert meeting_groups(views, states)[0]["members"] == ["assistant", "b", "c"]
    assert actor_view(states["assistant"])["external_calls"] == 1
    before = actor_view(states["assistant"])["active_contexts"]
    reduce_event(
        states,
        event(
            5,
            "tool.started",
            scope="external",
            presentation_external=True,
            name="write_file",
            call_id="f",
        ),
    )
    assert actor_view(states["assistant"])["active_contexts"] == before
    # 2、真实提问仍进入用户待办；终态释放全部关系，不展示过期会议或外援。
    question = event(6, "human.requested", scope="child-b", request_id="q")
    question["member_id"] = "b"
    reduce_event(states, question)
    assert "b" not in meeting_groups([actor_view(s) for s in states.values()], states)[0]["members"]
    reduce_event(states, event(7, "run.completed"))
    assert meeting_groups([actor_view(s) for s in states.values()], states) == []
    assert actor_view(states["assistant"])["external_calls"] == 0


def test_default_room_anchors_and_visual_navigation_are_reachable() -> None:
    """因为环境扩充不能把人物困住或留下越界座点，需要验证全部默认锚点及导航占地一致。"""
    # 1、包括新增休闲区的每个接近点，都必须位于固定地图并可从公共走道到达。
    room = default_room()
    graph = navigation_map(room)
    blocked = {tuple(point) for point in graph["blocked"]}
    for anchor in anchors(room):
        point = anchor["approach"]
        assert 0 <= point[0] < room["width"] and 0 <= point[1] < room["height"]
        assert tuple(point) not in blocked and path_to(room, [0, 0], point)
