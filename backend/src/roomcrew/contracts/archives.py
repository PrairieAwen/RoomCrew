"""受限的档案查询合同；不向 Agent 提供共享权限写入或任意文件路径。"""

from typing import Any, Protocol


class ArchiveQueries(Protocol):
    async def search(self, member_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """因为检索身份应来自实际执行者，需要固定成员后查询用户允许的档案范围。"""
        # 1、默认仅当前空间和自己的历史。
        ...

    async def read(self, identifier: str, offset: int = 0, limit: int = 10) -> dict[str, Any]:
        """因为摘要可能丢失细节，需要在权限检查后读取完整公开消息页。"""
        # 1、返回来源而非内部磁盘路径。
        ...

    async def recent(self, member_id: str) -> str:
        """因为无感续聊只应装入少量近期信息，需要返回有日期和来源的受限上下文。"""
        # 1、历史资料不能作为系统授权或新任务指令。
        ...
