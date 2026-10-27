"""稳定错误码，不携带 SDK 原始异常。"""

ERROR_MESSAGES = {
    "CONTEXT_LIMIT": "压缩后输入仍超出模型上下文窗口，请缩小任务或调整正确的窗口配置。",
    "CAPABILITY_UNAVAILABLE": "当前发行版尚未开放此能力，不能启用或回退到宿主执行。",
    "SKILL_SOURCE_INVALID": "显式技能来源不存在、为空或超出允许目录，请检查配置。",
    "MCP_CONNECTION": "无法发现 MCP 工具，请检查服务器地址、服务状态和工具数量。",
    "PYTHON_UNAVAILABLE": "隔离 Python 运行时不可用，未回退到宿主执行。",
    "PYTHON_FAILED": "隔离 Python 进程启动失败，请检查运行时完整性。",
    "MODEL_TIMEOUT": "模型请求超时，请检查网络，或在配置中调整超时后新建会话。",
    "MODEL_AUTH": "模型认证失败，请检查 API Key、权限和接口地址。",
    "MODEL_RATE_LIMIT": "模型服务限流或额度不足，请检查服务商控制台。",
    "MODEL_REQUEST": "接口拒绝了请求，请检查 Base URL、模型 ID 和工具调用兼容性。",
    "MODEL_CONNECTION": "无法连接模型接口，请检查网络和 Base URL。",
    "MODEL_UNAVAILABLE": "模型服务返回异常，请检查配置或稍后新建会话重试。",
    "RUN_TIMEOUT": "本轮超过 10 分钟，已停止继续执行。",
    "RUN_LIMIT": "本轮达到执行步数或模型调用上限，已停止继续执行。",
    "RUN_ERROR": "执行过程中发生异常，本轮已停止；请查看此前工具轨迹并新建会话重试。",
    "APP_RESTARTED": "应用在运行期间关闭，本轮已中断，未自动重做工具。",
}


class ExecutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        """因为未知异常不能泄露参数，需要只允许已知错误码进入公开执行链。"""
        # 1、不接受原始 SDK 文本作为错误码。
        self.code = code if code in ERROR_MESSAGES else "RUN_ERROR"
        super().__init__(self.code)
