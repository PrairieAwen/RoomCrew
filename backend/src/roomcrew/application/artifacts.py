"""实际产物查询用例，与 Agent 图和桌面渲染解耦。"""

from typing import Any

from roomcrew.platform.paths import AppPaths
from roomcrew.security.paths import resolve_task_path
from roomcrew.storage.sessions import SessionStore


class ArtifactService:
    def __init__(self, paths: AppPaths, store: SessionStore) -> None:
        """因为产物必须绑定已存在的会话，需要注入路径与会话查询，避免读取任意系统文件。"""
        # 1、本服务不创建模型、不解释任务文本，也不采信模型声明的文件清单。
        self._paths = paths
        self._store = store

    def list_files(self, conversation_id: str) -> list[dict[str, Any]]:
        """因为真实文件才是交付证据，需要枚举当前会话目录并过滤链接和框架内部资料。"""
        # 1、检查会话并固定根目录，不把任意外部路径当作会话标识。
        self._store.conversation(conversation_id)
        root = self._paths.session_files(conversation_id)
        result = []
        # 2、仅返回真实文件的虚拟路径，隐藏摘要外置历史与内部工具结果。
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                continue
            relative = path.relative_to(root).as_posix()
            if relative.startswith(
                (".deepagents/", "conversation_history/", "large_tool_results/")
            ):
                continue
            result.append({"path": "/" + relative, "size": path.stat().st_size})
            if len(result) >= 300:
                break
        return result

    def read(self, conversation_id: str, virtual_path: str) -> dict[str, Any]:
        """因为用户需要核对文件内容，需要统一路径检查并限制为有限大小的 UTF-8 纯文本。"""
        # 1、使用安全模块的统一解析，而不是在每个用例重复实现路径约束。
        self._store.conversation(conversation_id)
        path = resolve_task_path(self._paths.session_files(conversation_id), virtual_path)
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("文件不存在或大于 1 MB")
        # 2、只返回文本，前端不得执行 HTML 或脚本。
        try:
            return {"path": virtual_path, "text": path.read_text(encoding="utf-8")}
        except UnicodeError as error:
            raise ValueError("该文件不是可预览的 UTF-8 文本") from error
