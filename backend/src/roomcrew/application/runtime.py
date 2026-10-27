"""桌面应用用例门面；不包含图构建、SDK 事件解析或文件路径算法。"""

import asyncio
from typing import Any

from roomcrew.accounts.service import AccountService
from roomcrew.application.artifacts import ArtifactService
from roomcrew.application.execution import ExecutionService
from roomcrew.application.options import RunOptions
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
        self.accounts = self._create_accounts()
        self._aux_config = ConfigStore(paths.private, "presentation-model.dpapi")
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
            return self._aux_config
        raise ValueError("未知模型配置用途")

    async def new_conversation(self) -> dict[str, Any]:
        """因为新会话需要固定配置引用，需要组合配置读取和产品会话创建。"""
        # 1、只把引用写进产品状态，不写入真实模型参数。
        return self.store.create_conversation(self.config.require_profile().reference)

    async def agent_configurations(self) -> list[dict[str, Any]]:
        """因为通用执行框架需要不依赖人物编辑器的入口，需要返回本空间 Agent 定义。"""
        # 1、可信配置入口与模型的 list_agents 工具分离，后者不读取完整底层配置。
        return self.accounts.repository.agent_definitions()

    async def save_agent_configuration(
        self, values: dict[str, Any], expected_revision: int
    ) -> dict[str, Any]:
        """因为共享定义可能被多个执行者引用，需要在空闲时按版本保存配置。"""
        # 1、保护当前和待恢复的执行快照。
        if self.active or self._execution.state.questions():
            raise ValueError("请先完成或取消当前任务，再修改 Agent 定义")
        return self.accounts.save_agent(values, expected_revision)

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
            "capabilities": [
                "文件读写与检索",
                "任务规划",
                "子 Agent 委派",
                "Agent 目录",
                "Skills",
                "HTTP MCP",
                "隔离 Python",
            ],
            "unavailable": ["Shell", "浏览器 / Computer Use", "安全 VM"],
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

    async def native_events(self, conversation_id: str, after: int = 0) -> list[dict[str, Any]]:
        """因为客户端可独立适配官方轨迹，需要提供保留原生字段的分页查询。"""
        # 1、验证会话再查询；后端不将官方事件转换成素材动作。
        self.store.conversation(conversation_id)
        return self.store.native_events(conversation_id, after)

    async def read_artifact(self, conversation_id: str, virtual_path: str) -> dict[str, Any]:
        """因为文件预览需要统一访问约束，需要把读取交给受限产物查询。"""
        # 1、门面不直接拼接或读取文件路径。
        return self._artifacts.read(conversation_id, virtual_path)

    async def close(self) -> None:
        """因为退出顺序会影响状态可靠性，需要先停任务，再关闭框架和产品数据库。"""
        # 1、执行服务只负责运行，存储生命周期保持由应用统一拥有。
        await self._execution.close()
        await self._checkpoints.close()
        self.store.close()
        self._account_repository.close()

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

    def _create_accounts(self) -> AccountService:
        """因为执行框架只需要人员身份和能力定义，需要提供与桌面扩展无关的默认账号服务。"""
        # 1、桌面组合层可以覆盖属性校验，后端不导入素材或动作模块。
        return AccountService(self._account_repository)

    async def save_member(self, values: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        """因为 Agent 配置需要固定运行快照，需要在空闲时接受可信用户的配置修改。"""
        # 1、在途或待答复任务不切换底层定义。
        if self.active or self._execution.state.questions():
            raise ValueError("请先完成或取消当前任务，再修改成员")
        return self.accounts.save(values, expected_revision)

    async def generate_auxiliary(self, text: str) -> str:
        """因为客户端可能需要独立辅助文本，需要通过可信工厂调用单独模型并只返回字符串。"""
        # 1、只接受有界文本，模型配置不进入客户端对象或任务上下文。
        from roomcrew.models.factory import create_model

        if not isinstance(text, str) or len(text) > 6000:
            raise ValueError("辅助文本请求超出限制")
        model = create_model(self._aux_config.require_profile())
        try:
            reply = await model.ainvoke(text, max_tokens=160)
            return reply.content if isinstance(reply.content, str) else ""
        finally:
            await model.close()
