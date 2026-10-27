"""桌面组合层：成员外观、场景与表现适配，后端执行框架保持独立。"""

import asyncio
from typing import Any

from roomcrew.accounts.service import AccountService
from roomcrew.application.runtime import Runtime
from roomcrew_desktop.accounts import DesktopAccountService
from roomcrew_desktop.assets.library import AvatarLibrary
from roomcrew_desktop.studio import StudioService

DESKTOP_METHODS = frozenset(
    {
        "studio_feed",
        "acknowledge_bubble",
        "scene_move",
        "scene_edit",
        "preferences",
        "avatar_catalog",
        "avatar_asset",
        "import_avatar",
        "import_avatar_example",
        "import_avatar_portrait",
        "import_avatar_bundle",
    }
)


class DesktopRuntime(Runtime):
    def _create_accounts(self) -> AccountService:
        """因为桌面需要验证人物素材，需要在客户端组合点扩展通用人员服务。"""
        # 1、素材路径与动作规则不会导入后端执行模块。
        self._avatars = AvatarLibrary(self.paths.data / "avatars")
        return DesktopAccountService(
            self._account_repository, self._avatars.require_id, self._avatars.clip_catalog
        )

    async def start(self) -> None:
        """因为场景缓存不应阻止后端独立使用，需要由桌面启动时单独装配。"""
        # 1、先启动后端，再初始化只读表现消费者。
        await super().start()
        self._studio = StudioService(
            self.paths, self.accounts, self.generate_auxiliary, self.configuration
        )

    async def close(self) -> None:
        """因为桌面缓存与执行资源各自持有连接，需要先结束客户端辅助任务再释放后端。"""
        # 1、表现异常不能阻止任务和数据库关闭。
        try:
            await self._studio.close()
        finally:
            await super().close()

    async def studio_feed(self, after: int = 0) -> dict[str, Any]:
        """因为空间订阅必须与执行解耦，需要只消费独立表现服务的快照。"""
        # 1、返回版本化的普通字典，不提供 SDK 状态或原始消息。
        return await self._studio.feed(after)

    async def acknowledge_bubble(self, member_id: str, notice_id: str) -> dict[str, bool]:
        """因为完成泡泡只能由用户查看后消除，需要提供桌面专属的幂等已读入口。"""
        # 1、只登记人物显示回执，不改变任务、工具权限或人工答复。
        self.accounts.get(member_id)
        await asyncio.to_thread(self._studio.bubbles.acknowledge, member_id, notice_id)
        return {"acknowledged": True}

    async def scene_move(
        self, member_id: str, anchor_id: str, revision: int, start: list[int] | None = None
    ) -> dict[str, Any]:
        """因为空间操作有单独版本规则，需要转交表现服务验证。"""
        # 1、动画完成回调不属于任务执行合同。
        return await self._studio.move(member_id, anchor_id, revision, start)

    async def scene_edit(self, values: dict[str, Any], revision: int) -> dict[str, Any]:
        """因为家具布置不能绕过边界约束，需要统一应用布局校验。"""
        # 1、应用门面不接受像素或模型生成的任意脚本。
        return await self._studio.edit(values, revision)

    async def preferences(self, values: dict[str, Any]) -> dict[str, Any]:
        """因为额外模型调用由用户决定，需要单独保存表现偏好。"""
        # 1、此入口不注册为 Agent 工具。
        return await self._studio.preferences(values)

    async def save_member(self, values: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        """因为用户需要管理可复用员工属性，需要在可信入口校验并持久化账号元数据。"""
        # 1、首版在忙碌时不修改人员定义，历史运行仍保留已经固定的快照。
        if self.active or self._execution.state.questions():
            raise ValueError("请先完成或取消当前任务，再修改成员")
        distinct = {
            member["avatar_id"]
            for member in self.accounts.members()
            if member["id"] != values.get("id") and member["avatar_id"] != "builtin:crew-v1"
        }
        candidate = values.get("avatar_id", "builtin:crew-v1")
        if candidate != "builtin:crew-v1" and candidate not in distinct and len(distinct) >= 8:
            raise ValueError("同一空间最多同时使用 8 套自定义图集，请复用已有素材")
        return self.accounts.save(values, expected_revision)

    async def avatar_catalog(self) -> list[dict[str, Any]]:
        """因为成员表单只需要素材概况，需要按需读取本地库而不每轮广播图片。"""
        # 1、文件 IO 放在独立工作线程，不阻塞 Agent 调度循环。
        return await asyncio.to_thread(self._avatars.catalog)

    async def avatar_asset(self, identifier: str) -> dict[str, Any]:
        """因为渲染器不能读取任意本机文件，需要按注册 ID 请求有限 PNG 数据。"""
        # 1、此入口不作为 Agent 工具，不返回本地路径。
        return await asyncio.to_thread(self._avatars.asset, identifier)

    async def import_avatar(self, path: str) -> dict[str, Any]:
        """因为用户手工选择素材后需要安全注册，需要在线程中完成图片校验和原子导入。"""
        # 1、路径仅由原生选择器传入，不通过前端自由拼接路径。
        from pathlib import Path

        return await asyncio.to_thread(self._avatars.import_manifest, Path(path))

    async def import_avatar_example(self) -> dict[str, Any]:
        """因为用户需要可直接试用和修改的动作模板，需要从随程序分发的固定样例导入。"""
        # 1、开发源码与冻结包使用各自固定资源路径，不接受外部路径或 URL。
        resources = self.paths.resources
        packaged = resources / "materials/crew-avatar-example/avatar.json"
        source = resources / "doc/assets/crew-avatar-example/avatar.json"
        selected = packaged if packaged.is_file() else source
        if not selected.is_file():
            raise ValueError("随附素材样例缺失，请保留完整程序目录")
        return await asyncio.to_thread(self._avatars.import_manifest, selected)

    async def import_avatar_portrait(self) -> dict[str, Any]:
        """因为用户需要比较新的手绘人物效果，需要导入固定随附图集而不接收任意宿主路径。"""
        # 1、源码和冻结包的图集都跟随前端资源；仍通过同一个正式校验器注册。
        selected = self.paths.resources / "desktop/ui" / "studio/assets/atelier-v1/avatar.json"
        if not selected.is_file():
            raise ValueError("手绘角色样板缺失，请保留完整程序目录")
        return await asyncio.to_thread(self._avatars.import_manifest, selected)

    async def import_avatar_bundle(self, role: str) -> dict[str, Any]:
        """因为用户需要完整角色套装，需要从有限的随附人物库导入双页清单而不接收任意文件路径。"""
        # 1、这里只选择美术形象，不创建 Agent、修改身份或授予监管权限。
        if role not in ("owner", "assistant", "employee", "guardian"):
            raise ValueError("未知的内置人物素材")
        selected = (
            self.paths.resources
            / "desktop/ui"
            / "studio/assets/library-v1/characters"
            / role
            / "avatar.json"
        )
        return await asyncio.to_thread(self._avatars.import_manifest, selected)
