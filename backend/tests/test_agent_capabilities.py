"""执行配置、官方轨迹、只读 Skills、真实 MCP 和隔离脚本验收。"""

import hashlib
import json
import socket
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from mcp_fixture import mcp_server
from test_runtime import (
    TEST_KEY,
    TEST_MODEL,
    configured_runtime,
    model_server,
    tool_message,
    wait_finished,
)

from roomcrew.accounts.configuration import agent_configuration
from roomcrew.accounts.service import AccountService
from roomcrew.mcp.provider import configured_mcp_tools
from roomcrew.storage.accounts import SqliteAccountRepository
from roomcrew.tools.python import run_script


def test_agent_capabilities_live_in_definition_table(tmp_path: Path) -> None:
    """因为同一执行定义可被多个形象复用，需要验证能力持久化在 Agent 表并按版本共享。"""
    # 1、使用通用服务，不导入桌面；技能正文和 MCP 配置不落进人物行。
    repository = SqliteAccountRepository(tmp_path / "accounts.sqlite")
    service = AccountService(repository)
    values = {
        "name": "研究员",
        "prompt": "按工具证据回答",
        "skills": [{"name": "notes", "description": "整理笔记", "instructions": "按来源组织资料"}],
        "mcp_servers": [{"name": "math", "url": "http://127.0.0.1:1/mcp"}],
        "python_enabled": False,
    }
    first = service.save(values)
    second = service.save({"name": "另一个形象", "agent_id": first["agent_id"]})
    assert service.get(second["id"])["skills"] == first["skills"]
    raw = repository._db.execute("SELECT body FROM members WHERE id=?", (first["id"],)).fetchone()[
        0
    ]
    assert "instructions" not in raw and "mcp_servers" not in raw
    assert (
        "skills"
        in repository._db.execute(
            "SELECT body FROM agent_definitions WHERE id=?", (first["agent_id"],)
        ).fetchone()[0]
    )
    binding = service.binding(first["id"])
    assert binding["main"]["configuration"]["python_enabled"] is False
    repository.close()


@pytest.mark.parametrize(
    "invalid",
    [
        {"python_enabled": "yes"},
        {"skills": [{"name": "../escape", "description": "x", "instructions": "x"}]},
        {
            "skills": [
                {
                    "name": "valid",
                    "description": "x",
                    "instructions": "x",
                    "files": {"../escape.py": "print(1)"},
                }
            ]
        },
        {"mcp_servers": [{"name": "x", "url": "https://user:secret@example.com/mcp"}]},
        {"mcp_servers": [{"name": "x", "url": "https://example.com/mcp?key=secret"}]},
        {
            "mcp_servers": [
                {
                    "name": "x",
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "secret"},
                }
            ]
        },
    ],
)
def test_capability_configuration_rejects_paths_and_secrets(invalid: dict) -> None:
    """因为能力配置不能绕过路径或凭据边界，需要拒绝越界技能与内嵌认证参数。"""
    # 1、验证在任何网络或写文件之前失败。
    with pytest.raises(ValueError):
        agent_configuration(invalid)


async def test_configured_skills_load_progressively_and_stay_read_only(tmp_path: Path) -> None:
    """因为技能配置需要实际作用于 SDK，需要验证元信息先进入上下文、正文按需读取且不可改写。"""
    # 1、依据配置内容计算正式虚拟路径，正文标记只有调用 read_file 后才应进入模型上下文。
    skills = agent_configuration(
        {
            "skills": [
                {
                    "name": "note-style",
                    "description": "验收笔记样式",
                    "instructions": "CONFIGURED_SKILL_BODY_MARKER",
                }
            ]
        }
    )["skills"]
    digest = hashlib.sha256(
        json.dumps(skills, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    path = "/skills/configured/" + digest + "/note-style/SKILL.md"
    responses = [
        tool_message("read_file", {"file_path": path}),
        tool_message("write_file", {"file_path": path, "content": "tamper"}),
        {"role": "assistant", "content": "已读取技能；修改被拒绝"},
    ]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            await runtime.save_member({"id": "assistant", "skills": skills}, 1)
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "用配置技能整理笔记", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            first = json.dumps(requests[0]["messages"], ensure_ascii=False)
            second = json.dumps(requests[1]["messages"], ensure_ascii=False)
            assert "验收笔记样式" in first and "CONFIGURED_SKILL_BODY_MARKER" not in first
            assert "CONFIGURED_SKILL_BODY_MARKER" in second
            content = (
                runtime.paths.data / "skill-bundles" / digest / "note-style/SKILL.md"
            ).read_text("utf-8")
            assert "tamper" not in content
            events = await runtime.events(conversation["id"])
            assert any(item["payload"].get("tool_kind") == "skill" for item in events)
        finally:
            await runtime.close()


async def test_real_mcp_tool_runs_inside_deepagents_and_native_trace(tmp_path: Path) -> None:
    """因为 MCP 需要实际接入，需要验证真实协议、生产 Loop 和官方事件。"""
    # 1、模型协议使用可控响应，MCP 的发现、调用与结果全部走实际实现。
    responses = [
        tool_message("math_add_numbers", {"left": 17, "right": 25}),
        {"role": "assistant", "content": "计算结果是 42"},
    ]
    with mcp_server() as (url, calls), model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            await runtime.save_member(
                {"id": "assistant", "mcp_servers": [{"name": "math", "url": url}]}, 1
            )
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "通过配置 MCP 计算给定数值", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert calls == [{"left": 17, "right": 25}]
            assert "42" in json.dumps(requests[-1]["messages"])
            events = await runtime.events(conversation["id"])
            assert any(item["payload"].get("tool_kind") == "mcp" for item in events)
            native = []
            cursor = 0
            while batch := await runtime.native_events(conversation["id"], cursor):
                native.extend(batch)
                cursor = batch[-1]["seq"]
            tools = [
                item["native"]
                for item in native
                if item["native"]["event"] in {"on_tool_start", "on_tool_end"}
            ]
            assert tools[0]["run_id"] == tools[1]["run_id"]
            assert tools[0]["parent_ids"]
            assert tools[1]["data"]["output"]["tool_call_id"] != tools[1]["run_id"]
            encoded = json.dumps(native, ensure_ascii=False)
            assert TEST_KEY not in encoded and TEST_MODEL not in encoded and endpoint not in encoded
        finally:
            await runtime.close()


async def test_missing_mcp_server_fails_instead_of_fake_success() -> None:
    """因为连接失败不能生成假工具，需要验证不可用 MCP 服务会返回稳定失败。"""
    # 1、只连接本机关闭的测试端口，不发外部请求。
    with pytest.raises(Exception, match="MCP_CONNECTION"):
        await configured_mcp_tools(
            [{"name": "unavailable", "url": "http://127.0.0.1:1/mcp", "enabled": True}]
        )


async def test_catalog_routes_to_worker_with_its_own_mcp_configuration(tmp_path: Path) -> None:
    """因为主子 Agent 的能力配置不能混用，需要发现员工并通过真实 task 调用员工自己的 MCP。"""
    # 1、主 Agent 没有该 MCP，只有被委派员工注册数学工具。
    responses = [
        tool_message("list_agents", {}),
        tool_message(
            "task",
            {"description": "用你的数学 MCP 计算 18 加 24", "subagent_type": "member_math_worker"},
        ),
        tool_message("math_add_numbers", {"left": 18, "right": 24}),
        {"role": "assistant", "content": "员工计算结果为 42"},
        {"role": "assistant", "content": "员工已返回结果 42"},
    ]
    with mcp_server() as (url, calls), model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            await runtime.save_member(
                {
                    "id": "math_worker",
                    "name": "数学员工",
                    "description": "使用数学 MCP 进行计算",
                    "mcp_servers": [{"name": "math", "url": url}],
                    "python_enabled": False,
                },
                0,
            )
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "找数学员工计算", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert calls == [{"left": 18, "right": 24}]
            assert "math_add_numbers" not in {
                item["function"]["name"] for item in requests[0]["tools"]
            }
            assert "math_add_numbers" in {item["function"]["name"] for item in requests[2]["tools"]}
            assert "execute_python" not in {
                item["function"]["name"] for item in requests[2]["tools"]
            }
            events = await runtime.events(conversation["id"])
            assert any(
                item["member_id"] == "math_worker"
                and item["payload"].get("name") == "math_add_numbers"
                for item in events
            )
        finally:
            await runtime.close()


async def test_typed_human_choice_rejects_invalid_answer_and_resumes(tmp_path: Path) -> None:
    """因为人工介入需要明确的选择约束，需要验证限定选项、持久等待和同一 Run 恢复。"""
    # 1、问题通过真实 interrupt 保存，模型普通文本不充当审批或答复。
    responses = [
        tool_message(
            "ask_user",
            {
                "question": "这是合成验收，请选择一个测试方案",
                "choices": ["方案甲", "方案乙"],
                "interaction_type": "choice",
                "allow_other": False,
            },
        ),
        {"role": "assistant", "content": "已收到方案甲，验收完成"},
    ]
    with model_server(responses) as (endpoint, _):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            run = await runtime.submit(conversation["id"], "进行人工选择验收", uuid4().hex)
            await wait_finished(runtime)
            questions = await runtime.questions()
            assert len(questions) == 1 and questions[0]["interaction_type"] == "choice"
            assert questions[0]["allow_other"] is False
            with pytest.raises(ValueError, match="选项"):
                await runtime.respond(questions[0]["id"], "未列出的答案", uuid4().hex)
            assert runtime.store.latest_status(conversation["id"]) == "waiting_user"
            resumed = await runtime.respond(questions[0]["id"], "方案甲", uuid4().hex)
            assert resumed["run_id"] == run["run_id"]
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
        finally:
            await runtime.close()


@pytest.mark.integration
async def test_agent_writes_and_executes_python_without_host_python(tmp_path: Path) -> None:
    """因为代码必须由框架真实调用执行，需要让模拟模型提交脚本，再核对隔离执行生成的文件。"""
    # 1、脚本没有专用业务分支；只有执行之后才能产生计算产物。
    script = (
        "import json\nfrom pathlib import Path\n"
        "result = sum(n*n for n in range(1, 38))\n"
        "Path('answer.json').write_text(json.dumps({'sum_squares': result}), encoding='utf-8')\n"
        "print(result)\n"
    )
    responses = [
        tool_message("write_file", {"file_path": "/calculate.py", "content": script}),
        tool_message("execute_python", {"script_path": "/calculate.py", "timeout_seconds": 15}),
        tool_message("read_file", {"file_path": "/answer.json"}),
        {"role": "assistant", "content": "已执行并读取结果"},
    ]
    with model_server(responses) as (endpoint, requests):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "用 Python 计算并交付结果", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            result = json.loads(
                (runtime.paths.session_files(conversation["id"]) / "answer.json").read_text("utf-8")
            )
            assert result["sum_squares"] == sum(n * n for n in range(1, 38))
            output = json.dumps(requests[-1]["messages"])
            assert "windows-appcontainer" in output
        finally:
            await runtime.close()


def test_python_isolation_blocks_outside_reads_and_cleans_timeouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """因为脚本不能读取宿主秘密，需要验证隔离身份、文件和环境边界以及超时。"""
    # 1、只创建合成秘密，绝不读取应用已经保存的真实 Key。
    root = tmp_path / "files"
    root.mkdir()
    outside = tmp_path / "synthetic-private.txt"
    outside.write_text("SYNTHETIC_SECRET_NEVER_VISIBLE", encoding="utf-8")
    monkeypatch.setenv("ROOMCREW_TEST_SECRET", "SYNTHETIC_ENV_NEVER_VISIBLE")
    template = (Path(__file__).parent / "fixtures/isolation_probe.py").read_text("utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        script = (
            "OUTSIDE_FILE = "
            + repr(str(outside))
            + "\nLOCAL_PORT = "
            + str(listener.getsockname()[1])
            + "\n"
            + template
        )
        (root / "proof.py").write_text(script, encoding="utf-8")
        result = run_script(root, tmp_path / "cache", "/proof.py", 15, threading.Event())
    assert result["exit_code"] == 0, result
    proof = json.loads((root / "proof.json").read_text("utf-8"))
    assert proof == {
        "container": 1,
        "outside_read": False,
        "env": None,
        "network": False,
        "child_process": False,
    }
    # 2、实际无限循环在期限后被终止，没有宿主回退或后台继续运行。
    (root / "slow.py").write_text("while True:\n pass\n", encoding="utf-8")
    result = run_script(root, tmp_path / "cache", "/slow.py", 1, threading.Event())
    assert result["reason"] == "timeout" and result["exit_code"] != 0
