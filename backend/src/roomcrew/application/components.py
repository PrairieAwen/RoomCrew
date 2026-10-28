"""每次执行独立的 Agent 图工厂；集中装配能力，不持有产品状态或桌面对象。"""

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from roomcrew.accounts.configuration import agent_configuration
from roomcrew.agent_loop.engine import DeepAgentsLoop
from roomcrew.application.options import RunOptions
from roomcrew.contracts.agents import AgentSpec
from roomcrew.mcp.provider import configured_mcp_tools
from roomcrew.middleware.delegation import ConfiguredDelegationMiddleware
from roomcrew.middleware.stack import build_middleware
from roomcrew.models.private_chat import PrivateChatModel
from roomcrew.platform.paths import AppPaths
from roomcrew.skills.registry import materialize_skills, resolve_skill_sources
from roomcrew.storage.checkpoints import CheckpointStore
from roomcrew.tools.agents import agent_catalog_tool
from roomcrew.tools.files import file_tools
from roomcrew.tools.python import python_tool
from roomcrew.tools.registry import file_backend, local_tools


class AgentLoopFactory:
    def __init__(self, paths: AppPaths, conversation_id: str, options: RunOptions) -> None:
        """因为主子 Agent 应使用同一装配规则，需要为本次执行固定文件根、策略和共享资源。

        每次 invoke / 人工恢复新建工厂；锁与 MCP 发现缓存不跨 Run 复用，不读取模型秘密。
        """
        # 1、在创建模型前验证能力与显式技能来源；错误不回退到其他目录或执行后端。
        options.capabilities.validate_release()
        self._root = paths.session_files(conversation_id)
        self._sources = resolve_skill_sources(self._root, options.skills)
        self._options = options
        self._skill_home = paths.data / "skill-bundles"
        self._skill_home.mkdir(exist_ok=True)
        self._backend = file_backend(self._root, self._skill_home)
        # 2、同一轮脚本串行、相同 MCP 配置只发现一次；不同工厂不共享这些可变资源。
        self._cache = paths.root / "cache"
        self._script_lock = asyncio.Lock()
        self._mcp_catalog: dict[str, list[Any]] = {}

    async def build(
        self,
        binding: dict[str, Any],
        model: PrivateChatModel,
        checkpoints: CheckpointStore,
    ) -> DeepAgentsLoop:
        """因为执行服务只应管理 Run 生命周期，需要在单一工厂按快照建立主子 Agent 图。

        模型和 saver 的所有权仍属于调用方；每位 Agent 获得独立工具闭包、中间件及技能来源。
        """
        # 1、统一遍历主子定义装配能力，不为员工角色复制另一套构图逻辑。
        main = AgentSpec.restore(binding["main"])
        workers = [AgentSpec.restore(item) for item in binding["workers"]]
        components = {}
        middleware = {}
        for spec in (main, *workers):
            components[spec.tool_name] = await self._components(
                spec, workers if spec is main else []
            )
            middleware[spec.tool_name] = build_middleware(
                model, self._backend, self._options.compression
            )
        # 2、主 Agent 才能委派；所有中间件仍经过公开扩展点，底层只有 Deep Agents 一套 Loop。
        tools, skills = components[main.tool_name]
        return DeepAgentsLoop(
            model=model,
            backend=self._backend,
            tools=tools,
            middleware=[*middleware[main.tool_name], ConfiguredDelegationMiddleware(workers)],
            worker_middleware={spec.tool_name: middleware[spec.tool_name] for spec in workers},
            skills=skills,
            checkpointer=checkpoints.saver,
            limits=self._options.limits,
            redact=model.redact,
            main=main,
            workers=workers,
            worker_tools={spec.tool_name: components[spec.tool_name][0] for spec in workers},
            worker_skills={spec.tool_name: components[spec.tool_name][1] for spec in workers},
        )

    async def _components(
        self, spec: AgentSpec, workers: Sequence[AgentSpec]
    ) -> tuple[list[Any], list[str]]:
        """因为不同 Agent 的能力配置可以不同，需要在共用策略内按定义选择工具与技能。"""
        # 1、恢复快照也重新验证；工具来源标签由各工具的注册处维护，不在调度层按名称猜测。
        configuration = agent_configuration(spec.configuration)
        policy = self._options.capabilities
        tools = [*local_tools(policy), *file_tools(self._root), agent_catalog_tool(workers)]
        if configuration["python_enabled"] and policy.code_execution:
            tools.append(python_tool(self._root, self._cache, self._script_lock))
        # 2、缓存仅限本次工厂；保留顺序发现、工具重名拒绝及显式配置语义。
        if policy.mcp:
            key = json.dumps(configuration["mcp_servers"], sort_keys=True)
            if key not in self._mcp_catalog:
                self._mcp_catalog[key] = await configured_mcp_tools(configuration["mcp_servers"])
            tools.extend(self._mcp_catalog[key])
        if len({item.name for item in tools}) != len(tools):
            raise ValueError("工具名称冲突，请调整 MCP 服务器名称")
        source = materialize_skills(self._skill_home, configuration)
        return tools, ([source] if source else []) + self._sources
