"""只读运行快照中的可委派 Agent 目录。"""

import json
from collections.abc import Sequence

from langchain_core.tools import BaseTool, StructuredTool

from roomcrew.contracts.agents import AgentSpec


def agent_catalog_tool(specs: Sequence[AgentSpec]) -> BaseTool:
    """因为助手需要先发现已有 Agent 再准确委派，需要创建只读且不包含底层配置的目录工具。"""
    # 1、固定当前 Run 的公开能力目录，不提供提示词、端点、凭据或数据库入口。
    directory = json.dumps(
        [
            {
                "agent_id": spec.actor.agent_id,
                "member_id": spec.actor.member_id,
                "name": spec.actor.name,
                "subagent_type": spec.tool_name,
                "description": spec.description,
                "skills": [skill["name"] for skill in spec.configuration.get("skills", [])],
                "python_enabled": spec.configuration.get("python_enabled", True),
            }
            for spec in specs
        ],
        ensure_ascii=False,
    )

    def list_agents() -> str:
        """因为模型不应猜测员工标识，需要返回本轮可通过 task 调用的 Agent 目录。"""
        # 1、目录仅来自已验证的配置快照；工具不能创建配置或扩张权限。
        return directory

    return StructuredTool.from_function(
        list_agents, name="list_agents", metadata={"roomcrew_tool_kind": "directory"}
    )
