"""验证独立模块确实接入执行链，远程响应替身仅存在于测试中。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage
from test_runtime import (
    TEST_KEY,
    TEST_MODEL,
    configured_runtime,
    model_server,
    tool_message,
    wait_finished,
)

from roomcrew.application.options import RunOptions
from roomcrew.config.schema import ModelProfile
from roomcrew.context_compression.deepagents_adapter import build_compression
from roomcrew.context_compression.policy import CompressionPolicy
from roomcrew.contracts.limits import RunLimits
from roomcrew.middleware.limits import ModelCallBudget
from roomcrew.middleware.stack import build_middleware
from roomcrew.models.factory import create_model
from roomcrew.skills.registry import SkillPolicy
from roomcrew.tools.registry import file_backend


@pytest.mark.integration
async def test_parent_worker_share_budget_before_real_requests(tmp_path: Path) -> None:
    """因为主子 Agent 必须共同遵守 Run 额度，需要证明超额调用在真实 HTTP 发出前被阻止。"""
    # 1、主 Agent 一次委派、子 Agent 一次写文件，第三次模型调用必须被本机额度阻止。
    responses = [
        tool_message("task", {"description": "保存给定资料", "subagent_type": "general-purpose"}),
        tool_message("write_file", {"file_path": "/limited.txt", "content": "真实工具内容"}),
        {"role": "assistant", "content": "这条响应不应被请求"},
    ]
    with model_server(responses) as (endpoint, requests):
        options = RunOptions(limits=RunLimits(model_calls=2))
        runtime = await configured_runtime(tmp_path, endpoint, options)
        try:
            worker = await runtime.save_member({"name": "额度验收员"}, 0)
            responses[0] = tool_message(
                "task",
                {
                    "description": "保存给定资料",
                    "subagent_type": "member_" + worker["id"],
                },
            )
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "委派员工保存资料", uuid4().hex)
            await wait_finished(runtime)
            events = await runtime.events(conversation["id"])
            assert events[-1]["payload"]["code"] == "RUN_LIMIT"
            assert len(requests) == 2
            assert (runtime.paths.session_files(conversation["id"]) / "limited.txt").exists()
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_skills_are_disclosed_progressively(tmp_path: Path) -> None:
    """因为 Skills 模块不能只是目录占位，需要验证元信息先注入、正文经真实工具按需读取。"""
    # 1、显式配置技能来源；技能正文标记不能出现在第一个模型请求中。
    responses = [
        tool_message("read_file", {"file_path": "/skills/note-style/SKILL.md"}),
        {"role": "assistant", "content": "已读取相关技能"},
    ]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(
            tmp_path, endpoint, RunOptions(skills=SkillPolicy(("/skills/",)))
        )
        try:
            conversation = await runtime.new_conversation()
            skill = runtime.paths.session_files(conversation["id"]) / "skills/note-style/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: note-style\ndescription: 规范笔记格式\n"
                "---\nONLY_IN_SKILL_BODY_MARKER\n",
                "utf-8",
            )
            await runtime.submit(conversation["id"], "按笔记技能处理资料", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            first = json.dumps(requests[0]["messages"], ensure_ascii=False)
            second = json.dumps(requests[1]["messages"], ensure_ascii=False)
            assert "note-style" in first and "规范笔记格式" in first
            assert "ONLY_IN_SKILL_BODY_MARKER" not in first
            assert "ONLY_IN_SKILL_BODY_MARKER" in second
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_explicit_missing_skill_fails_before_model(tmp_path: Path) -> None:
    """因为显式技能来源不能被悄悄忽略，需要在模型执行前明确报告缺失。"""
    # 1、不创建技能目录，检查生产组装入口如何处理无效来源。
    with model_server([{"role": "assistant", "content": "不应调用"}]) as (endpoint, requests):
        runtime = await configured_runtime(
            tmp_path, endpoint, RunOptions(skills=SkillPolicy(("/skills/missing/",)))
        )
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "使用指定技能", uuid4().hex)
            await wait_finished(runtime)
            events = await runtime.events(conversation["id"])
            assert events[-1]["payload"]["code"] == "SKILL_SOURCE_INVALID"
            assert not requests
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_compression_preserves_raw_history_and_uses_same_budget(tmp_path: Path) -> None:
    """因为压缩不能删掉产品原始轨迹，需要验证 SDK 摘要视图、历史外置和共享调用计数。"""
    # 1、构造超过窗口的旧历史，摘要和后续模型响应均通过真实 SDK 访问本机协议服务。
    responses = [
        {"role": "assistant", "content": "COMPRESSED_TEST_CONTEXT 保留目标与产物引用"},
        {"role": "assistant", "content": "继续执行"},
    ]
    with model_server(responses) as (endpoint, requests):
        profile = ModelProfile("ref", "test", endpoint, TEST_MODEL, TEST_KEY, context_window=4096)
        budget = ModelCallBudget(4)
        model = create_model(profile, budget)
        backend = file_backend(tmp_path)
        policy = CompressionPolicy(trim_tokens_to_summarize=1000)
        middleware = build_compression(model, backend, policy)
        messages = []
        for index in range(20):
            messages.extend([HumanMessage(f"old-{index}-" + "a" * 600), AIMessage("b" * 600)])
        messages.append(HumanMessage("recent-goal"))
        original = [message.content for message in messages]
        observed = []

        async def next_model(request: ModelRequest) -> ModelResponse:
            """因为压缩后的有效请求需要继续真实模型调用，需要把修改后的消息交给同一受控模型。"""
            # 1、保留可观察消息用于断言，真实回复仍由 SDK 产生。
            observed.extend(request.messages)
            return ModelResponse(result=[await model.ainvoke(request.messages)])

        try:
            await middleware.awrap_model_call(
                ModelRequest(model=model, messages=messages, state={"messages": messages}),
                next_model,
            )
            assert len(requests) == 2 and budget.calls == 2
            assert "COMPRESSED_TEST_CONTEXT" in json.dumps(requests[-1]["messages"])
            assert "recent-goal" in json.dumps(requests[-1]["messages"])
            assert [message.content for message in messages] == original
            assert sum(len(str(message.content)) for message in observed) < sum(map(len, original))
            assert list((tmp_path / "conversation_history").glob("*.md"))
            # 2、主子 Agent 的中间件实例独立，名称相同用于替换 SDK 默认槽位而不叠第二份。
            left, right = (
                build_middleware(model, backend, policy),
                build_middleware(model, backend, policy),
            )
            assert len([item for item in left if item.name == middleware.name]) == 1
            assert len([item for item in right if item.name == middleware.name]) == 1
            assert left[0] is not right[0]
        finally:
            await model.close()


@pytest.mark.integration
async def test_context_error_type_reaches_sdk_recovery(tmp_path: Path) -> None:
    """因为隐藏厂商错误不能破坏压缩恢复，需要验证先超限、再摘要、再继续的真实调用顺序。"""
    # 1、初始输入低于本地估计窗口，但模拟服务报告超限，检验错误类型适配。
    responses = [
        {"role": "assistant", "content": "unused"},
        {"role": "assistant", "content": "RECOVERED_CONTEXT"},
        {"role": "assistant", "content": "完成"},
    ]
    with model_server(
        responses, statuses=[400, 200, 200], error_code="context_length_exceeded"
    ) as (endpoint, requests):
        model = create_model(
            ModelProfile("ref", "test", endpoint, TEST_MODEL, TEST_KEY, context_window=8192)
        )
        middleware = build_compression(
            model, file_backend(tmp_path), CompressionPolicy(trim_tokens_to_summarize=1000)
        )
        messages = []
        for index in range(8):
            messages.extend([HumanMessage(f"old-{index}-" + "a" * 500), AIMessage("b" * 500)])
        messages.append(HumanMessage("recent-goal"))

        async def next_model(request: ModelRequest) -> ModelResponse:
            """因为恢复后必须继续原模型接口，需要保持真实请求路径而不返回本地固定结果。"""
            # 1、SDK 压缩器决定何时再次调用，测试只提供真实后续调用入口。
            return ModelResponse(result=[await model.ainvoke(request.messages)])

        try:
            await middleware.awrap_model_call(
                ModelRequest(model=model, messages=messages, state={"messages": messages}),
                next_model,
            )
            assert len(requests) == 3
            assert "RECOVERED_CONTEXT" in json.dumps(requests[-1]["messages"])
            assert TEST_KEY not in json.dumps(requests[-1]["messages"])
        finally:
            await model.close()


@pytest.mark.integration
async def test_irreducible_context_failure_has_safe_terminal_code(tmp_path: Path) -> None:
    """因为不可再压缩的输入不能无限重试，需要验证 SDK 退出后由 Loop 返回稳定产品错误。"""
    # 1、对首次输入报告超限，此时没有可压缩旧历史，不能制造本地假摘要绕过错误。
    with model_server(
        [{"role": "assistant", "content": "unused"}],
        status=400,
        error_code="context_length_exceeded",
    ) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "首次任务", uuid4().hex)
            await wait_finished(runtime)
            events = await runtime.events(conversation["id"])
            assert events[-1]["payload"]["code"] == "CONTEXT_LIMIT"
            assert 1 <= len(requests) <= 3
            assert TEST_KEY not in json.dumps(events)
        finally:
            await runtime.close()
