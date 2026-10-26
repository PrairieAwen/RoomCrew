"""框架 checkpoint 的独立生命周期，不承担产品会话或工具副作用记录。"""

from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class CheckpointStore:
    def __init__(self, database: Path) -> None:
        """因为异步连接必须由所属事件循环管理，需要先保存上下文再显式打开。"""
        # 1、该库只交给框架，产品 SQLite 保持为另一连接和文件。
        self._context = AsyncSqliteSaver.from_conn_string(str(database))
        self._saver: AsyncSqliteSaver | None = None

    async def start(self) -> None:
        """因为构图前需要可用 checkpoint，需要在运行时线程内打开共享 saver。"""
        # 1、重复启动不新建第二条连接。
        if self._saver is None:
            self._saver = await self._context.__aenter__()

    @property
    def saver(self) -> AsyncSqliteSaver:
        """因为未启动的数据库不能悄悄退化为内存状态，需要在获取适配器时验证连接。"""
        # 1、启动顺序错误必须显式失败。
        if self._saver is None:
            raise RuntimeError("checkpoint 尚未启动")
        return self._saver

    async def close(self) -> None:
        """因为退出时需要释放后台 SQLite 线程，需要在任务停止后关闭 saver。"""
        # 1、未成功打开或已经关闭时不重复释放。
        if self._saver is not None:
            await self._context.__aexit__(None, None, None)
            self._saver = None
