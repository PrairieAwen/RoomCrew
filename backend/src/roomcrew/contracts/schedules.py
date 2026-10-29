"""定时任务管理合同；模型只提交普通参数，不接触调度器、数据库或凭据。"""

from typing import Any, Protocol


class DispatchBusy(ValueError):
    """统一受理入口的暂时繁忙信号，供定时队列延后而非误报失败。"""


class ScheduleCommands(Protocol):
    async def list_schedules(
        self, query: str = "", include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        """因为计划必须按空间隔离，需要只返回当前绑定空间的目录。"""
        # 1、查询不访问其他会议室。
        ...

    async def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        """因为修改前需要确定版本，需要返回本空间的计划与有限执行历史。"""
        # 1、不返回 Agent 提示词或秘密配置。
        ...

    async def create_schedule(self, values: dict[str, Any], command_id: str) -> dict[str, Any]:
        """因为重复工具请求不能创建多个安排，需要以可信命令标识幂等新增。"""
        # 1、目标身份由服务校验。
        ...

    async def update_schedule(
        self, schedule_id: str, changes: dict[str, Any], revision: int, command_id: str
    ) -> dict[str, Any]:
        """因为编辑不能覆盖并发修改，需要按当前版本更新未来安排。"""
        # 1、历史触发快照不随编辑改变。
        ...

    async def set_schedule_state(
        self, schedule_id: str, state: str, revision: int, command_id: str
    ) -> dict[str, Any]:
        """因为暂停、恢复和取消属于不同意图，需要通过白名单状态管理持久计划。"""
        # 1、取消保留历史，不能由恢复动作复活。
        ...
