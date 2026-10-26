"""运行额度合同，不依赖具体模型或图框架。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunLimits:
    model_calls: int = 32
    total_seconds: float = 600
    graph_steps: int = 80

    def __post_init__(self) -> None:
        """因为无效额度会造成无限执行或立即失败，需要在组装组件前校验运行上限。"""
        # 1、所有限制必须为正数，不能用零或负数暗示取消限制。
        if self.model_calls < 1 or self.total_seconds <= 0 or self.graph_steps < 1:
            raise ValueError("模型调用次数、总时长和图步数必须为正数")
