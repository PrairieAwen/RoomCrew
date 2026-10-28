"""可信用户配置和 Agent 装配之间的 MCP 凭据边界。"""

from typing import Any

from roomcrew.accounts.configuration import agent_configuration
from roomcrew.config.mcp_credentials import MCPCredentials
from roomcrew.mcp.provider import configured_mcp_tools
from roomcrew.platform.paths import AppPaths
from roomcrew.security.redaction import redact_value


class MCPSettings:
    def __init__(self, paths: AppPaths) -> None:
        """因为配置服务和执行工厂需要同一凭据作用域，需要按可信空间数据目录确定绑定。"""
        # 1、凭据位于全局私有目录，引用仍只能在创建它的会议室使用。
        self.credentials = MCPCredentials(
            paths.private, paths.data.relative_to(paths.root).as_posix()
        )
        self._keys: list[str] = []

    def connection_keys(self, servers: list[dict[str, Any]]) -> dict[str, str]:
        """因为请求认证仅属于可信 HTTP 连接，需要按启用服务解析 Key 而不改写 Agent 配置。"""
        # 1、关闭的服务不解密、不连接；已使用 Key 仅在当前工厂的内存中保留用于脱敏。
        keys = {}
        for server in servers:
            if server["enabled"] and server.get("auth_ref"):
                key = self.credentials.key(server)
                keys[server["name"]] = key
                if key not in self._keys:
                    self._keys.append(key)
        return keys

    def redact(self, value: Any) -> Any:
        """因为远端回显也可能出现在事件或工具结果中，需要递归过滤当前连接使用的所有 Key。"""
        # 1、长 Key 优先，避免短凭据先替换后留下长凭据片段。
        for key in sorted(self._keys, key=len, reverse=True):
            value = redact_value(value, key)
        return value

    async def test(self, server: dict[str, Any], auth: dict[str, Any] | None) -> dict[str, Any]:
        """因为用户尚未保存也应测试当前输入，需要临时连接并返回工具名，不写凭据和会话。"""
        # 1、仅测试当前一项，测试关闭的服务也不改变其持久启用开关。
        item = agent_configuration({"mcp_servers": [server]})["mcp_servers"][0]
        item["enabled"] = True
        key = self.credentials.resolve(item, auth)
        if key:
            self._keys.append(key)
        # 2、发现工具而不执行工具，避免测试产生搜索计费或其他业务副作用。
        tools = await configured_mcp_tools([item], {item["name"]: key}, self.redact)
        return {"connected": True, "tools": [tool.name for tool in tools]}
