"""人工 MCP 配置、保护引用、实际鉴权和秘密回显边界。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from mcp_fixture import mcp_server
from test_agent_capabilities import configured_runtime, wait_finished
from test_runtime import model_server, tool_message

from roomcrew.application.mcp_settings import MCPSettings
from roomcrew.application.runtime import Runtime
from roomcrew.config.mcp_credentials import MCPCredentials
from roomcrew.contracts.errors import ExecutionError
from roomcrew.platform.paths import AppPaths

KEY = "synthetic-mcp-secret-not-real-934782"


async def test_credentials_are_private_scoped_immutable_and_rollback(tmp_path: Path) -> None:
    """因为同一服务可被多个形象和历史 Run 引用，需要验证保护保存、CAS 回滚与端点隔离。"""
    # 1、测试独立数据目录，不读取用户的任何配置；新 Key 不进入普通账号数据。
    paths = AppPaths.create(tmp_path)
    runtime = Runtime(paths)
    await runtime.start()
    server = {"name": "search", "url": "https://example.com/mcp", "enabled": True}
    auth = {"search": {"mode": "bearer", "api_key": KEY}}
    try:
        member = await runtime.save_member({"id": "assistant", "mcp_servers": [server]}, 1, auth)
        saved = member["mcp_servers"][0]
        reference = saved["auth_ref"]
        store = MCPCredentials(paths.private, paths.data.relative_to(paths.root).as_posix())
        assert store.key(saved) == KEY
        assert KEY not in json.dumps(member)
        assert KEY.encode() not in (paths.private / "mcp-credentials.dpapi").read_bytes()
        assert KEY.encode() not in (paths.data / "account.sqlite").read_bytes()
        # 2、留空保留同一引用；改地址留空、跨空间引用、公网 HTTP 和 Header 注入均拒绝。
        retained = await runtime.save_member(
            {"id": "assistant", "mcp_servers": [saved]},
            member["revision"],
            {"search": {"mode": "bearer", "api_key": ""}},
        )
        assert retained["mcp_servers"][0]["auth_ref"] == reference
        with pytest.raises(ValueError, match="重新填写"):
            store.resolve({**saved, "url": "https://other.example/mcp"}, {"mode": "bearer"})
        with pytest.raises(ValueError, match="重新填写"):
            MCPCredentials(paths.private, "other-workspace").key(saved)
        with pytest.raises(ValueError, match="HTTPS"):
            store.validate_key("http://example.com/mcp", KEY)
        with pytest.raises(ValueError, match="换行"):
            store.validate_key(server["url"], KEY + "\r\nInjected:1")
        # 3、业务版本冲突不能遗留新增凭据；真正换地址并填新 Key 则获得新引用。
        before = store._load()
        with pytest.raises(ValueError):
            await runtime.save_member(
                {"id": "assistant", "mcp_servers": [saved]},
                0,
                {"search": {"mode": "bearer", "api_key": KEY + "new"}},
            )
        assert store._load() == before
        changed = await runtime.save_member(
            {"id": "assistant", "mcp_servers": [{**saved, "url": "https://other.example/mcp"}]},
            retained["revision"],
            auth,
        )
        assert changed["mcp_servers"][0]["auth_ref"] != reference
        assert store.key(saved) == KEY
        # 4、显式移除认证只移除公开引用，历史凭据仍可供原端点的 checkpoint 使用。
        removed = await runtime.save_member(
            {"id": "assistant", "mcp_servers": changed["mcp_servers"]},
            changed["revision"],
            {"search": {"mode": "none"}},
        )
        assert "auth_ref" not in removed["mcp_servers"][0]
    finally:
        await runtime.close()


async def test_unsaved_probe_authentication_and_discovery_echo(tmp_path: Path) -> None:
    """因为测试应验证当前表单而不先保存，需要通过真实 MCP 验证认证、失败和目录回显拒绝。"""
    # 1、正确 Key 发现工具，错误 Key 拒绝，测试不执行工具且不持久化任何秘密。
    settings = MCPSettings(AppPaths.create(tmp_path))
    with mcp_server(api_key=KEY) as (url, calls):
        server = {"name": "math", "url": url, "enabled": False}
        reply = await settings.test(server, {"mode": "bearer", "api_key": KEY})
        assert reply == {"connected": True, "tools": ["math_add_numbers"]}
        assert not calls
        with pytest.raises(ExecutionError, match="MCP_CONNECTION"):
            await settings.test(server, {"mode": "bearer", "api_key": "wrong-key"})
    assert not (tmp_path / "private/mcp-credentials.dpapi").exists()
    # 2、目录描述回显 Key 时拒绝注册，避免在首次模型请求中泄露。
    with (
        mcp_server(api_key=KEY, discovery_echo=True) as (url, _),
        pytest.raises(ExecutionError, match="MCP_CONNECTION"),
    ):
        await settings.test({"name": "bad", "url": url}, {"mode": "bearer", "api_key": KEY})


async def test_authenticated_mcp_executes_and_redacts_before_model_and_checkpoint(
    tmp_path: Path,
) -> None:
    """因为界面保存成功不等于 Agent 真能使用，需要验证生产 Loop、官方工具事件与密钥回显过滤。"""
    # 1、只有模型响应是确定性合成内容，工具发现、认证、调用、存储均走生产实现。
    replies = [
        tool_message("math_add_numbers", {"left": 19, "right": 23}),
        {"role": "assistant", "content": "结果为 42"},
    ]
    with (
        mcp_server(api_key=KEY, echo_key=True) as (url, calls),
        model_server(replies) as (endpoint, requests),
    ):
        runtime = await configured_runtime(tmp_path, endpoint)
        try:
            await runtime.save_member(
                {"id": "assistant", "mcp_servers": [{"name": "math", "url": url}]},
                1,
                {"math": {"mode": "bearer", "api_key": KEY}},
            )
            conversation = await runtime.new_conversation()
            await runtime.submit(conversation["id"], "调用数学 MCP 计算 19 加 23", uuid4().hex)
            await wait_finished(runtime)
            assert runtime.store.latest_status(conversation["id"]) == "completed"
            assert calls == [{"left": 19, "right": 23}]
            assert "42" in json.dumps(requests[-1]["messages"])
            assert KEY not in json.dumps(requests)
            assert "已隐藏凭据" in json.dumps(requests[-1]["messages"], ensure_ascii=False)
            events = await runtime.events(conversation["id"])
            assert any(event["payload"].get("tool_kind") == "mcp" for event in events)
            cursor, native = 0, []
            while batch := await runtime.native_events(conversation["id"], cursor):
                native.extend(batch)
                cursor = batch[-1]["seq"]
            assert KEY not in json.dumps(events + native)
            assert any(item["native"]["event"] == "on_tool_end" for item in native)
        finally:
            await runtime.close()
    # 2、关闭 SQLite 后检查真实数据库与任务文件，保护文件是唯一允许包含加密秘密的位置。
    for path in (tmp_path / "data").rglob("*"):
        if path.is_file():
            assert KEY.encode() not in path.read_bytes(), path.name
