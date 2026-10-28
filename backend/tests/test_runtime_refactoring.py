"""通用执行装配、资源释放与成员查询成本的稳定性约束。"""

from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import BaseTool, StructuredTool

from roomcrew.accounts.service import AccountService
from roomcrew.application.components import AgentLoopFactory
from roomcrew.application.options import RunOptions
from roomcrew.config.schema import ModelProfile
from roomcrew.contracts.agents import ActorRef, AgentSpec
from roomcrew.models.factory import model_session
from roomcrew.platform.paths import AppPaths
from roomcrew.security.capabilities import CapabilityPolicy
from roomcrew.storage.accounts import SqliteAccountRepository
from roomcrew.storage.checkpoints import CheckpointStore
from roomcrew.tools.human import ask_user
from roomcrew.tools.registry import local_tools


def test_static_tools_have_isolated_metadata_per_assembly() -> None:
    """因为同一工具会被主子 Agent 和不同 Run 使用，需要验证单次修改不会污染下一次装配。"""
    # 1、使用正式注册入口，不修改全局模板来模拟隔离成功。
    policy = CapabilityPolicy(code_execution=False)
    first, second = local_tools(policy), local_tools(policy)
    first[1].metadata["test_marker"] = "first-only"
    assert second[1].metadata == {"roomcrew_tool_kind": "human"}
    assert ask_user.metadata is None
    assert first[0] is not second[0]


async def test_model_session_closes_clients_after_failure_and_cancellation() -> None:
    """因为临时调用可能报错或取消，需要验证正式上下文入口总能关闭两个 HTTP 客户端。"""
    # 1、使用不发请求的本机地址，仅验证工厂创建的真实连接池所有权。
    import asyncio

    profile = ModelProfile("ref", "test", "http://127.0.0.1:1/v1", "test", "synthetic-key")
    for error in (ValueError("test-failure"), asyncio.CancelledError()):
        with pytest.raises(type(error)):
            async with model_session(profile) as model:
                clients = model._clients
                assert clients is not None
                raise error
        assert clients[0].is_closed and clients[1].is_closed
        await model.close()


async def test_async_client_closes_when_sync_client_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """因为一个连接池关闭失败不能泄漏另一个，需要验证异步清理仍被执行且二次关闭幂等。"""
    # 1、只替换本测试模型的同步关闭方法，其他实例与全局 HTTP 配置不受影响。
    profile = ModelProfile("ref", "test", "http://127.0.0.1:1/v1", "test", "synthetic-key")
    from roomcrew.models.factory import create_model

    model = create_model(profile)
    clients = model._clients
    assert clients is not None
    original_close = clients[0].close

    def failed_close() -> None:
        """因为需要覆盖关闭失败分支，需要在真正关闭本测试同步池后抛出受控异常。"""
        # 1、不故意留下测试自身的连接泄漏。
        original_close()
        raise RuntimeError("synthetic close failure")

    monkeypatch.setattr(clients[0], "close", failed_close)
    with pytest.raises(RuntimeError, match="synthetic close failure"):
        await model.close()
    assert clients[1].is_closed
    await model.close()


async def test_mcp_discovery_is_shared_with_workers_but_not_between_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """因为相同配置应减少重复发现但不能跨 Run 缓存会话，需要检查真实构图的资源作用域。"""
    # 1、替代的只是远端发现，工具与图仍由正式工厂和 Deep Agents 装配，不启动模型请求。
    discoveries = []

    def mcp_echo() -> str:
        """因为构图需要一个有标准协议的工具，需要提供不产生副作用的测试响应。"""
        # 1、该工具不进入发行包，只检验注册与构图合同。
        return "echo"

    async def discover(
        servers: list[dict[str, Any]], keys: dict[str, str], redact: Any
    ) -> list[BaseTool]:
        """因为需要计数发现生命周期，需要记录可信服务器配置并返回一个标准工具。"""
        # 1、每次发现返回新工具，不能用全局工具缓存让断言巧合通过。
        discoveries.append(servers)
        return [StructuredTool.from_function(mcp_echo, metadata={"roomcrew_tool_kind": "mcp"})]

    monkeypatch.setattr("roomcrew.application.components.configured_mcp_tools", discover)
    configuration = {
        "python_enabled": False,
        "mcp_servers": [{"name": "same", "url": "http://127.0.0.1:1/mcp", "enabled": True}],
    }
    main = AgentSpec(ActorRef(), "main", "主执行者", "", configuration=configuration)
    worker = AgentSpec(
        ActorRef("worker", "worker-config", "同事"),
        "member_worker",
        "工作",
        "",
        configuration=configuration,
    )
    binding = {"main": main.snapshot(), "workers": [worker.snapshot()]}
    paths = AppPaths.create(tmp_path)
    checkpoints = CheckpointStore(paths.data / "runtime.sqlite")
    await checkpoints.start()
    try:
        profile = ModelProfile("ref", "test", "http://127.0.0.1:1/v1", "test", "synthetic-key")
        async with model_session(profile) as model:
            for _ in range(2):
                factory = AgentLoopFactory(paths, "a" * 32, RunOptions())
                await factory.build(binding, model, checkpoints)
        assert len(discoveries) == 2
    finally:
        await checkpoints.close()


def test_member_binding_reads_definitions_in_constant_queries(tmp_path: Path) -> None:
    """因为成员增多不应产生逐人查询，需要在真实 SQLite 上约束绑定读取成本并核查共享定义。"""
    # 1、创建多个引用同一配置的形象，记录的都是测试数据，不读取用户仓库。
    repository = SqliteAccountRepository(tmp_path / "account.sqlite")
    try:
        accounts = AccountService(repository)
        first = accounts.save({"name": "成员一", "prompt": "共享配置"})
        for index in range(6):
            accounts.save({"name": f"成员{index + 2}", "agent_id": first["agent_id"]})
        selects = []

        def count_select(statement: str) -> None:
            """因为需要测量真正的查询数量，需要只统计 SQLite 实际发出的读取语句。"""
            # 1、回调只存在于本测试连接，生产不启用含参数的 SQL 日志。
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        repository._db.set_trace_callback(count_select)
        binding = accounts.binding(first["id"])
        assert len(selects) <= 3
        assert len(binding["workers"]) == 7
        assert binding["main"]["prompt"] == "共享配置"
        shared = [
            spec for spec in binding["workers"] if spec["actor"]["agent_id"] == first["agent_id"]
        ]
        assert len(shared) == 6
        assert all(spec["prompt"] == "共享配置" for spec in shared)
        # 2、批量查询不能把共享定义的可变列表变成成员间的共享对象。
        records = [
            item for item in repository.members() if item.get("agent_id") == first["agent_id"]
        ]
        records[0]["mcp_servers"].append({"name": "temporary-editor-value"})
        assert records[1]["mcp_servers"] == []
        assert accounts.get(first["id"])["mcp_servers"] == []
    finally:
        repository.close()
