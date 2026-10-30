"""空间用例组装：运行日志的消费者，不是执行器的前置依赖。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from roomcrew.accounts.service import AccountService
from roomcrew.platform.paths import AppPaths
from roomcrew_desktop.accounts import interaction_profile
from roomcrew_desktop.presentation.action_queue import ActionQueueStore
from roomcrew_desktop.presentation.animation import animation_hint
from roomcrew_desktop.presentation.bubbles import BubbleStore
from roomcrew_desktop.presentation.narration import NarrationService
from roomcrew_desktop.presentation.projection import StudioProjection
from roomcrew_desktop.presentation.scene import SceneStore, default_room


class StudioService:
    def __init__(
        self,
        paths: AppPaths,
        accounts: AccountService,
        generate: Callable[[str], Awaitable[str]],
        configuration: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> None:
        """因为人物空间应能独立降级，需要分开创建表现缓存、布局库和辅助模型服务。"""
        # 1、账号属性通过仓库接口读取，原始轨迹仅以只读连接消费。
        self.accounts = accounts
        self._scene_path = paths.data / "studio.sqlite"
        self._scene: SceneStore | None = None
        self.projection = StudioProjection(
            paths.data / "sessions.sqlite", paths.data / "presentation.sqlite"
        )
        self._configuration = configuration
        self.bubbles = BubbleStore(paths.data / "sessions.sqlite", paths.data / "bubbles.sqlite")
        self._bubble_snapshot: dict[str, list[dict[str, Any]]] = {}
        self.actions = ActionQueueStore(
            paths.data / "sessions.sqlite", paths.data / "scene-actions.sqlite"
        )
        self.narrator = NarrationService(generate)

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
        try:
            notices = await asyncio.to_thread(self.bubbles.feed, projection["cursor"])
            self._bubble_snapshot = notices
        except Exception:
            # 提示库异常保留上一次未读快照并明确降级，不让显示问题中断后端任务。
            notices = self._bubble_snapshot
            projection["degraded"] = True
        # 2、辅助旁白立即返回规则结果；未读提示独立于最新动作，不受新任务覆盖。
        preferences = self.accounts.repository.preferences()
        try:
            projection.update(await asyncio.to_thread(self.actions.feed, projection["cursor"]))
        except Exception:
            projection["degraded"] = True
            projection.update(actions=[], actions_pending=0)
        actors = projection["actors"]
        members = self.accounts.members()
        definitions = {item["id"]: item for item in members}
        for actor in actors:
            pending = notices.get(actor["member_id"], [])
            question_count = sum(item["kind"] == "question" for item in pending)
            was_question = actor["requires_input"]
            actor["question_count"] = question_count
            actor["requires_input"] = question_count > 0
            if question_count or was_question:
                # 人工问题由入口人物转达；实际子任务等待仍保留在原始会话轨迹。
                activity = "question" if question_count else "waiting"
                actor.update(
                    activity=activity,
                    action_id="ask" if question_count else "idle",
                    summary="等待你答复" if question_count else "等待主 Agent 协调",
                    idle_eligible=False,
                    animation=animation_hint(
                        activity, [], question_count, actor["warning_count"], []
                    ),
                )
            actor["external_calls"] += sum(
                target not in definitions for target in actor.get("delegation_targets", [])
            )
            profile = interaction_profile(
                definitions.get(actor["member_id"], {}).get("interaction_profile", {})
            )
            category = (
                "human"
                if actor["requires_input"]
                else "completed"
                if actor["activity"] == "reporting"
                else "tool"
                if actor["active_contexts"]
                else None
            )
            action = profile["action_overrides"].get(category)
            if action:
                actor["animation"] = {**actor["animation"], "gesture": action}
            actor["material_category"] = category
            binding = (
                definitions.get(actor["member_id"], {})
                .get("material_profile", {})
                .get("bindings", {})
                .get(category)
            )
            if binding:
                actor["animation"] = {**actor["animation"], "gesture": binding["action"]}
            notice = pending[0] if pending else None
            actor["bubble_notice"] = notice
            actor["bubble_pending_count"] = len(pending)
            actor["report_acknowledged"] = not any(item["kind"] == "result" for item in pending)
            actor["bubble"] = (
                profile["question_bubble"]
                if notice and notice["kind"] == "question"
                else "有历史结果待查看，当前任务仍在进行。"
                if notice and actor["active_contexts"] > 0
                else profile["completed_bubble"]
                if notice
                else ""
            )
            actor["bubble_is_history"] = bool(
                notice and notice["kind"] == "result" and actor["active_contexts"] > 0
            )
        actors = self.narrator.decorate(actors, preferences["narration_enabled"])
        question_presenters = {
            item["request_id"]: member
            for member, pending in notices.items()
            for item in pending
            if item["kind"] == "question"
        }
        questions_by_seq = {
            item["source_seq"]: member
            for member, pending in notices.items()
            for item in pending
            if item["kind"] == "question"
        }
        projection["cues"] = [
            {**cue, "member_id": questions_by_seq[cue["source_seq"]]}
            if cue["action"] == "ask"
            else cue
            for cue in projection.get("cues", [])
            if cue["action"] != "ask" or cue["source_seq"] in questions_by_seq
        ]
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
            "default_avatars": getattr(self.accounts, "default_avatars", {}),
            "question_presenters": question_presenters,
            "interactions": [group for group in interactions if len(group["members"]) >= 2],
            "scene": scene,
            "preferences": preferences,
        }

    async def preferences(self, values: dict[str, Any]) -> dict[str, Any]:
        """因为额外模型请求必须由用户明确开启，需要验证独立连接并持久化偏好。"""
        # 1、开启前要求单独模型配置存在；禁用时取消辅助请求，不动主任务。
        if values.get("narration_enabled") and not (await self._configuration("presentation")).get(
            "configured"
        ):
            raise ValueError("请先配置辅助模型")
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
