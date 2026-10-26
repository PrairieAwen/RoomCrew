"""桌面应用用例门面；不包含图构建、SDK 事件解析或文件路径算法。"""

import asyncio
from typing import Any

from roomcrew.accounts.service import AccountService
from roomcrew.application.artifacts import ArtifactService
from roomcrew.application.execution import ExecutionService
from roomcrew.application.options import RunOptions
from roomcrew.application.studio import StudioService
from roomcrew.assets.library import AvatarLibrary
from roomcrew.config.store import ConfigStore
from roomcrew.models.connection import test_model_connection, test_presentation_connection
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.accounts import SqliteAccountRepository
from roomcrew.storage.checkpoints import CheckpointStore
from roomcrew.storage.sessions import SessionStore


class Runtime:
    def __init__(self, paths: AppPaths, options: RunOptions | None = None) -> None:
        """因为桌面需要稳定入口而各模块需要独立演进，需要在应用边界组装服务。"""
        # 1、只连接职责模块，不把模型秘密注入图状态或前端合同。
        self.paths = paths
        self.config = ConfigStore(paths.private)
        self.store = SessionStore(paths.data / "sessions.sqlite")
        self._account_repository = SqliteAccountRepository(paths.data / "account.sqlite")
        self._avatars = AvatarLibrary(paths.data / "avatars")
        self.accounts = AccountService(self._account_repository, self._avatars.require_id)
        self._studio = StudioService(paths, self.accounts)
        self._checkpoints = CheckpointStore(paths.data / "runtime.sqlite")
        self._artifacts = ArtifactService(paths, self.store)
        self._execution = ExecutionService(
            paths=paths,
            config=self.config,
            store=self.store,
            checkpoints=self._checkpoints,
            options=options or RunOptions(),
            accounts=self.accounts,
        )

    @property
    def active(self) -> dict[str, asyncio.Task[None]]:
        """因为观察层需要了解忙碌状态，需要返回当前执行快照而不允许修改调度注册表。"""
        # 1、浅复制字典，调用者不能增删调度中的任务。
        return dict(self._execution.active)

    async def start(self) -> None:
        """因为后端必须在桥接请求前打开状态库，需要显式启动框架存储。"""
        # 1、打开失败时释放已经建立的产品连接。
        try:
            await self._checkpoints.start()
        except Exception:
            self.store.close()
            self._account_repository.close()
            raise

    async def configuration(self, target: str = "execution") -> dict[str, Any]:
        """因为人工配置界面需要安全概况，需要通过配置模块取得永不回传 Key 的投影。"""
        # 1、配置读取和损坏恢复语义统一留在配置模块。
        return self._model_config(target).summary()

    async def save_configuration(
        self, values: dict[str, Any], target: str = "execution"
    ) -> dict[str, Any]:
        """因为在途运行必须固定模型绑定，需要在应用层检查忙碌状态后保存配置。"""
        # 1、这是跨模块的用例约束，不让配置仓库反向依赖调度器。
        if target == "execution" and (self.active or self._execution.state.questions()):
            raise ValueError("请先停止当前任务，再修改模型配置")
        if target == "presentation":
            await self._studio.narrator.close()
        return self._model_config(target).save(values).public()

    async def test_connection(self, target: str = "execution") -> dict[str, Any]:
        """因为用户需要验证真实模型协议，需要调用模型适配层的探测能力而不是启动工作 Agent。"""
        # 1、探测不写入当前会话，真实配置只在可信模型创建路径使用。
        profile = self._model_config(target).require_profile()
        if target == "presentation":
            return await test_presentation_connection(profile)
        return await test_model_connection(profile)

    def _model_config(self, target: str) -> ConfigStore:
        """因为人工配置有两个用途且不能接受任意路径，需要按固定域选择可信仓库。"""
        # 1、表现模型没有执行模型的密钥兜底；未知域直接拒绝。
        if target == "execution":
            return self.config
        if target == "presentation":
            return self._studio.config
        raise ValueError("未知模型配置用途")

    async def new_conversation(self) -> dict[str, Any]:
        """因为新会话需要固定配置引用，需要组合配置读取和产品会话创建。"""
        # 1、只把引用写进产品状态，不写入真实模型参数。
        return self.store.create_conversation(self.config.require_profile().reference)

    async def submit(
        self, conversation_id: str, text: str, request_id: str, member_id: str = "assistant"
    ) -> dict[str, Any]:
        """因为桌面合同不能依赖具体执行器，需要把任务交给独立的运行调度用例。"""
        # 1、幂等、运行额度和状态变更由 ExecutionService 统一控制。
        return await self._execution.submit(conversation_id, text, request_id, member_id)

    async def stop(self, run_id: str) -> dict[str, Any]:
        """因为桌面停止命令需要稳定入口，需要由真实执行服务确认停止。"""
        # 1、不由界面或门面提前伪造终态。
        return await self._execution.stop(run_id)

    def execution_replay(self, method: str, args: list[Any]) -> bool:
        """因为全局额度不能破坏已有请求的幂等，需要只识别已受理请求，再由原用例完整校验。"""
        # 1、此内部查询不暴露为桌面业务入口，也不受理或恢复新任务。
        if len(args) < 3 or not all(isinstance(value, str) for value in args[:3]):
            return False
        if method == "submit":
            return self.store.run_by_request(args[2]) is not None
        if method == "respond":
            return self._execution.state.duplicate(args[2], args[0], args[1].strip()) is not None
        return False

    async def overview(self) -> dict[str, Any]:
        """因为窗口需要恢复本机状态，需要提供会话和能力概况而不读取完整模型配置。"""
        # 1、只暴露产品字段，异步 Task 和 SDK 对象不能出现在前端合同中。
        return {
            "configured": self.config.path.exists(),
            "conversations": self.store.conversations(),
            "active_run": next(iter(self.active), None),
            "pending_count": len(self._execution.state.questions()),
            "capabilities": ["文件读写与检索", "任务规划", "子 Agent 委派", "本机日期时间"],
            "unavailable": ["Shell / 任意代码", "MCP", "浏览器 / Computer Use", "安全 VM"],
        }

    async def events(self, conversation_id: str, after: int = 0) -> list[dict[str, Any]]:
        """因为轨迹断线后需要增量回放，需要在数据库所属线程读取持久事件。"""
        # 1、先验证会话身份，再使用非负游标读取。
        self.store.conversation(conversation_id)
        return self.store.events(conversation_id, max(0, int(after)))

    async def artifacts(self, conversation_id: str) -> list[dict[str, Any]]:
        """因为界面需要真实产物，需要调用独立查询用例而不解析模型回答。"""
        # 1、路径、大小和目录过滤规则统一在产物服务中维护。
        return self._artifacts.list_files(conversation_id)

    async def read_artifact(self, conversation_id: str, virtual_path: str) -> dict[str, Any]:
        """因为文件预览需要统一访问约束，需要把读取交给受限产物查询。"""
        # 1、门面不直接拼接或读取文件路径。
        return self._artifacts.read(conversation_id, virtual_path)

    async def close(self) -> None:
        """因为退出顺序会影响状态可靠性，需要先停任务，再关闭框架和产品数据库。"""
        # 1、执行服务只负责运行，存储生命周期保持由应用统一拥有。
        await self._execution.close()
        await self._studio.close()
        await self._checkpoints.close()
        self.store.close()
        self._account_repository.close()

    async def studio_feed(self, after: int = 0) -> dict[str, Any]:
        """因为空间订阅必须与执行解耦，需要只消费独立表现服务的快照。"""
        # 1、返回版本化的普通字典，不提供 SDK 状态或原始消息。
        return await self._studio.feed(after)

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
        resources = self.paths.desktop_ui.parents[1]
        packaged = resources / "materials/crew-avatar-example/avatar.json"
        source = resources / "doc/assets/crew-avatar-example/avatar.json"
        selected = packaged if packaged.is_file() else source
        if not selected.is_file():
            raise ValueError("随附素材样例缺失，请保留完整程序目录")
        return await asyncio.to_thread(self._avatars.import_manifest, selected)

    async def import_avatar_portrait(self) -> dict[str, Any]:
        """因为用户需要比较新的手绘人物效果，需要导入固定随附图集而不接收任意宿主路径。"""
        # 1、源码和冻结包的图集都跟随前端资源；仍通过同一个正式校验器注册。
        selected = self.paths.desktop_ui / "studio/assets/atelier-v1/avatar.json"
        if not selected.is_file():
            raise ValueError("手绘角色样板缺失，请保留完整程序目录")
        return await asyncio.to_thread(self._avatars.import_manifest, selected)

    async def import_avatar_bundle(self, role: str) -> dict[str, Any]:
        """因为用户需要完整角色套装，需要从有限的随附人物库导入双页清单而不接收任意文件路径。"""
        # 1、这里只选择美术形象，不创建 Agent、修改身份或授予监管权限。
        if role not in ("owner", "assistant", "employee", "guardian"):
            raise ValueError("未知的内置人物素材")
        selected = (
            self.paths.desktop_ui / "studio/assets/library-v1/characters" / role / "avatar.json"
        )
        return await asyncio.to_thread(self._avatars.import_manifest, selected)

    async def member(self, member_id: str) -> dict[str, Any]:
        """因为人工编辑需要查看完整属性，需要通过单独入口返回人物定义而不广播到场景。"""
        # 1、此接口不注册成 Agent 工具。
        return self.accounts.get(member_id)

    async def questions(self, conversation_id: str | None = None) -> list[dict[str, Any]]:
        """因为老板需要处理真实人工瓶颈，需要读取持久化的问题而不使用文本推断。"""
        # 1、问题只在用户展开事项时查询。
        return self._execution.state.questions(conversation_id)

    async def respond(self, request_id: str, answer: str, command_id: str) -> dict[str, Any]:
        """因为界面回答不能直接操作 checkpoint，需要由执行用例验证并恢复任务。"""
        # 1、动画或小模型不能调用此入口自动代替用户回答。
        return await self._execution.respond(request_id, answer, command_id)

    async def member_events(
        self, member_id: str, conversation_id: str, after: int = 0
    ) -> list[dict[str, Any]]:
        """因为人物轨迹只能按用户选择展开，需要查询该成员与会话的事件切片。"""
        # 1、先验证引用，避免把场景订阅变成全量消息广播。
        self.accounts.get(member_id)
        self.store.conversation(conversation_id)
        return self.store.member_events(member_id, conversation_id, after)
