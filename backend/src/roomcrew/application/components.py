"""按 Agent 定义组装真实工具与技能；不包含客户端表现逻辑。"""

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from roomcrew.accounts.configuration import agent_configuration
from roomcrew.contracts.agents import AgentSpec
from roomcrew.mcp.provider import configured_mcp_tools
from roomcrew.security.capabilities import CapabilityPolicy
from roomcrew.skills.registry import materialize_skills
from roomcrew.tools.agents import agent_catalog_tool
from roomcrew.tools.files import file_tools
from roomcrew.tools.python import python_tool
from roomcrew.tools.registry import local_tools


async def agent_components(
    spec: AgentSpec,
    workers: Sequence[AgentSpec],
    root: Path,
    cache: Path,
    skill_home: Path,
    policy: CapabilityPolicy,
    script_lock: asyncio.Lock,
    mcp_catalog: dict[str, list[Any]],
) -> tuple[list[Any], list[str]]:
    """因为每位 Agent 配置的技能与 MCP 可能不同，需要为本轮独立装配能力而不共享可变上下文。"""
    # 1、恢复的快照也重新校验路径与配置，避免损坏记录绕过首次保存规则。
    configuration = agent_configuration(spec.configuration)
    tools = [*local_tools(policy), *file_tools(root), agent_catalog_tool(workers)]
    for item in tools:
        if not item.metadata:
            item.metadata = {"roomcrew_tool_kind": "human" if item.name == "ask_user" else "tool"}
    # 2、按各自开关接入真实隔离脚本与 MCP，未知能力不伪装成功。
    if configuration["python_enabled"] and policy.code_execution:
        tools.append(python_tool(root, cache, script_lock))
    if policy.mcp:
        catalog_key = json.dumps(configuration["mcp_servers"], sort_keys=True)
        if catalog_key not in mcp_catalog:
            mcp_catalog[catalog_key] = await configured_mcp_tools(configuration["mcp_servers"])
        tools.extend(mcp_catalog[catalog_key])
    if len({item.name for item in tools}) != len(tools):
        raise ValueError("工具名称冲突，请调整 MCP 服务器名称")
    source = materialize_skills(skill_home, configuration)
    return tools, [source] if source else []
