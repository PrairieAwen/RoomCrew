"""桌面桥：显式工作空间请求与人工本地文件选择。"""

from collections.abc import Callable
from typing import Any

from roomcrew_desktop.host import RuntimeThread
from roomcrew_desktop.responses import public_reply


class DesktopAPI:
    def __init__(
        self, host: RuntimeThread, avatar_picker: Callable[[], str | None] | None = None
    ) -> None:
        """因为桌面界面要按会议室隔离操作，需要只暴露具名目录方法和有界业务请求。"""
        # 1、后端、配置和数据库对象均保留为私有引用，不发布成桥属性。
        self._host = host
        self._avatar_picker = avatar_picker

    @public_reply
    def workspace_state(self) -> dict[str, Any]:
        """因为首次启动尚无活动空间标识，需要取得目录与上次选择的会议室。"""
        # 1、不广播其他空间的会话、工具参数或模型配置。
        return self._host.call(self._host.hub.state())

    @public_reply
    def create_workspace(self, name: str) -> dict[str, Any]:
        """因为每个新空间必须有独立会议室，需要通过目录用例创建并打开它。"""
        # 1、显示名称不作为文件路径。
        return self._host.call(self._host.hub.create(name))

    @public_reply
    def select_workspace(self, identifier: str) -> dict[str, Any]:
        """因为切换画布不能停止后台任务，需要只更新活动会议室选择。"""
        # 1、其他空间仍由各自 Runtime 执行。
        return self._host.call(self._host.hub.select(identifier))

    @public_reply
    def rename_workspace(self, identifier: str, name: str) -> dict[str, Any]:
        """因为改名应保留任务与人物，需要只修改空间及对应会议室的显示名称。"""
        # 1、保持稳定空间与房间 ID。
        return self._host.call(self._host.hub.rename(identifier, name))

    @public_reply
    def invoke(self, workspace_id: str, method: str, args: list[Any]) -> Any:
        """因为切换时可能有迟到请求，需要把所有业务调用绑定到原空间并由后端白名单分派。"""
        # 1、素材源路径只能来自人工选择器，页面不能通过通用请求传任意宿主路径。
        if method == "import_avatar":
            if args or self._avatar_picker is None:
                raise ValueError("请通过本地素材选择入口导入")
            selected = self._avatar_picker()
            if not selected:
                return {"cancelled": True}
            args = [selected]
        # 2、共享模型配置仍在可信本机入口，日志和请求不打印表单内容。
        return self._host.call(self._invoke(workspace_id, method, args))

    async def _invoke(self, workspace_id: str, method: str, args: list[Any]) -> Any:
        """因为空间目录的 SQLite 连接属于运行时线程，需要在同一事件循环组装桌面响应。"""
        # 1、先分派后端请求，再在桌面层添加会议室显示信息；不跨线程直接读取仓库。
        result = await self._host.hub.invoke(workspace_id, method, args)
        if method == "studio_feed":
            result = {**result, "workspace": self._host.hub.repository.get(workspace_id)}
        return result
