"""可复用 Agent 执行配置；不包含人物动作、模型秘密或桌面协议。"""

import json
import re
from typing import Any
from urllib.parse import urlsplit

CONFIGURATION_FIELDS = ("skills", "mcp_servers", "python_enabled")


def agent_configuration(value: dict[str, Any]) -> dict[str, Any]:
    """因为同一 Agent 定义需要独立配置能力，需要验证可持久化的技能、MCP 与 Python 开关。"""
    # 1、开关只接受用户配置的布尔值，不把字符串真值当作执行授权。
    enabled = value.get("python_enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("Python 执行开关必须是布尔值")
    skills = value.get("skills", [])
    servers = value.get("mcp_servers", [])
    if not isinstance(skills, list) or len(skills) > 16:
        raise ValueError("每个 Agent 最多配置 16 个技能")
    if not isinstance(servers, list) or len(servers) > 8:
        raise ValueError("每个 Agent 最多配置 8 个 MCP 服务器")
    # 2、技能是数据与说明；正文按需加载，文件名不能逃出独立技能包。
    names: set[str] = set()
    normalized_skills = []
    for skill in skills:
        if not isinstance(skill, dict) or set(skill) - {
            "name",
            "description",
            "instructions",
            "files",
        }:
            raise ValueError("技能字段无效")
        name = skill.get("name", "")
        description = skill.get("description", "")
        instructions = skill.get("instructions", "")
        files = skill.get("files", {})
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name)
            or name in names
            or not isinstance(description, str)
            or not 1 <= len(description) <= 500
            or not isinstance(instructions, str)
            or not 1 <= len(instructions) <= 24000
            or not isinstance(files, dict)
            or len(files) > 16
        ):
            raise ValueError("技能需要唯一英文名称、描述和正文，且大小必须在限制内")
        for filename, content in files.items():
            if (
                not isinstance(filename, str)
                or not re.fullmatch(r"[a-zA-Z0-9_./-]{1,120}", filename)
                or filename.startswith("/")
                or any(part in {"", ".", ".."} for part in filename.split("/"))
                or filename.upper() == "SKILL.MD"
                or not isinstance(content, str)
                or len(content) > 32000
            ):
                raise ValueError("技能附带文件需要安全的相对路径和有限文本")
        names.add(name)
        normalized_skills.append(
            {
                "name": name,
                "description": description,
                "instructions": instructions,
                "files": dict(files),
            }
        )
    # 3、首个连接器支持 HTTP；凭据不允许混进 Agent 定义或工具目录。
    names.clear()
    normalized_servers = []
    for server in servers:
        if not isinstance(server, dict) or set(server) - {"name", "url", "enabled", "auth_ref"}:
            raise ValueError("MCP 配置只接受名称、HTTP 地址、启用开关与凭据引用")
        name, url = server.get("name", ""), server.get("url", "")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", name)
            or name in names
        ):
            raise ValueError("MCP 名称必须唯一并使用英文小写和下划线")
        if not isinstance(url, str) or len(url) > 500:
            raise ValueError("MCP 地址无效")
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("MCP 使用不含凭据和查询参数的 HTTP(S) 地址")
        if type(server.get("enabled", True)) is not bool:
            raise ValueError("MCP 启用开关必须是布尔值")
        names.add(name)
        normalized_servers.append(
            {"name": name, "url": url.rstrip("/"), "enabled": server.get("enabled", True)}
        )
        reference = server.get("auth_ref")
        if reference is not None:
            if not isinstance(reference, str) or not re.fullmatch(r"[a-f0-9]{32}", reference):
                raise ValueError("MCP 凭据引用无效")
            normalized_servers[-1]["auth_ref"] = reference
    result = {
        "skills": normalized_skills,
        "mcp_servers": normalized_servers,
        "python_enabled": enabled,
    }
    if len(json.dumps(result, ensure_ascii=False).encode()) > 256000:
        raise ValueError("Agent 能力配置超过 256 KB")
    return result
