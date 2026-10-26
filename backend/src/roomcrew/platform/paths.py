"""区分可更新的程序资源、私有配置和 Agent 可以访问的任务文件。"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    private: Path
    data: Path
    sessions: Path
    frontend: Path

    @classmethod
    def create(cls, root: Path | None = None) -> "AppPaths":
        """因为升级不能覆盖用户数据，需要分别定位本机数据和随应用分发的界面资源。"""
        # 1、开发和冻结程序分别定位只读资源，用户数据默认进入当前用户的本地应用目录。
        bundle_root = getattr(sys, "_MEIPASS", None)
        resources = Path(bundle_root) if bundle_root else Path(__file__).resolve().parents[4]
        base = (root or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RoomCrew").resolve()
        paths = cls(
            base,
            base / "private",
            base / "data",
            base / "data/sessions",
            resources / "frontend/src",
        )
        # 2、提前建立数据目录；配置始终位于 Agent 会话根目录之外。
        for folder in (paths.private, paths.data, paths.sessions):
            folder.mkdir(parents=True, exist_ok=True)
        return paths

    def session_files(self, conversation_id: str) -> Path:
        """因为前端传入的会话标识不能变成任意系统路径，需要限定为程序生成的十六进制 ID。"""
        # 1、拒绝分隔符和未知格式，返回该会话独立的产物目录。
        if len(conversation_id) != 32 or any(c not in "0123456789abcdef" for c in conversation_id):
            raise ValueError("会话标识无效")
        target = self.sessions / conversation_id / "files"
        target.mkdir(parents=True, exist_ok=True)
        return target
