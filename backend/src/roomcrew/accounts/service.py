"""人物配置校验、默认身份和通用 Agent 定义装配。"""

import re
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from roomcrew.accounts.repository import AccountRepository
from roomcrew.contracts.agents import ActorRef, AgentSpec
from roomcrew.contracts.animation import leisure_profile

DEFAULTS = [
    ("assistant", "小禾", "assistant", "#6d9785"),
    ("guardian", "监管员", "guardian", "#718ea7"),
]


class AccountService:
    def __init__(
        self, repository: AccountRepository, avatar_validator: Callable[[str], None] | None = None
    ) -> None:
        """因为用户本人无需场景替身，需要只用稳定身份初始化助手和监管员。"""
        # 1、监管员是基础设施展示；只为助手和员工建立 Agent 绑定。
        self.repository = repository
        self._avatar_validator = avatar_validator
        existing = {member["id"] for member in repository.members()}
        for identifier, name, role, color in DEFAULTS:
            if identifier not in existing:
                self.save({"id": identifier, "name": name, "role": role, "color": color}, 0)

    def members(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """因为场景不应该广播完整提示配置，需要只提供显示属性及稳定身份。"""
        # 1、人物属性和 Agent 定义仍在仓库中完整保存，公开列表移除执行提示。
        return [
            {
                **{key: value for key, value in member.items() if key != "prompt"},
                **leisure_profile(member),
            }
            for member in self.repository.members()
            if member["role"] != "user" and (include_archived or not member["archived"])
        ]

    def get(self, member_id: str) -> dict[str, Any]:
        """因为用户编辑与运行绑定需要精确身份，需要查询已存在人物而不按名字模糊匹配。"""
        # 1、完整定义仅通过人工配置或可信执行装配路径使用。
        for member in self.repository.members():
            if member["id"] == member_id and member["role"] != "user":
                return {**member, **leisure_profile(member)}
        raise ValueError("成员不存在")

    def save(self, values: dict[str, Any], expected_revision: int = 0) -> dict[str, Any]:
        """因为账号配置不能夹带密钥或可执行代码入口，需要白名单校验后保存普通人物和 Agent 属性。"""
        # 1、未知字段直接拒绝，避免未来云端元数据混入凭据或本地路径。
        allowed = {
            "id",
            "name",
            "role",
            "color",
            "skin",
            "hair",
            "glasses",
            "prompt",
            "description",
            "enabled",
            "archived",
            "agent_id",
            "revision",
            "avatar_id",
            "agent_revision",
            "model_binding",
            "leisure_action",
            "leisure_actions",
            "leisure_delay",
        }
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("成员版本必须是非负整数")
        if set(values) - allowed:
            raise ValueError("成员配置包含不支持的字段")
        if values.get("model_binding", "execution:default") != "execution:default":
            raise ValueError("当前版本只支持默认执行模型引用")
        if "avatar_id" in values and values["avatar_id"] != "builtin:crew-v1":
            if not isinstance(values["avatar_id"], str) or self._avatar_validator is None:
                raise ValueError("请先导入并注册人物素材")
            self._avatar_validator(values["avatar_id"])
        for key in ("glasses", "enabled", "archived"):
            if key in values and not isinstance(values[key], bool):
                raise ValueError("人物开关必须是布尔值")
        identifier = str(values.get("id") or uuid4().hex)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", identifier):
            raise ValueError("人物标识无效")
        previous = next(
            (item for item in self.repository.members() if item["id"] == identifier), None
        )
        if previous is None and len(self.members(include_archived=True)) >= 16:
            raise ValueError("首版最多 16 位人物，请先复用或编辑已有成员")
        if previous and values.get("agent_id", previous.get("agent_id")) != previous.get(
            "agent_id"
        ):
            raise ValueError("已有形象不能直接更换 Agent 定义，请新增一个绑定形象")
        role = previous["role"] if previous else str(values.get("role", "employee"))
        if previous and values.get("role", role) != role:
            raise ValueError("已有成员的系统身份不能修改")
        if role not in {"assistant", "guardian", "employee"}:
            raise ValueError("未知人物身份")
        if not previous and identifier not in {row[0] for row in DEFAULTS} and role != "employee":
            raise ValueError("新增人物只能是员工")
        # 2、系统身份不能被改成普通员工或关闭；同一 Agent 定义可供多个形象引用。
        merged = {**(previous or {}), **values}
        reference = str(merged.get("agent_id") or "")
        shared = next(
            (
                item
                for item in self.repository.members()
                if reference and item.get("agent_id") == reference
            ),
            None,
        )
        if shared and not previous:
            merged = {**shared, **values, "id": identifier}
        name = str(merged.get("name", "新成员")).strip()
        prompt = str(merged.get("prompt", ""))
        description = str(merged.get("description", "通用文件与资料处理"))
        if not 1 <= len(name) <= 30 or len(prompt) > 8000 or len(description) > 300:
            raise ValueError("名称、职责或提示长度不符合要求")
        for key, default in (("color", "#6d9785"), ("skin", "#edc39b"), ("hair", "#51443e")):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(merged.get(key, default))):
                raise ValueError("外观颜色必须是六位十六进制颜色")
        enabled, archived = bool(merged.get("enabled", True)), bool(merged.get("archived", False))
        if role != "employee" and (not enabled or archived):
            raise ValueError("助手和监管员必须保留")
        agent_id = (
            None
            if role in {"user", "guardian"}
            else str(merged.get("agent_id") or "agent_" + identifier)
        )
        if agent_id is not None and not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", agent_id):
            raise ValueError("Agent 标识无效")
        # 3、头像只引用已注册素材，不能通过配置加载任意脚本或远程 URL。
        member = {
            "id": identifier,
            "name": name,
            "role": role,
            "agent_id": agent_id,
            "color": merged.get("color", "#6d9785"),
            "skin": merged.get("skin", "#edc39b"),
            "hair": merged.get("hair", "#51443e"),
            "glasses": bool(merged.get("glasses", False)),
            "avatar_id": merged.get("avatar_id", "builtin:crew-v1"),
            "prompt": prompt,
            "description": description,
            "enabled": enabled,
            "archived": archived,
            "agent_revision": merged.get("agent_revision", 0),
            "model_binding": "execution:default",
            **leisure_profile({**(previous or {}), **values, "role": role}),
        }
        return self.repository.save(member, expected_revision)

    def binding(self, member_id: str = "assistant") -> dict[str, Any]:
        """因为运行必须固定当时的身份与属性，需要建立不含模型秘密的主子 Agent 快照。"""
        # 1、明确指定员工就使用该配置；老板和监管员不能成为执行 Agent。
        root = self.get(member_id)
        if not root["enabled"] or root["archived"] or root["agent_id"] is None:
            raise ValueError("该人物不是可执行的 Agent")
        members = [
            item
            for item in self.repository.members()
            if item["role"] in {"employee", "assistant"}
            and item["enabled"]
            and not item["archived"]
            and item["id"] != member_id
        ]
        main = self._spec(root, "main")
        # 2、默认通用子任务归属于当前人物的独立上下文，不伪造一个已招募员工。
        general = AgentSpec(
            main.actor, "general-purpose", "通用子任务执行", main.prompt, main.revision
        )
        workers = [general, *[self._spec(item, "member_" + item["id"]) for item in members]]
        return {"main": main.snapshot(), "workers": [item.snapshot() for item in workers]}

    def _spec(self, member: dict[str, Any], tool_name: str) -> AgentSpec:
        """因为人物与执行器的身份不同，需要统一转换为无数据库依赖的 Agent 合同。"""
        # 1、Agent ID 标识配置，member ID 标识形象，二者不能混用共享任务状态。
        return AgentSpec(
            ActorRef(member["id"], member["agent_id"], member["name"]),
            tool_name,
            member["name"] + "：" + member.get("description", "通用任务"),
            member.get("prompt", ""),
            member.get("agent_revision", 1),
        )
