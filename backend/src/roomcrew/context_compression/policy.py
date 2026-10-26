"""压缩参数属于独立策略，不混入配置存储或应用运行控制。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompressionPolicy:
    trim_tokens_to_summarize: int | None = None
    summary_prompt: str | None = None

    def __post_init__(self) -> None:
        """因为错误的摘要参数会丢失输入或破坏模板，需要在构图前验证明确配置的参数。"""
        # 1、未设置时沿用 SDK 默认值，不另建第二套摘要机制。
        if self.trim_tokens_to_summarize is not None and self.trim_tokens_to_summarize < 256:
            raise ValueError("摘要输入预算不能小于 256 Token")
        if self.summary_prompt is not None and "{messages}" not in self.summary_prompt:
            raise ValueError("自定义摘要提示必须保留 {messages} 占位符")
