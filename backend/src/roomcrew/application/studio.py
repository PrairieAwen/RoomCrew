"""空间用例组装：运行日志的消费者，不是执行器的前置依赖。"""

import asyncio
from typing import Any

from roomcrew.accounts.service import AccountService
from roomcrew.application.narration import NarrationService
from roomcrew.config.store import ConfigStore
from roomcrew.platform.paths import AppPaths
from roomcrew.presentation.projection import StudioProjection
from roomcrew.presentation.scene import SceneStore, default_room


class StudioService:
    def __init__(self, paths: AppPaths, accounts: AccountService) -> None:
        """因为人物空间应能独立降级，需要分开创建表现缓存、布局库和辅助模型服务。"""
        # 1、账号属性通过仓库接口读取，原始轨迹仅以只读连接消费。
        self.accounts = accounts
        self._scene_path = paths.data / "studio.sqlite"
        self._scene: SceneStore | None = None
        self.projection = StudioProjection(
            paths.data / "sessions.sqlite", paths.data / "presentation.sqlite"
        )
        self.config = ConfigStore(paths.private, "presentation-model.dpapi")
        self.narrator = NarrationService(self.config)

    @property
    def scene(self) -> SceneStore:
        """因为布局库损坏不能阻止执行器启动，需要延迟到空间请求时才打开独立连接。"""
        # 1、异常只传播给对应空间请求，不在主执行服务构造时打开布局库。
        if self._scene is None:
            self._scene = SceneStore(self._scene_path)
        return self._scene

    async def feed(self, after: int) -> dict[str, Any]:
        """因为空间只需要当前人物状态，需要异步生成最小快照而不广播消息或工具正文。"""
        # 1、只读投影运行在工作线程；损坏或繁忙时显示降级，不修改任务状态。
        try:
            projection = await asyncio.to_thread(self.projection.feed, max(0, int(after)))
        except Exception:
            projection = {
                "protocol_version": 1,
                "cursor": after,
                "actors": [],
                "reset": False,
                "degraded": True,
                "catching_up": False,
            }
        # 2、辅助旁白立即返回规则结果；不开启时不会使用执行模型替代配置。
        preferences = self.accounts.repository.preferences()
        actors = self.narrator.decorate(projection["actors"], preferences["narration_enabled"])
        members = self.accounts.members()
        live = {member["id"] for member in members}
        actors = [actor for actor in actors if actor["member_id"] in live]
        interactions = [
            {**group, "members": [member for member in group["members"] if member in live]}
            for group in projection.get("interactions", [])
        ]
        try:
            scene = self.scene.snapshot(members)
        except Exception:
            projection["degraded"] = True
            scene = {
                "room": {**default_room(), "revision": 0},
                "anchors": [],
                "placements": [],
                "catalog": {},
            }
        return {
            **projection,
            "actors": actors,
            "members": members,
            "interactions": [group for group in interactions if len(group["members"]) >= 2],
            "scene": scene,
            "preferences": preferences,
        }

    async def preferences(self, values: dict[str, Any]) -> dict[str, Any]:
        """因为额外模型请求必须由用户明确开启，需要验证独立连接并持久化偏好。"""
        # 1、开启前要求单独模型配置存在；禁用时取消辅助请求，不动主任务。
        if values.get("narration_enabled"):
            self.config.require_profile()
        self.accounts.repository.set_preferences(values)
        if not values["narration_enabled"]:
            await self.narrator.close()
        return self.accounts.repository.preferences()

    async def move(
        self, member_id: str, anchor_id: str, revision: int, start: list[int] | None = None
    ) -> dict[str, Any]:
        """因为用户可以指挥人物换座，需要验证实际人物后只改变空间显示目标。"""
        # 1、显示移动不调用 Agent，也不能回答人工问题或批准敏感操作。
        member = self.accounts.get(member_id)
        if member["archived"]:
            raise ValueError("已归档成员不能移动")
        return self.scene.move(member_id, anchor_id, revision, start)

    async def edit(self, values: dict[str, Any], revision: int) -> dict[str, Any]:
        """因为用户布置房间不能影响执行，需要把家具校验交给独立场景服务。"""
        # 1、该入口不修改任务、模型或权限配置。
        return self.scene.edit(values, revision)

    async def close(self) -> None:
        """因为退出不能遗留旁白请求和布局连接，需要独立关闭表现资源。"""
        # 1、表现服务不持有执行器对象。
        await self.narrator.close()
        if self._scene is not None:
            self._scene.close()
