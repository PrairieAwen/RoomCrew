"""服务商异常到稳定错误码的转换。"""

from langchain_core.exceptions import ContextOverflowError

from roomcrew.contracts.errors import ExecutionError


def sanitized_error(error: Exception) -> Exception:
    """因为压缩器需要识别上下文超限，需要保留安全的异常类型而不向上传播厂商原始正文。"""
    # 1、只依据明确的标准类型或错误码识别，不把异常消息、Header 和请求数据带出去。
    code = getattr(error, "code", None)
    if isinstance(error, ContextOverflowError) or (
        isinstance(code, str)
        and code
        in {"context_length_exceeded", "context_window_exceeded", "max_context_length_exceeded"}
    ):
        return ContextOverflowError("模型输入超出上下文窗口")
    # 2、其他错误继续转换为稳定产品错误，不能伪装成可压缩故障重试。
    return ExecutionError(failure_code(error))


def failure_code(error: Exception) -> str:
    """因为界面需要区分可处理的连接故障，需要把 SDK 异常转换为不包含秘密的错误码。"""
    # 1、只检查异常类型和状态码，不把异常文本写入日志或轨迹。
    name = type(error).__name__.lower()
    status = getattr(error, "status_code", None)
    if "timeout" in name:
        return "MODEL_TIMEOUT"
    if status in (401, 403):
        return "MODEL_AUTH"
    if status == 429:
        return "MODEL_RATE_LIMIT"
    if status in (400, 404, 422):
        return "MODEL_REQUEST"
    if "connection" in name:
        return "MODEL_CONNECTION"
    return "MODEL_UNAVAILABLE"
