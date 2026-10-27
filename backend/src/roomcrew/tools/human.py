"""真正的可持久化人工询问工具；不是系统权限审批。"""

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def ask_user(
    question: str,
    choices: list[str],
    runtime: ToolRuntime,
    interaction_type: str = "question",
    allow_other: bool = True,
) -> str:
    """因为任务缺少必须由用户提供的信息，需要暂停并等待明确回答，而不是替用户猜测。"""
    # 1、仅接收有限的问题和建议选项，不把模型输出当成权限许可。
    if (
        not question.strip()
        or len(question) > 2000
        or len(choices) > 8
        or any(len(item) > 120 for item in choices)
        or interaction_type not in {"question", "choice", "approval"}
        or not isinstance(allow_other, bool)
        or (not allow_other and not choices)
    ):
        raise ValueError("人工问题或选项长度无效")
    # 2、中断前不执行副作用；恢复时框架重放本函数并返回已保存的用户回答。
    answer = interrupt(
        {
            "kind": "question",
            "question": question,
            "choices": choices,
            "tool_call_id": runtime.tool_call_id,
            "interaction_type": interaction_type,
            "allow_other": allow_other,
        }
    )
    return str(answer)
