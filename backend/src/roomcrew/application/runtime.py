"""桌面应用用例门面；不包含图构建、SDK 事件解析或文件路径算法。"""

import asyncio
from typing import Any

from roomcrew.application.artifacts import ArtifactService
from roomcrew.application.execution import ExecutionService
from roomcrew.application.options import RunOptions
from roomcrew.config.store import ConfigStore
from roomcrew.models.connection import test_model_connection
from roomcrew.platform.paths import AppPaths
from roomcrew.storage.checkpoints import CheckpointStore
from roomcrew.storage.sessions import SessionStore


class Runtime:
    def __init__(self, paths: AppPaths, options: RunOptions | None = None) -> None:
        """因为桌面需要稳定入口而各模块需要独立演进，需要在应用边界组装服务。"""
        # 1、只连接职责模块，不把模型秘密注入图状态或前端合同。
        self.paths = paths
        self.config = ConfigStore(paths.private)
        self.store = SessionStore(paths.data / "sessions.sqlite")
        self._checkpoints = CheckpointStore(paths.data / "runtime.sqlite")
        self._artifacts = ArtifactService(paths, self.store)
        self._execution = ExecutionService(
            paths=paths,
            config=self.config,
            store=self.store,
            checkpoints=self._checkpoints,
            options=options or RunOptions(),
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
            raise

    async def configuration(self) -> dict[str, Any]:
        """因为人工配置界面需要安全概况，需要通过配置模块取得永不回传 Key 的投影。"""
        # 1、配置读取和损坏恢复语义统一留在配置模块。
        return self.config.summary()

    async def save_configuration(self, values: dict[str, Any]) -> dict[str, Any]:
        """因为在途运行必须固定模型绑定，需要在应用层检查忙碌状态后保存配置。"""
        # 1、这是跨模块的用例约束，不让配置仓库反向依赖调度器。
        if self.active:
            raise ValueError("请先停止当前任务，再修改模型配置")
        return self.config.save(values).public()

    async def test_connection(self) -> dict[str, Any]:
        """因为用户需要验证真实模型协议，需要调用模型适配层的探测能力而不是启动工作 Agent。"""
        # 1、探测不写入当前会话，真实配置只在可信模型创建路径使用。
        return await test_model_connection(self.config.require_profile())

    async def new_conversation(self) -> dict[str, Any]:
        """因为新会话需要固定配置引用，需要组合配置读取和产品会话创建。"""
        # 1、只把引用写进产品状态，不写入真实模型参数。
        return self.store.create_conversation(self.config.require_profile().reference)

    async def submit(self, conversation_id: str, text: str, request_id: str) -> dict[str, Any]:
        """因为桌面合同不能依赖具体执行器，需要把任务交给独立的运行调度用例。"""
        # 1、幂等、运行额度和状态变更由 ExecutionService 统一控制。
        return await self._execution.submit(conversation_id, text, request_id)

    async def stop(self, run_id: str) -> dict[str, Any]:
        """因为桌面停止命令需要稳定入口，需要由真实执行服务确认停止。"""
        # 1、不由界面或门面提前伪造终态。
        return await self._execution.stop(run_id)

    async def overview(self) -> dict[str, Any]:
        """因为窗口需要恢复本机状态，需要提供会话和能力概况而不读取完整模型配置。"""
        # 1、只暴露产品字段，异步 Task 和 SDK 对象不能出现在前端合同中。
        return {
            "configured": self.config.path.exists(),
            "conversations": self.store.conversations(),
            "active_run": next(iter(self.active), None),
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
        await self._checkpoints.close()
        self.store.close()
