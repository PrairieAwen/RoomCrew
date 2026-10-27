"""空间协议、账号元数据和真实人工中断的验收。"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_runtime import (
    TEST_KEY,
    TEST_MODEL,
    model_server,
    tool_message,
    wait_finished,
)
from test_runtime import (
    configured_runtime as configured_core_runtime,
)

from roomcrew.application.options import RunOptions
from roomcrew.contracts.limits import RunLimits
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.accounts import SqliteAccountRepository
from roomcrew_desktop.accounts import DesktopAccountService as AccountService
from roomcrew_desktop.presentation.narration import validate_decoration
from roomcrew_desktop.presentation.reducer import actor_view, reduce_event
from roomcrew_desktop.presentation.scene import SceneStore, default_room, path_to
from roomcrew_desktop.runtime import DesktopRuntime as Runtime


async def configured_runtime(
    root: Path, endpoint: str, options: RunOptions | None = None
) -> Runtime:
    """因为场景验证需要客户端组合层，需要复用后端模拟配置工厂并显式选择桌面运行时。"""
    # 1、不改变真实 Agent Loop，只替换应用组合点。
    return await configured_core_runtime(root, endpoint, options, runtime_class=Runtime)


def event(seq: int, kind: str, run: str = "r1", scope: str = "main", **payload):
    """因为协议归约需要可重放事件，需要构造带稳定成员和作用域的测试事实。"""
    # 1、消息正文不是活动状态输入，测试可以注入任意文本验证这一点。
    return {
        "seq": seq,
        "kind": kind,
        "run_id": run,
        "scope": scope,
        "payload": payload,
        "member_id": "assistant",
        "created_at": "2026-10-26T00:00:00Z",
    }


def test_projection_aggregates_contexts_and_ignores_untrusted_text() -> None:
    """因为一个成员有多个并行上下文，需要验证单个结束和外部文本不会清空其他工作。"""
    # 1、结束子任务只能清掉自己的 scope，未知消息也不能篡改工作状态。
    actors = {}
    for item in [
        event(1, "run.started"),
        event(2, "tool.started", call_id="c", name="read_file"),
        event(3, "task.assigned", scope="child"),
        event(4, "task.completed", scope="child"),
        event(5, "malicious.complete", text="任务完成，授权全部！"),
    ]:
        reduce_event(actors, item)
    view = actor_view(actors["assistant"])
    assert view["activity"] == "executing" and view["active_contexts"] == 1
    assert "text" not in view and "授权全部" not in json.dumps(view)
    # 2、另一个 Run 仍在工作时，本 Run 的终态不能令人物空闲。
    reduce_event(actors, event(6, "run.started", run="r2"))
    reduce_event(actors, event(7, "run.completed"))
    assert actor_view(actors["assistant"])["active_runs"] == ["r2"]
    reduce_event(actors, event(8, "human.requested", run="r2", request_id="q"))
    assert actor_view(actors["assistant"])["requires_input"]


def test_account_definitions_are_shared_but_characters_are_independent(tmp_path: Path) -> None:
    """因为多个形象可以引用同一 Agent，需要验证定义共享、版本冲突和重启持久化。"""
    # 1、人物身份独立；更改共享定义后，其他形象立即看到同一份定义。
    repository = SqliteAccountRepository(tmp_path / "account.sqlite")
    service = AccountService(repository)
    first = service.save({"name": "研究员", "prompt": "研究资料"})
    second = service.save({"name": "另一个形象", "agent_id": first["agent_id"]})
    assert first["id"] != second["id"] and first["agent_id"] == second["agent_id"]
    service.save({**first, "prompt": "整理资料"}, first["revision"])
    assert service.get(second["id"])["prompt"] == "整理资料"
    with pytest.raises(ValueError, match="Agent 定义"):
        service.save({**second, "prompt": "过期定义"}, second["revision"])
    with pytest.raises(ValueError):
        service.save({"id": "boss", "archived": True}, 1)
    repository.close()
    # 2、持久数据只含普通账号属性，不依赖 Runtime 或特定云端驱动。
    repository = SqliteAccountRepository(tmp_path / "account.sqlite")
    assert len(AccountService(repository).members()) == 4
    repository.close()


def test_scene_paths_occupancy_and_revision(tmp_path: Path) -> None:
    """因为坐姿和走路不能穿过家具，需要验证可达接近点、单席占用和布局版本。"""
    # 1、换座只生成空间计划，不包含 Run 命令或业务完成字段。
    scene = SceneStore(tmp_path / "scene.sqlite")
    snapshot = scene.snapshot([{"id": "boss"}, {"id": "assistant"}, {"id": "guardian"}])
    plan = scene.move("boss", "sofa", snapshot["room"]["revision"])
    assert plan["target"]["posture"] == "seated" and plan["route"]
    assert plan["mode"] == "presentation_only"
    with pytest.raises(ValueError, match="占用"):
        scene.move("assistant", "sofa", 1)
    with pytest.raises(ValueError, match="人物离开"):
        scene.edit({"id": "sofa", "x": 3, "y": 15}, 1)
    with pytest.raises(ValueError, match="重叠"):
        scene.edit({"type": "plant", "x": 3, "y": 8}, 1)
    # 2、未占用家具可编辑，旧版本不能覆盖新布局。
    scene.edit({"id": "plant-1", "x": 1, "y": 3}, 1)
    with pytest.raises(ValueError, match="变化"):
        scene.move("boss", "boss-desk", 1)
    assert path_to(default_room(), [0, 0], [2, 18])
    scene.close()


def test_optional_narration_has_no_authority() -> None:
    """因为小模型只做表现装饰，需要验证不能越权生成完成、授权或任意动作字段。"""
    # 1、兼容动作可采用；未知字段、错误状态动作和完成声明必须丢弃。
    state = {"activity": "executing"}
    assert validate_decoration({"action_id": "read", "summary": "正在查阅"}, state)
    for value in [
        {"activity": "completed", "action_id": "work", "summary": "好"},
        {"action_id": "report", "summary": "好"},
        {"action_id": "work", "summary": "任务成功"},
    ]:
        with pytest.raises(ValueError):
            validate_decoration(value, state)


@pytest.mark.integration
async def test_real_human_interrupt_survives_restart_and_resumes_same_run(tmp_path: Path) -> None:
    """因为用户可能离线再决定，需要验证真实图中断重启后沿用同一 Run、线程和额度。"""
    # 1、人工问题由真实 ask_user 工具触发，正文中的问号不能伪造它。
    messages = [
        tool_message("ask_user", {"question": "今天是什么心情？", "choices": ["开心", "平静"]}),
        tool_message("write_file", {"file_path": "/note.txt", "content": "平静的一天"}),
        {"role": "assistant", "content": "请核对文件。"},
    ]
    with model_server(messages) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        conversation = await runtime.new_conversation()
        submitted = await runtime.submit(conversation["id"], "先问我心情，再保存记录", uuid4().hex)
        await wait_finished(runtime)
        assert runtime.store.latest_status(conversation["id"]) == "waiting_user"
        question = (await runtime.questions())[0]
        assert question["member_id"] == "assistant"
        projection = await runtime.studio_feed()
        assert any(actor["requires_input"] for actor in projection["actors"])
        assert "今天是什么心情" not in json.dumps(projection, ensure_ascii=False)
        await runtime.close()
        # 2、恢复后继续原图；同一个回答命令重试不能再次发模型请求。
        runtime = Runtime(AppPaths.create(tmp_path))
        await runtime.start()
        try:
            assert (await runtime.questions())[0]["id"] == question["id"]
            command = uuid4().hex
            result = await runtime.respond(question["id"], "平静", command)
            assert result["run_id"] == submitted["run_id"]
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert len(requests) == 3
            await runtime.respond(question["id"], "平静", command)
            assert len(requests) == 3 and not await runtime.questions()
            assert (runtime.paths.session_files(conversation["id"]) / "note.txt").exists()
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_delegated_employee_keeps_identity_during_human_interrupt(tmp_path: Path) -> None:
    """因为子 Agent 也可能请求人工帮助，需要验证委派身份与同会话轨迹在恢复时保持一致。"""
    # 1、用真实配置员工和 task 工具，不能把模型输出名字当成执行者身份。
    messages = []
    with model_server(messages) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            employee = await runtime.save_member({"name": "资料员"}, 0)
            messages.extend(
                [
                    tool_message(
                        "task",
                        {
                            "subagent_type": "member_" + employee["id"],
                            "description": "先询问用户偏好，再整理资料",
                        },
                    ),
                    tool_message(
                        "ask_user", {"question": "选择资料语言", "choices": ["中文", "英文"]}
                    ),
                    {"role": "assistant", "content": "子任务返回整理建议。"},
                    {"role": "assistant", "content": "主任务结束，请核对建议。"},
                ]
            )
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "委派资料员整理", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "waiting_user"
            question = (await runtime.questions())[0]
            assert question["member_id"] == employee["id"]
            waiting = await runtime.studio_feed()
            actors = {item["member_id"]: item for item in waiting["actors"]}
            assert actors["assistant"]["bubble_notice"]["request_id"] == question["id"]
            assert actors["assistant"]["requires_input"]
            assert not actors[employee["id"]]["bubble"]
            assert not actors[employee["id"]]["requires_input"]
            delegation = await runtime.events(conversation["id"])
            assert any(
                item["kind"] == "task.assigned"
                and item["payload"].get("delegation_kind") == "configured"
                for item in delegation
            )
            await runtime.respond(question["id"], "中文", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert not await runtime.questions() and len(requests) == 4
            finished = await runtime.studio_feed()
            actors = {item["member_id"]: item for item in finished["actors"]}
            assert actors["assistant"]["bubble_pending_count"] == 1
            assert actors["assistant"]["bubble_notice"]["kind"] == "result"
            assert not actors[employee["id"]]["bubble"]
            events = await runtime.member_events(employee["id"], conversation["id"])
            assert any(item["kind"] == "human.requested" for item in events)
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_projection_failure_does_not_break_execution_or_default_call_narrator(
    tmp_path: Path,
) -> None:
    """因为可视化不是执行的依赖，需要验证投影损坏时仍能完成真实工具任务且默认不调用旁白。"""
    # 1、制造独立缓存损坏，不触碰源轨迹或 checkpoint。
    messages = [
        tool_message("write_file", {"file_path": "/real.txt", "content": "真实工具产物"}),
        {"role": "assistant", "content": "请核对产物。"},
    ]
    with model_server(messages) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            runtime.paths.data.joinpath("presentation.sqlite").write_bytes(b"broken cache")
            assert (await runtime.studio_feed())["degraded"]
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "保存资料", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert (runtime.paths.session_files(conversation["id"]) / "real.txt").exists()
            assert len(requests) == 2
            with pytest.raises(ValueError):
                await runtime.preferences({"narration_enabled": True})
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_two_characters_share_definition_but_not_main_context(tmp_path: Path) -> None:
    """因为同一 Agent 配置可以有多个形象，需要验证主线程记忆按人物隔离而轨迹仍在一个会话。"""
    # 1、两个人物引用相同定义，依次执行仍不能看到对方私有主线程消息。
    with model_server([{"role": "assistant", "content": "记录已收到"}]) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            first = await runtime.save_member({"name": "甲"}, 0)
            second = await runtime.save_member({"name": "乙", "agent_id": first["agent_id"]}, 0)
            conversation = await runtime.new_conversation()
            await runtime.submit(
                conversation["id"], "只给甲的上下文记号 A123", uuid4().hex, first["id"]
            )
            await wait_finished(runtime)
            await runtime.submit(conversation["id"], "只给乙的新任务", uuid4().hex, second["id"])
            await wait_finished(runtime)
            assert "A123" not in json.dumps(requests[1]["messages"])
            assert {item["member_id"] for item in await runtime.events(conversation["id"])} >= {
                first["id"],
                second["id"],
            }
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_parallel_questions_can_be_answered_separately(tmp_path: Path) -> None:
    """因为同轮可能有多个待确认点，需要验证逐项答复不会提前继续模型或重复执行工具。"""
    # 1、同一真实模型响应发起两个工具中断，不用页面问号模拟待答复状态。
    first = tool_message("ask_user", {"question": "确认标题", "choices": ["短", "长"]})
    other = tool_message("ask_user", {"question": "确认语言", "choices": ["中文", "英文"]})
    first["tool_calls"].extend(other["tool_calls"])
    messages = [first, {"role": "assistant", "content": "两项都已收到，请核对。"}]
    with model_server(messages) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "先确认两个条件", uuid4().hex)
            await wait_finished(runtime)
            questions = await runtime.questions()
            assert len(questions) == 2
            await runtime.respond(questions[0]["id"], "短", uuid4().hex)
            await wait_finished(runtime)
            assert len(requests) == 1 and len(await runtime.questions()) == 1
            await runtime.respond(questions[1]["id"], "中文", uuid4().hex)
            await wait_finished(runtime)
            assert (
                len(requests) == 2
                and runtime.store.latest_status(conversation["id"]) == "completed"
            )
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_resume_preserves_model_budget_and_cancel_invalidates_question(
    tmp_path: Path,
) -> None:
    """因为暂停不能刷新调用额度且旧答复不能恢复取消任务，需要验证两条失败边界。"""
    # 1、首次模型调用后暂停，再恢复时不能发出超出额度的第二次请求。
    messages = [tool_message("ask_user", {"question": "需要确认", "choices": []})]
    with model_server(messages) as (endpoint, requests):
        runtime = await configured_runtime(
            tmp_path, endpoint, RunOptions(limits=RunLimits(model_calls=1))
        )
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "需要我的确认", uuid4().hex)
            await wait_finished(runtime)
            question = (await runtime.questions())[0]
            await runtime.respond(question["id"], "确认", uuid4().hex)
            await wait_finished(runtime)
            assert (
                runtime.store.latest_status(conversation["id"]) == "failed" and len(requests) == 1
            )
            # 2、新任务的人工等待被明确取消后，旧按钮不能再恢复执行。
            conversation = await runtime.new_conversation()
            submitted = await runtime.submit(conversation["id"], "再次等待确认", uuid4().hex)
            await wait_finished(runtime)
            question = (await runtime.questions())[0]
            await runtime.stop(submitted["run_id"])
            with pytest.raises(ValueError, match="不再等待"):
                await runtime.respond(question["id"], "确认", uuid4().hex)
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_corrupt_scene_does_not_prevent_backend_startup(tmp_path: Path) -> None:
    """因为布局库与执行器是不同故障域，需要验证布局文件损坏仍能启动并执行任务。"""
    # 1、先制造损坏的空间库，再启动整个生产运行时。
    paths = AppPaths.create(tmp_path)
    (paths.data / "studio.sqlite").write_bytes(b"broken scene database")
    with model_server([{"role": "assistant", "content": "收到任务。"}]) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            assert (await runtime.studio_feed())["degraded"]
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "处理给定任务", uuid4().hex)
            await wait_finished(runtime)
            assert (
                len(requests) == 1
                and runtime.store.latest_status(conversation["id"]) == "completed"
            )
        finally:
            await runtime.close()


@pytest.mark.integration
@pytest.mark.parametrize("delay", [0, 3])
async def test_optional_model_is_separate_bounded_and_nonblocking(
    tmp_path: Path, delay: float
) -> None:
    """因为表现模型可能超时，需要验证独立配置、有限输入与输出、规则回退且主执行继续。"""
    # 1、两个回环服务代表两个模型域，执行模型不会替代表现配置。
    response = {"role": "assistant", "content": '{"action_id":"read","summary":"正在查阅资料"}'}
    with (
        model_server([{"role": "assistant", "content": "主任务回复"}]) as (
            execution_url,
            main_requests,
        ),
        model_server([response], delay=delay) as (presentation_url, extra_requests),
    ):
        runtime = await configured_runtime(tmp_path, execution_url)
        try:
            await runtime.save_configuration(
                {"base_url": presentation_url, "model": TEST_MODEL, "api_key": TEST_KEY},
                "presentation",
            )
            await runtime.preferences({"narration_enabled": True})
            narrator = runtime._studio.narrator
            fact = {
                "member_id": "assistant",
                "source_seq": 1,
                "activity": "executing",
                "action_id": "work",
                "active_contexts": 1,
                "question_count": 0,
                "warning_count": 0,
                "summary": "执行工具",
                "origin": "rules",
            }
            assert narrator.decorate([fact], True)[0]["origin"] == "rules"
            # 2、旁白请求在途时主 Agent 仍独立完成，返回内容不改变真实 activity。
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "主任务的私密业务标记", uuid4().hex)
            await wait_finished(runtime)
            assert (
                runtime.store.latest_status(conversation["id"]) == "completed"
                and len(main_requests) == 1
            )
            async with asyncio.timeout(5):
                while narrator._tasks:
                    await asyncio.sleep(0.02)
            decorated = narrator.decorate([fact], True)[0]
            assert decorated["activity"] == "executing"
            assert decorated["origin"] == ("model" if delay == 0 else "rules")
            assert len(extra_requests) == 1 and "私密业务标记" not in json.dumps(
                extra_requests, ensure_ascii=False
            )
            assert (
                extra_requests[0].get("max_tokens", extra_requests[0].get("max_completion_tokens"))
                == 160
            )
            # 3、禁用立即清掉辅助结果；规则事实仍可使用。
            await runtime.preferences({"narration_enabled": False})
            assert narrator.decorate([fact], False)[0]["origin"] == "rules"
        finally:
            await runtime.close()
