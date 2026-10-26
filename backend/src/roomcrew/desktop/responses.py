"""桌面接口的统一安全响应。"""

import functools
from collections.abc import Callable
from typing import Any

from roomcrew.contracts.errors import ERROR_MESSAGES, ExecutionError


def public_reply(method: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """因为桌面桥需要稳定且不泄露 SDK 异常的响应，需要统一包装成功结果与安全错误。"""

    # 1、保留函数签名，便于 WebView 发现明确的公共方法。
    @functools.wraps(method)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """因为桥方法可能读取失败或遇到模型错误，需要将异常转换为可展示而不含秘密的响应。"""
        # 1、返回产品数据，未知异常只给通用提示，不序列化 traceback。
        try:
            return {"ok": True, "data": method(*args, **kwargs)}
        except ExecutionError as error:
            return {"ok": False, "error": ERROR_MESSAGES.get(str(error), "模型调用失败")}
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        except Exception:
            return {"ok": False, "error": "本地操作失败，请检查应用数据目录是否可写，或重启后重试"}

    return wrapped
