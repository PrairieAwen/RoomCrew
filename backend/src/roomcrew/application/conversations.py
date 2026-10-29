"""持久人物对话选择与封存后的延续线程；不共享并行任务的可变上下文。"""

from typing import Any

from roomcrew.accounts.service import AccountService
from roomcrew.config.store import ConfigStore
from roomcrew.storage.sessions import SessionStore


class ConversationService:
    def __init__(self, store: SessionStore, accounts: AccountService, config: ConfigStore) -> None:
        """因为人物点击与任务发送应复用同一解析规则，需要注入会话、身份和可信配置引用。"""
        # 1、不持有模型客户端，不在选择聊天时调用模型或新建空会话。
        self.store, self.accounts, self.config = store, accounts, config

    def member(self, identifier: str) -> dict[str, Any]:
        """因为监管员与停用形象不能接单，需要验证当前空间中的真实可执行成员。"""
        # 1、同名与跨空间身份不会被隐式替换为助手。
        member = self.accounts.get(identifier)
        if not member["agent_id"] or not member["enabled"] or member.get("archived"):
            raise ValueError("该成员当前不能接单")
        return member

    def preferred(self, member_id: str) -> dict[str, Any] | None:
        """因为再次点击人物应恢复其持久聊天，需要读取自己的默认线程而不创建新消息。"""
        # 1、归档线程返回只读引用，实际延续在发送时完成。
        self.member(member_id)
        return self.store.memory.preferred(member_id)

    def prepare(self, member_id: str, reference: str = "") -> dict[str, Any]:
        """因为用户不必感知封存换线程，需要在发送前选择可续写的自己的会话或新建延续会话。"""
        # 1、显式选择优先；没有选择时复用持久默认聊天，仍不混用其他人的活动线程。
        member = self.member(member_id)
        profile = self.config.require_profile()
        previous = self.store.conversation(reference) if reference else self.preferred(member_id)
        if previous is not None:
            owner = self.store.memory.get(previous["id"])["member_id"]
            if owner and owner != member_id:
                previous = self.preferred(member_id)
        if previous is not None:
            memory = self.store.memory.get(previous["id"])
            status = self.store.latest_status(previous["id"])
            if (
                memory["lifecycle"] == "open"
                and memory["member_id"] in {"", member_id}
                and previous["profile_ref"] == profile.reference
                and status not in {"failed", "cancelled", "interrupted"}
            ):
                return previous
        # 2、封存、失败或模型绑定变化时用新 checkpoint；旧证据与文件始终保留。
        created = self.store.create_conversation(profile.reference)
        with self.store.connection:
            self.store.memory.bind(created["id"], member_id, member["agent_id"])
            self.store.connection.execute(
                "UPDATE conversation_memory SET predecessor_id=? WHERE conversation_id=?",
                (previous["id"] if previous else None, created["id"]),
            )
        return {**created, "predecessor_id": previous["id"] if previous else None}
