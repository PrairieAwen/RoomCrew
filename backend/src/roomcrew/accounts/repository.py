"""账号数据仓库合同，不依赖 SQLite 或 Agent SDK。"""

from typing import Any, Protocol


class AccountRepository(Protocol):
    def preferences(self) -> dict[str, Any]:
        """因为账号偏好未来随账号同步，需要通过独立仓库合同读取。"""
        # 1、偏好不包含秘密。
        ...

    def set_preferences(self, values: dict[str, Any]) -> None:
        """因为旁白启用需要人工显式选择，需要持久保存安全的账号偏好。"""
        # 1、不接受密钥或本地绝对路径。
        ...

    def members(self) -> list[dict[str, Any]]:
        """因为账号配置未来会迁移云端，需要通过仓库合同列出人物及绑定定义。"""
        # 1、实现方返回普通数据，不包含真实凭据。
        ...

    def save(self, member: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        """因为并发编辑不能静默覆盖，需要按版本写入人物和 Agent 配置。"""
        # 1、实现方必须原子比较修订号。
        ...

    def close(self) -> None:
        """因为仓库可能持有本机或远程连接，需要统一释放资源。"""
        # 1、不修改用户保存的配置。
        ...
